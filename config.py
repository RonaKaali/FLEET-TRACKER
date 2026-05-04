# config.py
# ------------------------------------------------------------
# Pengaturan aplikasi – ubah nilai di sini bila diperlukan.
# ------------------------------------------------------------

# URL layanan reverse‑geocoding (OpenStreetMap Nominatim)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

# Header yang diminta Nominatim (sangat penting, agar tidak diblokir)
USER_AGENT = "FleetManagerApp/1.0 (your_email@example.com)"

# Jeda antar panggilan API (ms) – hindari limit rate Nominatim
API_DELAY_MS = 1000

# Daftar zona “danger” (contoh: area pabrik atau lokasi yang tidak boleh diakses)
# Format: (latitude, longitude, radius_km)
DANGER_ZONES = [
    # (lat, lon, radius_km)
    (-6.200000, 106.816666, 2.0),   # contoh zona Jakarta pusat
]

# Batas waktu (detik) untuk menganggap data lokasi "stale" (tidak terpilih)
STALE_SECONDS = 300

# ---------- Wi‑Fi Geolocation (Opsional) ----------
# Google Geolocation API endpoint – memerlukan API key.
# Jika Anda tidak memiliki key, fungsi get_location_by_wifi() akan mengembalikan None
# dan menuliskan peringatan pada log.
GOOGLE_GEO_API_URL = "https://www.googleapis.com/geolocation/v1/geolocate"
GOOGLE_GEO_API_KEY = "YOUR_GOOGLE_API_KEY_HERE"  # <-- Ganti dengan key Anda

# Interval (detik) antara scan Wi‑Fi untuk pelacakan real‑time
WIFI_SCAN_INTERVAL = 30

# Jumlah percobaan ulang saat panggilan API gagal
MAX_RETRIES = 3

# Waktu tunggu (detik) antar percobaan ulang
RETRY_BACKOFF = 5
# ------------------------------------------------------------
