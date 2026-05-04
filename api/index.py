# web_app.py
"""FastAPI backend for the Fleet Tracker.

Provides:
- Real‑time device tracking (threads started from web_server.py)
- Endpoints to view live data, export CSV/JSON, and show a simple UI.
- Uses geocoder (IP), SQLite (SQLAlchemy), CSV live log, and optional reverse‑geocode.
"""

import os
import csv
import json
import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Optional, Dict

import geocoder
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pymongo
from bson import ObjectId

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = "fleet_command"

def get_db():
    if MONGO_URI:
        client = pymongo.MongoClient(MONGO_URI)
        return client[DB_NAME]
    return None

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
API_DIR = os.path.abspath(os.path.dirname(__file__))
BASE_DIR = os.path.abspath(os.path.join(API_DIR, ".."))
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
CSV_LIVE = os.path.join("/tmp", "live_location_log.csv")
DB_PATH = os.path.join("/tmp", "fleet_tracker.db")
LOG_FILE = os.path.join("/tmp", "fleet_tracker.log")
POLL_INTERVAL = 30  # seconds per device
API_DELAY_MS = 1000
MAX_RETRY = 3

os.makedirs(EXPORT_DIR, exist_ok=True)

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Database (SQLAlchemy)
# ----------------------------------------------------------------------
Base = declarative_base()

class LocationLog(Base):
    __tablename__ = "location_logs"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, nullable=False)
    device_name = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    city = Column(String, nullable=True)
    country = Column(String, nullable=True)
    address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Target(Base):
    __tablename__ = "targets"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    ip_address = Column(String, nullable=True) # Optional: if empty, tracks self

engine = create_engine(f"sqlite:///{DB_PATH}", future=True, echo=False)
SessionLocal = sessionmaker(bind=engine, future=True)

def init_db() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized.")
    except Exception as e:
        logger.warning(f"Could not initialize SQLite (Read-only?): {e}")

# ----------------------------------------------------------------------
# Rate‑limit helper
# ----------------------------------------------------------------------
_last_api_call = 0.0

def _respect_rate_limit() -> None:
    global _last_api_call
    now = time.time()
    elapsed = (now - _last_api_call) * 1000
    if elapsed < API_DELAY_MS:
        time.sleep((API_DELAY_MS - elapsed) / 1000.0)
    _last_api_call = time.time()

# ----------------------------------------------------------------------
# Geolocation utilities
# ----------------------------------------------------------------------
def get_location_ip() -> Tuple[float, float, Optional[str], Optional[str]]:
    """Return lat, lng, city, country using public IP via geocoder."""
    for attempt in range(1, MAX_RETRY + 1):
        try:
            g = geocoder.ip("me")
            if g.ok and g.latlng:
                lat, lng = map(float, g.latlng)
                return lat, lng, g.city, g.country
            raise RuntimeError("Geocoder did not return coordinates.")
        except Exception as exc:
            logger.warning(f"IP geolocation attempt {attempt}/{MAX_RETRY}: {exc}")
            if attempt < MAX_RETRY:
                time.sleep(2 ** attempt)
    raise RuntimeError("IP geolocation failed after retries.")

def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Optional address via OpenStreetMap Nominatim (may return None)."""
    try:
        _respect_rate_limit()
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"format": "json", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1}
        headers = {"User-Agent": "FleetTracker/1.0 (example@example.com)"}
        resp = requests.get(url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        return resp.json().get("display_name")
    except Exception:
        return None

# ----------------------------------------------------------------------
# CSV live log (append‑only)
# ----------------------------------------------------------------------
def init_live_csv() -> None:
    if not os.path.isfile(CSV_LIVE):
        with open(CSV_LIVE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Waktu",
                "ID_Perangkat",
                "Nama_Aset",
                "Lintang",
                "Bujur",
                "Kota",
                "Negara",
                "Alamat",
            ])
        logger.info("Live CSV diinisialisasi.")

def append_live_csv(
    device_id: int,
    device_name: str,
    lat: float,
    lon: float,
    city: Optional[str],
    country: Optional[str],
    address: Optional[str],
) -> None:
    # Adjust to WITA (UTC+8)
    from datetime import timedelta
    tz_wita = timezone(timedelta(hours=8))
    ts = datetime.now(tz_wita).strftime("%d-%m-%Y %H:%M:%S")
    with open(CSV_LIVE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            ts,
            device_id,
            device_name,
            lat,
            lon,
            city or "",
            country or "",
            address or "",
        ])

# ----------------------------------------------------------------------
# Tracking worker (run in a thread per device)
# ----------------------------------------------------------------------
def track_device(
    device_id: int,
    device_name: str,
    ip_address: Optional[str] = None,
    poll_interval: int = POLL_INTERVAL,
    stop_event: threading.Event = None,
) -> None:
    """Continuously obtain location (IP fallback) and store it.
    If ip_address is provided, it tracks that IP instead of 'me'.
    """
    session = SessionLocal()
    target_ip = ip_address if ip_address else "me"
    
    while not (stop_event and stop_event.is_set()):
        try:
            # Modified to use specific IP
            for attempt in range(1, MAX_RETRY + 1):
                try:
                    g = geocoder.ip(target_ip)
                    if g.ok and g.latlng:
                        lat, lng = map(float, g.latlng)
                        city, country = g.city, g.country
                        break
                    raise RuntimeError("Geocoder failed")
                except Exception as e:
                    if attempt == MAX_RETRY: raise e
                    time.sleep(2**attempt)
            
            address = reverse_geocode(lat, lng)
            # DB insert
            log = LocationLog(
                device_id=device_id,
                device_name=device_name,
                lat=lat,
                lon=lng,
                city=city,
                country=country,
                address=address,
                timestamp=datetime.now(timezone(timedelta(hours=8))),
            )
            session.add(log)
            session.commit()
            # CSV live
            append_live_csv(device_id, device_name, lat, lng, city, country, address)
            logger.info(
                f"[✅] {device_name} ({target_ip}) → {lat:.5f},{lng:.5f}"
            )
        except Exception as exc:
            logger.error(f"[❌] Tracking error for {device_name}: {exc}")
        time.sleep(poll_interval)

# ----------------------------------------------------------------------
# FastAPI app definition
# ----------------------------------------------------------------------
app = FastAPI(title="Fleet Tracker", description="Real‑time asset tracking using IP geolocation", version="1.0.0")

# Mount static files and Jinja2 templates
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.on_event("startup")
async def startup_event():
    init_db()
    init_live_csv()
    logger.info("FastAPI startup complete.")

# ----------------------------------------------------------------------
# UI – index page (shows latest live rows in a table)
# ----------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    rows: List[List[str]] = []
    targets: List[dict] = []
    
    db = get_db()
    if db:
        # MongoDB Mode
        logs = list(db.location_logs.find().sort("timestamp", -1).limit(20))
        for l in logs:
            rows.append([
                l.get("timestamp_str", ""),
                str(l.get("device_id", "")),
                l.get("device_name", ""),
                l.get("lat", ""),
                l.get("lon", ""),
                l.get("city", ""),
                l.get("country", ""),
                l.get("address", "")
            ])
        targets = list(db.targets.find())
        for t in targets: t["id"] = str(t["_id"])
    else:
        # SQLite Mode
        session = SessionLocal()
        try:
            if os.path.isfile(CSV_LIVE):
                with open(CSV_LIVE, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    next(reader)
                    for row in reader: rows.append(row)
                rows = rows[-20:]
            targets_db = session.query(Target).all()
            targets = [{"id": t.id, "name": t.name, "ip_address": t.ip_address} for t in targets_db]
        finally:
            session.close()
            
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"rows": rows, "targets": targets},
    )

@app.get("/share-location", response_class=HTMLResponse)
async def share_location_ui(request: Request):
    return templates.TemplateResponse(request=request, name="share.html", context={})

# ----------------------------------------------------------------------
# Target Management & Data Reset
# ----------------------------------------------------------------------
from fastapi import Form
from fastapi.responses import RedirectResponse

@app.post("/targets/add")
async def add_target(name: str = Form(...), description: str = Form(None), ip_address: str = Form(None)):
    session = SessionLocal()
    new_target = Target(name=name, description=description, ip_address=ip_address)
    session.add(new_target)
    session.commit()
    session.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/targets/delete/{target_id}")
async def delete_target(target_id: int):
    session = SessionLocal()
    target = session.query(Target).filter(Target.id == target_id).first()
    if target:
        session.delete(target)
        session.commit()
    session.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/data/reset")
async def reset_data():
    session = SessionLocal()
    session.query(LocationLog).delete()
    session.commit()
    session.close()
    # Also clear CSV
    if os.path.isfile(CSV_LIVE):
        os.remove(CSV_LIVE)
    init_live_csv()
    return RedirectResponse(url="/", status_code=303)

from pydantic import BaseModel
class LocationReport(BaseModel):
    name: str
    lat: float
    lon: float

@app.post("/api/report_location")
async def report_location(report: LocationReport):
    db = get_db()
    tz_wita = timezone(timedelta(hours=8))
    ts_str = datetime.now(tz_wita).strftime("%d-%m-%Y %H:%M:%S")
    address = reverse_geocode(report.lat, report.lon)

    if db:
        # MongoDB Mode
        target = db.targets.find_one({"name": report.name})
        if not target:
            res = db.targets.insert_one({"name": report.name, "description": "Remote Broadcaster"})
            target_id = str(res.inserted_id)
        else:
            target_id = str(target["_id"])
        
        db.location_logs.insert_one({
            "device_id": target_id,
            "device_name": report.name,
            "lat": report.lat,
            "lon": report.lon,
            "address": address,
            "timestamp": datetime.now(tz_wita),
            "timestamp_str": ts_str
        })
        return {"status": "ok"}
    else:
        # SQLite Mode
        session = SessionLocal()
        try:
            target = session.query(Target).filter(Target.name == report.name).first()
            if not target:
                target = Target(name=report.name, description="Remote Broadcaster")
                session.add(target); session.commit(); session.refresh(target)
            
            new_log = LocationLog(
                device_id=target.id, device_name=target.name,
                lat=report.lat, lon=report.lon, address=address,
                timestamp=datetime.now(timezone(timedelta(hours=8)))
            )
            session.add(new_log); session.commit()
            append_live_csv(target.id, target.name, report.lat, report.lon, None, None, address)
            return {"status": "ok"}
        finally:
            session.close()

# ----------------------------------------------------------------------
# Export endpoints (full DB export)
# ----------------------------------------------------------------------
def _export_csv_path() -> str:
    path = os.path.join(EXPORT_DIR, "fleet_export.csv")
    session = SessionLocal()
    rows = session.query(LocationLog).order_by(LocationLog.timestamp).all()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "ID_Perangkat", "Nama_Aset", "Lintang", "Bujur", "Kota", "Negara", "Alamat", "Waktu"])
        for r in rows:
            writer.writerow([
                r.id,
                r.device_id,
                r.device_name,
                r.lat,
                r.lon,
                r.city or "",
                r.country or "",
                r.address or "",
                r.timestamp.strftime("%d-%m-%Y %H:%M:%S"),
            ])
    return path

def _export_json_path() -> str:
    path = os.path.join(EXPORT_DIR, "fleet_export.json")
    session = SessionLocal()
    rows = session.query(LocationLog).order_by(LocationLog.timestamp).all()
    data = [
        {
            "id": r.id,
            "device_id": r.device_id,
            "device_name": r.device_name,
            "lat": r.lat,
            "lon": r.lon,
            "city": r.city,
            "country": r.country,
            "address": r.address,
            "timestamp_utc": r.timestamp.isoformat(),
        }
        for r in rows
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path

@app.get("/export/csv")
async def export_csv():
    path = _export_csv_path()
    return FileResponse(path, media_type="text/csv", filename="fleet_export.csv")

@app.get("/export/json")
async def export_json():
    path = _export_json_path()
    return FileResponse(path, media_type="application/json", filename="fleet_export.json")

# ----------------------------------------------------------------------
# API to fetch latest live rows as JSON (for possible JS polling)
# ----------------------------------------------------------------------
@app.get("/api/map_data")
async def api_map_data():
    """Return the latest location for every active target."""
    db = get_db()
    result = []
    
    if db:
        # MongoDB Mode
        device_names = db.location_logs.distinct("device_name")
        for name in device_names:
            latest = db.location_logs.find_one({"device_name": name}, sort=[("timestamp", -1)])
            if latest:
                result.append({
                    "name": latest["device_name"],
                    "lat": latest["lat"],
                    "lon": latest["lon"],
                    "address": latest.get("address") or "Lokasi terdeteksi",
                    "time": latest.get("timestamp_str") or ""
                })
    else:
        # SQLite Mode
        session = SessionLocal()
        try:
            device_names = [r[0] for r in session.query(LocationLog.device_name).distinct().all()]
            for name in device_names:
                latest = session.query(LocationLog).filter(LocationLog.device_name == name).order_by(LocationLog.timestamp.desc()).first()
                if latest:
                    result.append({
                        "name": latest.device_name,
                        "lat": latest.lat,
                        "lon": latest.lon,
                        "address": latest.address or "Lokasi terdeteksi",
                        "time": latest.timestamp.strftime("%d-%m-%Y %H:%M:%S")
                    })
        finally:
            session.close()
    return result

# End of web_app.py
