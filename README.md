# Plugin ID untuk Cloudstream

Repo plugin Cloudstream yang dibuild otomatis (`.cs3` + `plugins.json`) oleh GitHub Actions,
lengkap dengan deteksi domain baru tiap 6 jam.

## Cara pakai (sekali setup)

1. Buat repo **public** baru di GitHub, upload semua isi zip ini, push ke branch `main` atau `master`.
2. Edit `domains.yml` dengan domain situs yang sedang aktif.
3. Buka **Settings → Actions → General → Workflow permissions**, pilih **Read and write permissions**.
4. Buka tab **Actions → Build → Run workflow**. Setelah hijau, branch `builds` berisi semua `.cs3` dan `plugins.json`.
5. Di aplikasi Cloudstream: **Pengaturan → Ekstensi → Tambah repositori**, isi:
   `https://raw.githubusercontent.com/USERNAME/REPO/main/repo.json`
   (ganti `main` dengan `master` kalau itu nama branch Anda).

## Kelola plugin: cukup edit `domains.yml`

- **Update domain**: ganti URL di barisnya. `mainUrl` dan `version` plugin naik otomatis.
- **Hapus plugin**: hapus barisnya (atau beri `#` di depan). Folder plugin ikut terhapus saat workflow jalan.
  Pengaman: kalau `domains.yml` kosong/rusak, tidak ada yang dihapus.
- **Tambah plugin**: tambah baris baru (lihat bagian "Tambah plugin baru").

## Kategori beranda

Hanya kategori asli situs yang tampil, tanpa "Terbaru" otomatis. Daftarnya ada di `categories = listOf(...)`
pada `XxxProvider.kt` (path relatif, ikut domain baru). Kalau satu plugin tidak punya daftar sendiri,
`detect_selectors.py` hanya mengisi kategori dari menu situs yang terbukti berisi daftar item.
Kalau tetap kosong, aplikasi menampilkan satu entri "Beranda" supaya plugin tidak kosong.

## Pemutar (`loadLinks`)

Urutan: `<video>` di halaman → semua embed (iframe, mirror, atribut `data-*`, base64) lewat extractor
bawaan CloudStream → kalau host tidak dikenal: buka halaman embed, cari `.m3u8/.mp4` (termasuk JS yang
di-pack) dan ikuti iframe bersarang → tombol "Nonton" yang membuka halaman pemutar lain → URL embed di dalam script.
Tiap langkah dibungkus try/catch, jadi satu host rusak tidak menggagalkan yang lain.

Jika semuanya gagal, mesin memuat halaman di WebView tersembunyi dan menangkap request `.m3u8/.mp4`
(untuk pemutar yang dirender JavaScript), lalu melempar error berisi jejak diagnosis dan menulisnya ke
logcat dengan tag `AdaptiveProvider`.

## Uji pemutaran berkala (`health.yml`)

Tiap 12 jam `check_playback.py` menelusuri kategori → item → episode → embed → URL video, lalu memverifikasi
playlist `.m3u8` (termasuk segmen pertama) atau `.mp4`. Hasil di `playback_report.md`; workflow merah bila
ada plugin ❌ FAIL. URL situs yang berganti/tidak terjangkau dikecualikan (🔁), begitu juga situs yang
memblokir bot atau memuat daftar lewat JavaScript (⏸️). Kategori yang tidak memuat daftar ikut dilaporkan.
Isi `AUTO_STATUS: "1"` di `health.yml` kalau status Down/Ok mau diubah otomatis setelah 2x FAIL berturut-turut.
Catatan: uji ini tidak menjalankan plugin sungguhan, hanya meniru alurnya dari CI.

## Alur otomatis

`check_domains.py` cek domain & redirect → `domains.yml` diperbarui → `sync_plugins.py` membuat/menghapus
folder plugin → `apply_domains.py`
mengganti `mainUrl` di Kotlin dan menaikkan `version` → `generate_json.py repo` menulis
`repo.json` → Gradle build → `generate_json.py plugins` melengkapi dan **memvalidasi**
`plugins.json` → publish ke branch `builds`.

## Pembuat JSON (`generate_json.py`)

- `repo.json` dibuat otomatis dari `GITHUB_REPOSITORY`, jadi tidak ada lagi nama repo yang
  tertulis manual. Format: `name`, `description`, `manifestVersion: 1`, `pluginLists`.
- `plugins.json` berasal dari Gradle (`makePluginsJson`), lalu dilengkapi `iconUrl` (favicon
  dari `domains.yml`), `fileSize` asli, `version`/`status`/`tvTypes`/`language` dari
  `build.gradle.kts`, dan `repositoryUrl`.
- Validasi sebelum publish: field wajib, tipe data, `status` 0–3, `tvTypes` harus nama
  `TvType` CloudStream yang sah, URL `https` berakhiran `.cs3`, dan file `.cs3` harus ada serta
  tidak kosong. Kalau ada yang rusak, workflow gagal dan JSON lama di branch `builds` tetap utuh.
- Jalankan lokal: `GITHUB_REPOSITORY=user/repo python3 .github/scripts/generate_json.py plugins --builds-dir <folder .cs3>`

## Mesin scraper bersama (`shared/kotlin`)

Semua plugin memakai `AdaptiveProvider`. Selector di `Selectors.kt` dan `SiteConfig` hanyalah
**kandidat**. Saat dijalankan di aplikasi (IP perangkat Anda, dengan `CloudflareKiller`), mesin
mencoba berurutan: hasil auto-detect → tuning manual (`extra*`) → selector bawaan → heuristik
struktur halaman, lalu memakai yang menghasilkan data valid. Selector yang salah tidak lagi
membuat daftar kosong, dan kartu yang menaut ke beranda/kategori/iklan otomatis dibuang.

Tuning khusus situs ditulis di bagian `SiteConfig(...)` pada `XxxProvider.kt` (tidak ditimpa script).

## Tambah plugin baru (otomatis)

1. Tambah satu baris di `domains.yml`: `NamaBaruProvider: https://situsbaru.tld`
   (nama harus huruf/angka dan berakhiran `Provider`).
2. Opsional, untuk situs film/serial tulis `NamaBaruProvider: movie` di `plugin_types.yml`
   (default: `anime`).
3. Push. `sync_plugins.py` membuat foldernya dari `.github/templates/`, lalu workflow membuild dan mempublikasikannya.
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
- Kode di `shared/kotlin` ikut dikompilasi ke setiap plugin lewat `build.gradle.kts` root.
