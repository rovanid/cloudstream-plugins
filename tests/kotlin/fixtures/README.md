# Fixture HTML

Simpan halaman asli dari browser ke sini (Chrome Android: menu ⋮ → Unduh halaman, atau
`view-source:` lalu salin). Tiga file per situs:

- `<Provider>/list.html` — halaman daftar/beranda yang menampilkan kartu anime/film
- `<Provider>/detail.html` — halaman satu judul (ada daftar episode)
- `<Provider>/episode.html` — halaman satu episode (ada pemutar/iframe)

Fixture yang belum ada membuat tesnya dilewati, bukan gagal.

## Selectors.kt terisi otomatis dari fixture

Kalau `<Provider>/list.html` ada, `detect_selectors.py` (dijalankan `build.yml`) membaca selector dari
fixture ini, bukan dari situs langsung, lalu menulis `Selectors.kt` dan meng-commit-nya. Fixture baru
atau berubah otomatis memicu deteksi ulang. Format MHTML dari Chrome "Simpan halaman" sudah didukung.
Hapus baris `// @auto-detect` di `Selectors.kt` untuk mengunci dan mengedit manual.
