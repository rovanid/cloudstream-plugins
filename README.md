# Plugin ID untuk Cloudstream

Repo plugin Cloudstream yang dibuild otomatis (`.cs3` + `plugins.json`) oleh GitHub Actions,
lengkap dengan pemantauan domain tiap 6 jam (usulan domain baru masuk lewat Pull Request, bukan otomatis ke main).

## Cara pakai (sekali setup)

1. Buat repo **public** baru di GitHub, upload semua isi zip ini, push ke branch `main` atau `master`.
2. Edit `domains.yml` dengan domain situs yang sedang aktif.
3. Buka **Settings → Actions → General → Workflow permissions**, pilih **Read and write permissions**.
4. Buka tab **Actions → Build → Run workflow**. Setelah hijau, branch `builds` berisi semua `.cs3` dan `plugins.json`.
5. Di aplikasi Cloudstream: **Pengaturan → Ekstensi → Tambah repositori**, isi:
   `https://raw.githubusercontent.com/USERNAME/REPO/main/repo.json`
   (ganti `main` dengan `master` kalau itu nama branch Anda).

## Kelola plugin: cukup edit `domains.yml`

- **Update domain**: ganti URL di barisnya (atau merge PR dari domain-watch). `mainUrl` berubah dan `version` plugin naik otomatis (`bump_versions.py`).
- **Nonaktifkan plugin**: beri `#` di depan barisnya (`#NamaProvider: https://host`). Folder dan tuning manualnya dipertahankan, tetapi plugin tidak dibuild/dipublikasikan. Hapus `#` untuk mengaktifkan lagi.
- **Hapus plugin**: hapus barisnya sama sekali. Folder plugin ikut terhapus saat workflow jalan.
- **Versi otomatis**: `version` naik 1 bila `shared/kotlin`, kode plugin, `mainUrl`, atau selector berubah sejak build terakhir (hash di `plugin_hashes.json`; jangan diedit manual).
  Pengaman: kalau `domains.yml` kosong/rusak, tidak ada yang dihapus.
- **Tambah plugin / ganti ke domain baru**: unggah fixture HTML dulu, baru tambah/ubah barisnya (lihat "Tambah plugin baru"). Tanpa fixture, build gagal.

## Kategori beranda

Hanya kategori asli situs yang tampil, tanpa "Terbaru" otomatis. Daftarnya ada di `categories = listOf(...)`
pada `XxxProvider.kt` (path relatif, ikut domain baru). Kalau satu plugin tidak punya daftar sendiri,
`detect_selectors.py` hanya mengisi kategori dari menu situs di `list.html` (tanpa halaman indeks genre/kategori; belum diuji ke situs).
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

**Build (`build.yml`)**: `registry.py` (termasuk gerbang fixture) + tes → `sync_plugins.py` → `apply_domains.py` → `generate_json.py repo`
→ `detect_selectors.py` → commit → Gradle build → `generate_json.py plugins` (validasi) → publish ke branch `builds`.

**Pantau domain (`domain-watch.yml`, tiap 6 jam)**: `check_domains.py` memeriksa tiap domain (retry, kata kunci per plugin
di `domain_keywords.yml`). Jika situs pindah ke origin baru, origin itu diverifikasi langsung (https, HTTP 200, kata kunci ada,
host unik, dan fixture HTML domain baru sudah ada), tes dijalankan, lalu workflow membuka/memperbarui satu PR `auto/domain-update`. **Anda yang me-merge.**
Domain mati/diblokir/parkir, atau pindah domain yang fixture-nya belum ada (`NEEDS_FIXTURE`), hanya dilaporkan di Actions summary; `domains.yml` tidak diubah.
Prasyarat: Settings → Actions → General → centang "Allow GitHub Actions to create and approve pull requests".

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

## Tambah plugin baru (fixture dulu)

1. **Unggah fixture HTML asli** ke `tests/kotlin/fixtures/NamaBaruProvider/`: `list.html`, `detail.html`,
   `episode.html` (simpan halaman dari browser; format MHTML Chrome didukung).
2. **Tambah satu baris** di `domains.yml`: `NamaBaruProvider: https://situsbaru.tld`
   (nama harus huruf/angka dan berakhiran `Provider`). Opsional, untuk situs film/serial tulis
   `NamaBaruProvider: movie` di `plugin_types.yml` (default: `anime`).
3. **Push.** `registry.py` memvalidasi: kalau fixture belum ada/lengkap, bukan HTML, atau berasal dari domain
   lain, penambahan ditolak dan build gagal sebelum apa pun dibuat. Kalau lolos, `sync_plugins.py` membuat
   foldernya dari `.github/templates/` dan `detect_selectors.py` menulis `Selectors.kt` dari fixture.
4. Plugin baru berstatus Beta-only. Cek `detection_report.md`, lalu ubah `status = 1` di `build.gradle.kts`
   kalau hasilnya sudah baik.

## Selectors.kt otomatis dari fixture

`detect_selectors.py` membaca fixture HTML (bukan situs) dan mengisi `Selectors.kt`: daftar item, judul,
pencarian, pagination, kategori beranda, deskripsi, genre, episode, pemutar. Ringkasannya di `detection_report.md`.

- Jalan untuk plugin baru dan ulang otomatis hanya bila isi fixture berubah. Run manual `build.yml` dari tab
  Actions memaksa deteksi ulang semua.
- Hasil diuji balik pada fixture. Daftar item tak terdeteksi/tak valid = build gagal. Bagian lain yang tidak
  ada buktinya di HTML dikosongkan (❌) dan dilengkapi bawaan runtime; tidak ada tebakan.
- Untuk mengunci dan edit manual: hapus baris `// @auto-detect` di baris pertama `Selectors.kt`.
- Batas: daftar yang dimuat lewat JavaScript tidak ikut tersimpan di HTML, jadi tidak terdeteksi. Kotak
  pencarian tanpa `<form>` (digerakkan JS) tidak bisa diketahui URL-nya. Pemutar yang dimuat lewat AJAX/token
  tidak ada di `episode.html`. Semuanya muncul sebagai ❌ dan perlu disetel manual.

## Catatan

- Jangan ubah format baris `override var mainUrl = "..."`, karena dibaca `apply_domains.py`.
- Kode di `shared/kotlin` ikut dikompilasi ke setiap plugin lewat `build.gradle.kts` root.
