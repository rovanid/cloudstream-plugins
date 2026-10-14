# Audit repo (berdasarkan kode di zip, 14 Okt 2026)

Alur aktual: `domains.yml` → `check_domains.py` → `sync_plugins.py` → `apply_domains.py` → `generate_json.py repo`
→ `detect_selectors.py` → commit ke main → Gradle build → `generate_json.py plugins` → force-push ke branch `builds`.
Parser: satu mesin generik `shared/kotlin/.../AdaptiveProvider.kt` (992 baris) + `Selectors.kt`/`SiteConfig` per plugin.
Cloudflare: tidak dipakai di infrastruktur proyek (hanya `CloudflareKiller` di app untuk menembus proteksi situs sumber).
Repo tambahan: tidak diperlukan oleh audit ini (lihat bagian akhir).

## Status sumber saat ini (dari laporan di repo, bukan dari pengujian saya)
| Sumber | Deteksi selector | Uji pemutaran CI | status di gradle |
|---|---|---|---|
| AnimeSail | gagal (diblokir bot) | BLOCKED | 1 (Ok) |
| Kuronime | sebagian (cari ❌, halaman ❌, genre ❌, pemutar ❌) | PARTIAL | 3 (Beta) |
| LayarKaca21 | gagal (diblokir bot) | BLOCKED | 1 (Ok) |
Kesimpulan: **tidak ada satu pun sumber yang playback-nya terverifikasi.** AnimeSail dan LayarKaca21 berstatus "Ok" tanpa bukti.

## Temuan (urut prioritas)
1. **Domain redirect diadopsi otomatis tanpa review/tes** (`check_domains.py`): syarat hanya kata kunci nama folder ada di
   halaman, lalu `domains.yml` ditulis ulang dan di-push ke main. Situs/ domain parkir yang memuat kata itu bisa mengalihkan
   semua pengguna ke host baru. Risiko supply-chain.
2. **Kata kunci domain salah untuk sumber nyata**: keyword = nama folder tanpa "Provider" ("AnimeSail", "LayarKaca21"), padahal
   domain aktif `anisail.com` dan `lk21official.cc`; sangat mungkin dinilai "MATI" meski sehat. Tidak ada retry, tidak ada riwayat.
3. **Versi plugin tidak naik saat kode bersama berubah**: `apply_domains.py` hanya menaikkan `version` bila `mainUrl` berubah.
   Perbaikan di `AdaptiveProvider.kt` tidak sampai ke pengguna karena Cloudstream membandingkan `version`.
4. **Menonaktifkan = menghapus**: memberi `#` pada baris membuat `sync_plugins.py` menghapus folder, termasuk tuning `SiteConfig`
   manual (mis. kategori dan selector AnimeSail). Tidak ada status DISABLED sungguhan.
5. **Registry tanpa validasi**: nama ganda diam-diam menimpa, baris tanpa `:` diabaikan, host ganda tidak terdeteksi. (DIPERBAIKI di tahap 1.)
6. **Tidak ada quality gate**: tidak ada tes parser/fixture; build dan publish jalan walau health merah; publish memakai
   `git push --force` dengan `--amend` sehingga **tidak ada riwayat/rollback**; tidak ada release/prerelease.
7. **Monitoring tanpa notifikasi**: `health.yml` hanya menandai workflow merah. Tidak ada issue/Telegram/Discord, deduplikasi,
   cooldown, notifikasi pulih, atau riwayat per domain (state hanya `fails` dan `last`). Metadata yang hilang, jumlah episode
   berubah, dan server hilang tidak dipantau.
8. **Race commit ke main**: `build.yml` dan `health.yml` sama-sama push ke main dalam concurrency group berbeda;
   `health.yml` memakai `git pull --rebase || true` dan `git push || true`, sehingga kegagalan simpan laporan tersembunyi.
9. **Metadata Cloudstream belum lengkap** di `load()`: tidak ada rating, backdrop (`backgroundPosterUrl`), status tayang,
   judul alternatif, season; `year` hanya dari "(2024)" di judul; episode selalu `DubStatus.Subbed`; hasil pencarian selalu
   bertipe Anime (film tidak dibedakan). Tidak ada data yang dikarang, tetapi banyak yang tersedia di situs belum diambil.
10. **Playback**: alur bertingkat cukup defensif (extractor bawaan → halaman embed → iframe bersarang → WebView sniff) dan
    HLS dikirim sebagai satu stream adaptif (tidak membuat resolusi palsu). Namun `emitDirect` menganggap URL ditemukan = sukses;
    kualitas mp4 ditebak dari teks URL/label, selain itu `Unknown`. `check_playback.py` hanya meniru alur dan tidak bisa
    membuktikan pemutaran Android.
11. **Build tidak reproducible**: `cloudstream3:pre-release` dan `recloudstream/gradle:master-SNAPSHOT` tidak dipatok; versi Kotlin
    `2.4.0` di root `build.gradle.kts` belum bisa saya verifikasi tanpa jaringan.

## Batasan lingkungan audit ini
Jaringan sandbox dimatikan: tidak ada situs yang bisa dibuka, build Gradle tidak bisa dijalankan, dan Kotlin tidak dikompilasi.
Semua yang di bawah "diuji" hanya mencakup skrip Python offline.

## Repo tambahan?
Tidak perlu. Satu repo public sudah memuat registry, parser, build, dan distribusi. Monitoring cukup GitHub Actions + Issues
(+ secret Telegram/Discord opsional). Repo private baru hanya berguna bila Anda ingin menyimpan riwayat monitoring di luar repo
publik; ini opsional dan tidak saya buat.

## Status tahap
- Tahap 1 (validasi registry): SELESAI. `.github/scripts/registry.py`, `tests/test_registry.py`.
- Tahap 2 (temuan 1 dan 2): SELESAI di kode, 14 Okt 2026. `check_domains.py` hanya mengusulkan, `domain-watch.yml` membuat PR,
  `domain_keywords.yml` memberi keyword per plugin, ada retry. Belum pernah dijalankan di GitHub Actions (butuh jaringan dan izin PR).
- Tahap 3 dst: BELUM.

## Tahap berikutnya (usulan urutan)
2. Ganti adopsi redirect otomatis dengan **Pull Request** + tes, dan keyword per domain.
3. Naikkan `version` otomatis saat `shared/` berubah; status DISABLED yang tidak menghapus folder.
4. Parser test dengan fixture HTML (Python/Kotlin) + metadata (rating, backdrop, status, judul alternatif, season).
5. Monitoring per domain (HEALTHY/DEGRADED/BROKEN/UNVERIFIED/DISABLED) + GitHub Issue dengan dedup/cooldown/pulih.
6. Publikasi bertahap: prerelease dulu, stabil hanya bila gate lolos; simpan riwayat build untuk rollback.
