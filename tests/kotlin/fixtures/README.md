# Fixture HTML (wajib, sumber Selectors.kt)

Simpan halaman asli dari browser ke sini (Chrome Android: menu ⋮ → Unduh halaman, atau
`view-source:` lalu salin). Tiga file per situs:

- `<Provider>/list.html` — halaman daftar/beranda yang menampilkan kartu anime/film
- `<Provider>/detail.html` — halaman satu judul (ada daftar episode)
- `<Provider>/episode.html` — halaman satu episode (ada pemutar/iframe)

## Urutan kerja (fixture dulu)

1. **Unggah fixture** ke `tests/kotlin/fixtures/<NamaProvider>/` (tiga file di atas).
2. **Tambahkan URL/domain** di `domains.yml`: `NamaProvider: https://domain`.
3. **Validasi otomatis** (`registry.py`, langkah pertama `build.yml` dan `pr-check.yml`). Baris ditolak dan
   build GAGAL bila:
   - salah satu dari tiga file belum ada;
   - file kosong / terlalu kecil / bukan HTML;
   - file berasal dari domain lain. Host asal dibaca dari header `Snapshot-Content-Location` (MHTML
     Chrome "Simpan halaman"), lalu `<link rel=canonical>` / `og:url`; kalau tidak ada petunjuk sama sekali,
     nama host harus muncul di isi HTML. `www.` diabaikan; subdomain berbeda dianggap domain berbeda.
4. **`Selectors.kt` dibuat otomatis** oleh `detect_selectors.py` dari struktur HTML fixture (tanpa mengakses
   situs): daftar item, judul, pagination (tautan "berikutnya"), pencarian (`<form>` GET), kategori (menu),
   deskripsi, genre, episode, pemutar. Hasilnya diuji balik pada fixture; daftar item yang tidak valid
   membuat build gagal. Bagian yang tidak ada buktinya di HTML dikosongkan (❌ di `detection_report.md`)
   dan diisi bawaan oleh runtime. Tidak ada tebakan.

Entri yang di-`#` (nonaktif) tidak butuh fixture. Mengganti URL plugin yang sudah ada ke domain baru juga
butuh fixture dari domain baru; usulan `domain-watch` yang fixture-nya belum ada hanya dilaporkan.

## Deteksi ulang

Isi fixture berubah (sidik jari di baris pertama `Selectors.kt`) → `Selectors.kt` dibuat ulang otomatis.
Paksa ulang: jalankan `build.yml` manual dari tab Actions. Hapus baris `// @auto-detect` di `Selectors.kt`
untuk mengunci dan mengedit manual (plugin tetap wajib punya fixture).

Format MHTML dari Chrome "Simpan halaman" didukung. Tes Kotlin (`SelectorFixtureTest`) menguji selector
di `Selectors.kt` terhadap fixture yang sama.
