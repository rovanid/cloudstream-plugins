# Plugin ID untuk Cloudstream

Repo plugin Cloudstream yang dibuild otomatis (`.cs3` + `plugins.json`) oleh GitHub Actions,
lengkap dengan deteksi domain baru tiap 6 jam.

## Cara pakai (sekali setup)

1. Buat repo **public** baru di GitHub, upload semua isi zip ini, push ke branch `main` atau `master`.
2. Edit `domains.yml` (dan `candidates.yml`) dengan domain situs yang sedang aktif.
3. Buka **Settings → Actions → General → Workflow permissions**, pilih **Read and write permissions**.
4. Buka tab **Actions → Build → Run workflow**. Setelah hijau, branch `builds` berisi semua `.cs3` dan `plugins.json`.
5. Di aplikasi Cloudstream: **Pengaturan → Ekstensi → Tambah repositori**, isi:
   `https://raw.githubusercontent.com/USERNAME/REPO/main/repo.json`
   (ganti `main` dengan `master` kalau itu nama branch Anda).

## Alur otomatis

`check_domains.py` cek domain & redirect → `domains.yml` diperbarui → `apply_domains.py`
mengganti `mainUrl` di Kotlin dan menaikkan `version` → Gradle build → publish ke branch `builds`.

## Tambah plugin baru (otomatis)

1. Tambah satu baris di `domains.yml`: `NamaBaruProvider: https://situsbaru.tld`
   (nama harus huruf/angka dan berakhiran `Provider`).
2. Opsional, untuk situs film/serial tulis `NamaBaruProvider: movie` di `plugin_types.yml`
   (default: `anime`).
3. Push. Workflow membuat foldernya dari `.github/templates/`, membuild, dan mempublikasikannya.
4. Plugin baru berstatus Beta-only dan selector-nya dideteksi otomatis. Cek `detection_report.md`,
   lalu ubah `status = 1` di `build.gradle.kts` kalau hasilnya sudah baik.

## Deteksi selector otomatis

`detect_selectors.py` mengambil HTML tiap situs dan mengisi `Selectors.kt` (daftar item, judul,
pencarian, pagination, kategori beranda, deskripsi, genre, episode, pemutar). Hasilnya
ringkas di `detection_report.md`.

- Jalan otomatis untuk plugin baru dan diulang tiap 7 hari. Run manual dari tab Actions
  memaksa deteksi ulang semua.
- Hasil yang skornya lebih rendah dari sebelumnya tidak menimpa hasil lama.
- Untuk mengunci dan edit manual: hapus baris `// @auto-detect` di baris pertama `Selectors.kt`.
- Tidak bisa dideteksi: situs yang memblokir bot (Cloudflare, sering terjadi pada IP GitHub),
  situs yang memuat daftar lewat JavaScript, dan pemutar yang dimuat lewat AJAX/token.
  Kasus ini muncul sebagai ❌ di laporan dan perlu disetel manual.

## Catatan

- Jangan ubah format baris `override var mainUrl = "..."`, karena dibaca `apply_domains.py`.
