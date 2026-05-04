# safety.py
# ------------------------------------------------------------
# Logika keselamatan karyawan & aset.
#   • memeriksa apakah posisi berada dalam radius zona bahaya.
#   • menghitung jarak haversine.
# ------------------------------------------------------------
import math
from config import DANGER_ZONES, STALE_SECONDS
from datetime import datetime, timezone

def haversine(lat1, lon1, lat2, lon2):
    """
    Menghitung jarak (km) antara dua titik koordinat.
    Formula Haversine.
    """
    R = 6371.0  # radius Bumi km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def is_in_danger(lat, lon):
    """
    Mengembalikan True bila koordinat berada dalam
    radius salah satu DANGER_ZONES.
    """
    for dz_lat, dz_lon, radius in DANGER_ZONES:
        if haversine(lat, lon, dz_lat, dz_lon) <= radius:
            return True
    return False

def is_location_stale(timestamp):
    """
    Memeriksa apakah data lokasi sudah lama (> STALE_SECONDS).
    timestamp harus tipe datetime (aware/naive – diasumsikan UTC).
    """
    now = datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    delta = (now - timestamp).total_seconds()
    return delta > STALE_SECONDS
