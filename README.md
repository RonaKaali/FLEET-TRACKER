# 🚚 FleetCommand Enterprise (v1.0.1)

**FleetCommand Enterprise** adalah sistem pelacakan aset dan armada logistik berbasis web yang dirancang untuk pemantauan real-time dengan tingkat akurasi tinggi. Aplikasi ini memungkinkan manajer armada untuk melacak kendaraan atau personel langsung di peta interaktif hanya melalui sebuah tautan (link).

![Fleet Tracker Dashboard](https://raw.githubusercontent.com/RonaKaali/FLEET-TRACKER/master/static/preview.png) *(Catatan: Tambahkan screenshot Anda di sini)*

## ✨ Fitur Utama

-   **📍 Pelacakan Live via Link (Broadcast)**: Target (kurir/driver) cukup membuka link di browser HP mereka untuk mulai berbagi lokasi GPS secara real-time tanpa perlu instalasi aplikasi.
-   **🗺️ Dashboard Peta Interaktif**: Visualisasi posisi aset secara live menggunakan Leaflet.js dengan fitur *auto-focus* dan *zoom*.
-   **📊 Manajemen Target Dinamis**: Tambah, hapus, dan kelola target pelacakan langsung dari dashboard UI.
-   **📑 Riwayat Aktivitas & Ekspor**: Rekaman perjalanan otomatis yang dapat diekspor ke format **CSV** dan **JSON** untuk audit dan laporan kerja.
-   **🌐 Antarmuka Premium (Bento Grid)**: Desain modern berbasis *glassmorphism* yang responsif dan elegan.
-   **🇮🇩 Full Bahasa Indonesia**: Seluruh antarmuka dan laporan menggunakan Bahasa Indonesia dan zona waktu lokal (WITA/UTC+8).

## 🛠️ Teknologi yang Digunakan

-   **Backend**: Python, FastAPI
-   **Database**: SQLite (SQLAlchemy)
-   **Frontend**: HTML5, CSS3 (Glassmorphism), JavaScript (Leaflet.js)
-   **Geolokasi**: IP Geolocation & Browser Geolocation API

## 🚀 Cara Menjalankan Secara Lokal

1.  **Clone Repository**:
    ```bash
    git clone https://github.com/RonaKaali/FLEET-TRACKER.git
    cd FLEET-TRACKER
    ```

2.  **Instal Dependensi**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Jalankan Server**:
    ```bash
    python web_server.py
    ```

4.  **Akses Dashboard**:
    Buka `http://localhost:8000` di browser Anda.

## 📡 Cara Melacak Seseorang

1.  Buka dashboard utama, salin **Link Broadcast** yang tersedia di panel kanan.
2.  Kirimkan link tersebut ke target (misal: Jackson).
3.  Target membuka link, memasukkan nama, dan menekan **"Mulai Berbagi Lokasi"**.
4.  Posisi target akan langsung muncul dan bergerak di peta dashboard Anda secara otomatis.

---
*Dibuat dengan ❤️ untuk Jennifer & Keluarga. FleetCommand Enterprise membantu mengamankan operasional logistik Anda.*
