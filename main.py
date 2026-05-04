# main.py
"""
Entry point for Fleet Manager application.
- Inisialisasi database (SQLite) dan menambah data contoh bila kosong.
- Mengambil lokasi terkini berdasar IP (geocoder).
- Memperbaharui posisi setiap karyawan & aset, menyimpan log, dan menampilkan peringatan bila berada dalam zona bahaya.
- Memeriksa apakah ada log yang sudah usang.
"""

import sys
from datetime import datetime, timezone

from models import init_db, get_session, Employee, Asset, LocationLog
from geoutil import get_location_by_ip, reverse_geocode
from safety import is_in_danger, is_location_stale


def add_sample_data(session):
    """Masukkan contoh data bila belum ada."""
    if session.query(Employee).count() == 0:
        emp = Employee(name="Budi Santoso", health_status="aktif")
        session.add(emp)
    if session.query(Asset).count() == 0:
        asset = Asset(name="Truck #12", description="Truck pengangkut bahan baku")
        session.add(asset)
    session.commit()


def update_entity_location(session, entity, lat, lon):
    """Perbaharui koordinat entity (karyawan atau aset), simpan log, dan cek keselamatan."""
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    # Update entity
    entity.lat = lat
    entity.lon = lon
    if hasattr(entity, "last_seen"):
        entity.last_seen = now
    if hasattr(entity, "last_update"):
        entity.last_update = now
    # Simpan log
    address = reverse_geocode(lat, lon)
    log = LocationLog(
        entity_type=entity.__tablename__,
        entity_id=entity.id,
        lat=lat,
        lon=lon,
        timestamp=now,
        address=address,
    )
    session.add(log)
    session.commit()
    # Peringatan keselamatan
    if is_in_danger(lat, lon):
        print(f"[!!!] {entity.__class__.__name__} '{entity.name}' berada dalam zona bahaya!")
    else:
        print(f"[OK] {entity.__class__.__name__} '{entity.name}' berada di lokasi aman.")
    if address:
        print(f"   → Alamat: {address}")


def main():
    print("=== Fleet Manager – Inisialisasi DB ===")
    init_db()
    session = get_session()
    add_sample_data(session)
    # Dapatkan lokasi IP saat ini
    try:
        lat, lon = get_location_by_ip()
        print(f"Lokasi IP terdeteksi: ({lat:.5f}, {lon:.5f})")
    except Exception as e:
        print(f"Gagal memperoleh lokasi IP: {e}")
        sys.exit(1)
    # Update semua karyawan & aset
    for emp in session.query(Employee).all():
        update_entity_location(session, emp, lat, lon)
    for asset in session.query(Asset).all():
        update_entity_location(session, asset, lat, lon)
    # Cek log usang
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    stale_logs = session.query(LocationLog).filter(LocationLog.timestamp < now).all()
    for log in stale_logs:
        if is_location_stale(log.timestamp):
            print(
                f"[WARNING] Log {log.id} untuk {log.entity_type} {log.entity_id} "
                f"telah usang (lebih dari {STALE_SECONDS}s)."
            )
    print("\n=== Selesai. Data tersimpan di 'fleet.db' ===")

if __name__ == "__main__":
    main()
