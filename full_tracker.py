import threading
import time
import logging
import os
import csv
import json
from datetime import datetime, timezone

# Local imports from the existing project (same directory)
from models import init_db, get_session, Employee, Asset, LocationLog
from geoutil import get_location_by_ip, get_location_by_wifi, reverse_geocode
from safety import is_in_danger, is_location_stale
from config import (
    EXPORT_DIR,
    POLL_INTERVAL,
    GOOGLE_GEO_API_KEYS,
)

# ------------------------------------------------------------
# Logging configuration (both console and file)
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("full_tracker.log"),
        logging.StreamHandler()
    ]
)

# ------------------------------------------------------------
# Helper: CSV logger (append each location record)
# ------------------------------------------------------------
CSV_PATH = "location_log.csv"

def init_csv():
    """Create CSV file with header if it does not exist."""
    if not os.path.isfile(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp_utc",
                "entity_type",
                "entity_id",
                "latitude",
                "longitude",
                "city",
                "country",
                "address",
            ])

def append_csv(entry):
    """Append a dict with required keys to CSV file."""
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            entry.get("timestamp"),
            entry.get("entity_type"),
            entry.get("entity_id"),
            entry.get("lat"),
            entry.get("lon"),
            entry.get("city"),
            entry.get("country"),
            entry.get("address"),
        ])

# ------------------------------------------------------------
# Core tracking function for a single entity (asset or employee)
# ------------------------------------------------------------
def track_entity(entity, wifi_data=None, stop_event=None):
    """Continuously fetch location for *entity* until *stop_event* is set.
    *wifi_data* is a list of Wi‑Fi access‑point dicts (or None to use IP).
    """
    session = get_session()
    while not (stop_event and stop_event.is_set()):
        try:
            # ---------- Geolocation ----------
            if wifi_data:
                loc = get_location_by_wifi(wifi_data)
                source = "WiFi"
            else:
                loc = get_location_by_ip()
                source = "IP"
            if not loc:
                raise RuntimeError("Tidak ada lokasi yang diperoleh")
            lat, lon = loc
            # optional reverse‑geocode for human readable address
            address = reverse_geocode(lat, lon)
            ts = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

            # ---------- SQLite log ----------
            log = LocationLog(
                entity_type=entity.__tablename__,
                entity_id=entity.id,
                lat=lat,
                lon=lon,
                timestamp=datetime.utcnow().replace(tzinfo=timezone.utc),
                address=address,
            )
            session.add(log)
            session.commit()

            # ---------- CSV log ----------
            csv_entry = {
                "timestamp": ts,
                "entity_type": entity.__tablename__,
                "entity_id": entity.id,
                "lat": lat,
                "lon": lon,
                "city": None,
                "country": None,
                "address": address,
            }
            # If geocoder ip provided city/country we could add here; omitted for brevity.
            append_csv(csv_entry)

            # ---------- Safety check ----------
            if is_in_danger(lat, lon):
                logging.warning(f"{entity.__class__.__name__} '{entity.name}' berada di zona bahaya! (via {source})")
            else:
                logging.info(f"{entity.__class__.__name__} '{entity.name}' lokasi aman ({lat:.5f},{lon:.5f}) via {source}")
        except Exception as exc:
            logging.error(f"Error tracking {entity.name}: {exc}")
        finally:
            time.sleep(POLL_INTERVAL)

# ------------------------------------------------------------
# Export functions (CSV & JSON) for all logs in SQLite
# ------------------------------------------------------------
def ensure_export_dir():
    os.makedirs(EXPORT_DIR, exist_ok=True)

def export_to_csv(filename="fleet_logs.csv"):
    ensure_export_dir()
    path = os.path.join(EXPORT_DIR, filename)
    sess = get_session()
    logs = sess.query(LocationLog).order_by(LocationLog.timestamp).all()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id",
            "entity_type",
            "entity_id",
            "latitude",
            "longitude",
            "timestamp_utc",
            "address",
        ])
        for log in logs:
            writer.writerow([
                log.id,
                log.entity_type,
                log.entity_id,
                log.lat,
                log.lng,
                log.timestamp.isoformat(),
                log.address or "",
            ])
    logging.info(f"CSV diekspor ke {path}")

def export_to_json(filename="fleet_logs.json"):
    ensure_export_dir()
    path = os.path.join(EXPORT_DIR, filename)
    sess = get_session()
    logs = sess.query(LocationLog).order_by(LocationLog.timestamp).all()
    data = [
        {
            "id": log.id,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "latitude": log.lat,
            "longitude": log.lng,
            "timestamp_utc": log.timestamp.isoformat(),
            "address": log.address,
        }
        for log in logs
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logging.info(f"JSON diekspor ke {path}")

# ------------------------------------------------------------
# Main entry – sets up demo assets/employees, starts tracking threads
# ------------------------------------------------------------
def main():
    logging.info("=== Memulai Full Tracker ===")
    init_db()
    init_csv()
    session = get_session()

    # Register demo entities (if not already present)
    jenn = session.query(Employee).filter_by(name="Jennifer").first()
    if not jenn:
        jenn = Employee(name="Jennifer", health_status="aktif")
        session.add(jenn)
    truck = session.query(Asset).filter_by(name="Truck #12").first()
    if not truck:
        truck = Asset(name="Truck #12", description="Truck pengangkut barang")
        session.add(truck)
    session.commit()

    # Example Wi‑Fi data (you can replace with real scans)
    sample_wifi = [
        {"macAddress": "00:11:22:33:44:55", "signalStrength": -55, "channel": 11},
        {"macAddress": "66:77:88:99:AA:BB", "signalStrength": -70, "channel": 6},
    ]
    # Map entity ID -> wifi data (or None to fallback to IP)
    wifi_map = {
        truck.id: sample_wifi,   # truck uses Wi‑Fi (demo)
        jenn.id: None,           # Jennifer uses IP (default)
    }

    stop_event = threading.Event()
    threads = []
    # Start a thread per entity
    for entity in [jenn, truck]:
        t = threading.Thread(
            target=track_entity,
            args=(entity, wifi_map.get(entity.id), stop_event),
            daemon=True,
        )
        t.start()
        threads.append(t)

    # Let it run for a limited time (e.g., 60 seconds) – adjust as needed
    run_seconds = 60
    logging.info(f"Tracking berjalan selama {run_seconds} detik…")
    try:
        time.sleep(run_seconds)
    except KeyboardInterrupt:
        logging.info("Interupsi pengguna – menghentikan tracker…")
    finally:
        stop_event.set()
        for t in threads:
            t.join()
        logging.info("Semua thread selesai.")

    # Export collected data
    export_to_csv()
    export_to_json()
    logging.info("=== Full Tracker selesai ===")

if __name__ == "__main__":
    main()
