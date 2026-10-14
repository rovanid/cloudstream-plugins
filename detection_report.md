# Laporan deteksi selector

Dibuat otomatis oleh `detect_selectors.py` dari fixture HTML nyata (tanpa akses situs). ❌ = tidak ada buktinya di HTML; runtime memakai selector bawaan/heuristik. Kategori diambil dari menu situs dan belum diuji ke situs.

| Plugin | Fixture | Item | Judul | Cari | Halaman | Kategori | Deskripsi | Genre | Episode | Pemutar |
|---|---|---|---|---|---|---|---|---|---|---|
| SflixProvider | 49318b44 | ✅ | ✅ | ❌ | ❌ | 8 | ✅ | ❌ | ❌ | ✅ |

Tidak diproses / gagal:

- **AnimeSailProvider**: dikunci manual

Peringatan:

- **SflixProvider**: daftar episode tidak ditemukan di detail.html (wajar untuk situs film)
- **SflixProvider**: pencarian tidak terdeteksi (tidak ada <form> GET pencarian di list.html); runtime mencoba pola bawaan
- **SflixProvider**: tautan halaman berikutnya tidak ada di list.html; pagination dimatikan
