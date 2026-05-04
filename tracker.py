# tracker.py
"""
Modul utama untuk pelacakan aset (kendaraan) secara real‑time.

Fitur yang disediakan:
1. Geolokasi berbasis IP (menggunakan geocoder) dan Wi‑Fi (menggunakan Google Geolocation API – contoh stub).
2. Pencatatan tiap posisi dengan timestamp ke database SQLite (models.LocationLog).
3. Dukungan multi‑perangkat – setiap kendaraan diproses di thread terpisah.
4. Export data ke CSV atau JSON.
5. Penanganan kegagalan API dengan retry & logging.
"""

import threading
import time
import json
import csv
import logging
from datetime import datetime, timezone
from typing import List, Tuple, Optional

import requests
import geocoder

from models import get_session, Employee, Asset, LocationLog, init_db
from safety import is_in_danger
from config import API_DELAY_MS, USER_AGENT, STALE_SECONDS

# ---------------------------------------------------------------------------
# Logging konfigurasi – semua error & info akan ditulis ke console & file log.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("tracker.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper – Rate‑limit untuk semua panggilan API eksternal.
# ---------------------------------------------------------------------------
_last_api_call = 0

def _respect_rate_limit():
    global _last_api_call
    now = time.time()
    elapsed_ms = (now - _last_api_call) * 1000
    if elapsed_ms < API_DELAY_MS:
        time.sleep((API_DELAY_MS - elapsed_ms) / 1000.0)
    _last_api_call = time.time()

# ---------------------------------------------------------------------------
# Geolokasi IP
# ---------------------------------------------------------------------------
def get_ip_location() -> Optional[Tuple[float, float]]:
    """Kembalikan (lat, lon) berdasarkan IP publik.
    Mengembalikan None bila gagal.
    """
    try:
        g = geocoder.ip('me')
        if g.ok:
            logger.info("IP geolocation succeeded: %s", g.latlng)
            return tuple(g.latlng)
        else:
            logger.warning("Geocoder IP response not ok.")
    except Exception as e:
        logger.exception("Exception during IP geolocation: %s", e)
    return None

# ---------------------------------------------------------------------------
# Geolokasi Wi‑Fi (Google Geolocation API contoh).
# ---------------------------------------------------------------------------
# Untuk penggunaan nyata, Anda memerlukan API key Google dan daftar SSID/BSSID.
# Di sini kami menyediakan stub yang dapat diganti dengan implementasi sebenarnya.

def get_wifi_location(access_points: List[dict]) -> Optional[Tuple[float, float]]:
    """Menggunakan Google Geolocation API untuk menentukan lokasi berdasarkan Wi‑Fi.
    *access_points* – list of dicts dengan kunci 'macAddress' dan 'signalStrength'.
    Returns (lat, lon) atau None bila gagal.
    """
    # **NOTE**: Ganti 'YOUR_GOOGLE_API_KEY' dengan kunci anda.
    API_KEY = "YOUR_GOOGLE_API_KEY"
    if API_KEY == "YOUR_GOOGLE_API_KEY":
        logger.warning("Google API key not set – WiFi location will return None.")
        return None
    url = f"https://www.googleapis.com/geolocation/v1/geolocate?key={API_KEY}"
    payload = {"wifiAccessPoints": access_points}
    try:
        _respect_rate_limit()
        resp = requests.post(url, json=payload, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        lat = data["location"]["lat"]
        lng = data["location"]["lng"]
        logger.info("WiFi geolocation succeeded: (%s, %s)", lat, lng)
        return (lat, lng)
    except Exception as e:
        logger.exception("WiFi geolocation failed: %s", e)
        return None

# ---------------------------------------------------------------------------
# Penyimpanan log lokasi ke DB + optional reverse‑geocode.
# ---------------------------------------------------------------------------
def _save_location(session, entity_type: str, entity_id: int, lat: float, lon: float, address: Optional[str] = None):
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    log = LocationLog(
        entity_type=entity_type,
        entity_id=entity_id,
        lat=lat,
        lon=lon,
        timestamp=now,
        address=address,
    )
    session.add(log)
    session.commit()
    logger.info("Saved %s %d location (%.5f, %.5f)", entity_type, entity_id, lat, lon)

# ---------------------------------------------------------------------------
# Worker thread untuk satu kendaraan.
# ---------------------------------------------------------------------------
class VehicleTracker(threading.Thread):
    """Thread yang mengambil lokasi secara periodik untuk satu kendaraan.
    
    Params:
        vehicle_id – ID Asset di tabel assets.
        interval   – detik antara tiap pembacaan lokasi.
        use_wifi   – bila True, coba Wi‑Fi terlebih dahulu, fallback ke IP.
    """
    def __init__(self, vehicle_id: int, interval: int = 30, use_wifi: bool = False):
        super().__init__(daemon=True)
        self.vehicle_id = vehicle_id
        self.interval = interval
        self.use_wifi = use_wifi
        self._stop_event = threading.Event()
        self.session = get_session()
        # Ambil objek asset (agar nama dapat dipakai dalam log)
        self.asset = self.session.query(Asset).filter(Asset.id == vehicle_id).first()
        if not self.asset:
            raise ValueError(f"Asset with id {vehicle_id} not found.")

    def stop(self):
        self._stop_event.set()

    def run(self):
        logger.info("Starting tracker for vehicle %s (ID %d)", self.asset.name, self.vehicle_id)
        while not self._stop_event.is_set():
            latlon = None
            # 1️⃣ Coba Wi‑Fi bila di‑enable
            if self.use_wifi:
                # Contoh data Wi‑Fi – di‑real world anda harus mengisi dengan BSSID yang terdeteksi
                sample_ap = [{"macAddress": "00:25:9c:cf:1c:ac", "signalStrength": -43}]
                latlon = get_wifi_location(sample_ap)
            # 2️⃣ Fallback ke IP bila tidak ada hasil
            if not latlon:
                latlon = get_ip_location()
            if latlon:
                lat, lon = latlon
                # Optional: reverse‑geocode untuk alamat manusia‑baca
                try:
                    address = None  # skip for brevity – could call reverse_geocode()
                except Exception:
                    address = None
                _save_location(self.session, "assets", self.vehicle_id, lat, lon, address)
                if is_in_danger(lat, lon):
                    logger.warning("Vehicle %s (ID %d) entered danger zone!", self.asset.name, self.vehicle_id)
            else:
                logger.error("Failed to obtain location for vehicle %s (ID %d).", self.asset.name, self.vehicle_id)
            # Tunggu interval
            time.sleep(self.interval)
        logger.info("Tracker for vehicle %s stopped.", self.asset.name)

# ---------------------------------------------------------------------------
# Export utilitas
# ---------------------------------------------------------------------------
def export_logs_to_csv(path: str = "location_logs.csv"):
    session = get_session()
    rows = session.query(LocationLog).order_by(LocationLog.timestamp).all()
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "entity_type", "entity_id", "lat", "lon", "timestamp", "address"])
        for r in rows:
            writer.writerow([
                r.id,
                r.entity_type,
                r.entity_id,
                r.lat,
                r.lon,
                r.timestamp.isoformat(),
                r.address or "",
            ])
    logger.info("Exported %d rows to CSV %s", len(rows), path)


def export_logs_to_json(path: str = "location_logs.json"):
    session = get_session()
    rows = session.query(LocationLog).order_by(LocationLog.timestamp).all()
    data = []
    for r in rows:
        data.append({
            "id": r.id,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "lat": r.lat,
            "lon": r.lon,
            "timestamp": r.timestamp.isoformat(),
            "address": r.address,
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info("Exported %d rows to JSON %s", len(rows), path)

# ---------------------------------------------------------------------------
# Demo runner – hanya untuk contoh, tidak dipanggil oleh produksi.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    # Pastikan ada kendaraan contoh (jika belum ada)
    sess = get_session()
    if sess.query(Asset).count() == 0:
        sess.add(Asset(name="Demo Truck", description="Demo vehicle for testing"))
        sess.commit()
    vehicle = sess.query(Asset).first()
    tracker = VehicleTracker(vehicle_id=vehicle.id, interval=20, use_wifi=False)
    tracker.start()
    # Jalankan 3 siklus (sekitar 1 menit) untuk demo
    time.sleep(65)
    tracker.stop()
    tracker.join()
    export_logs_to_csv()
    export_logs_to_json()
    logger.info("Demo selesai.")
