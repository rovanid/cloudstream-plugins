# Laporan deteksi selector

Dibuat otomatis oleh `detect_selectors.py` dari fixture HTML nyata (tanpa akses situs). ❌ = tidak ada buktinya di HTML; runtime memakai selector bawaan/heuristik. Kategori diambil dari menu situs dan belum diuji ke situs.

| Plugin | Fixture | Item | Judul | Cari | Halaman | Kategori | Deskripsi | Genre | Episode | Pemutar |
|---|---|---|---|---|---|---|---|---|---|---|
| LayarKaca21Provider | 900a1766 | ✅ | ✅ | ✅ | ✅ | 8 | ✅ | ❌ | ❌ | ✅ |

Tidak diproses / gagal:

- **AnimeSailProvider**: dikunci manual

Peringatan:

- **LayarKaca21Provider**: ITEM 'li.slider' juga cocok dengan 12 kartu di luar daftar utama (mis. tab trending/sidebar); dipertahankan karena selector lebih spesifik rapuh antar halaman
- **LayarKaca21Provider**: daftar episode tidak ditemukan di detail.html (wajar untuk situs film)
