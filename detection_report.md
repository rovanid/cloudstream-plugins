# Laporan deteksi selector

Dibuat otomatis oleh `detect_selectors.py` dari fixture HTML nyata (tanpa akses situs). ❌ = tidak ada buktinya di HTML; runtime memakai selector bawaan/heuristik. Kategori diambil dari menu situs dan belum diuji ke situs.

| Plugin | Fixture | Item | Judul | Cari | Halaman | Kategori | Deskripsi | Genre | Episode | Pemutar |
|---|---|---|---|---|---|---|---|---|---|---|
| MyFlixerProvider | 70a971e4 | ✅ | ✅ | ✅ | ❌ | 8 | ✅ | ❌ | ❌ | ✅ |

Tidak diproses / gagal:

- **AnimeSailProvider**: dikunci manual

Peringatan:

- **MyFlixerProvider**: ITEM 'div.flw-item' juga cocok dengan 48 kartu di luar daftar utama (mis. tab trending/sidebar); dipertahankan karena selector lebih spesifik rapuh antar halaman
- **MyFlixerProvider**: daftar episode tidak ditemukan di detail.html (wajar untuk situs film)
- **MyFlixerProvider**: tautan halaman berikutnya tidak ada di list.html; pagination dimatikan
