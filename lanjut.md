# lanjut.md — dokumen utama kesinambungan proyek

Diperbarui: 14 Okt 2026. Dokumen ini adalah SUMBER UTAMA. `PROJECT_STATE.md` (status fitur) dan `NEXT_STEPS.md` (tugas) melengkapinya; `docs/AUDIT.md` berisi temuan audit.

## 1. Proyek
Repo plugin CloudStream (`rovanid/cloudstream-plugins`, dari `repo.json`) untuk sumber anime/film berbahasa Indonesia. Sasaran: domain di `domains.yml` dikelola otomatis dan aman; metadata dan pemutaran video benar; ada pemantauan, notifikasi, dan CI/CD.

## 2. File penting
- `domains.yml` registry (format `NamaProvider: https://host`), `plugin_types.yml` (anime|movie), `domain_keywords.yml` (keyword per plugin)
- `.github/scripts/`: `registry.py` (validator), `check_domains.py` (pemantau, hanya mengusulkan), `sync_plugins.py`, `apply_domains.py`, `generate_json.py`, `detect_selectors.py`, `check_playback.py`
- `.github/workflows/`: `build.yml`, `health.yml`, `domain-watch.yml`, `pr-check.yml`
- `shared/kotlin/com/cloudstreamid/common/AdaptiveProvider.kt` (mesin parser generik, 992 baris) dan `SiteConfig.kt`
- Plugin: `AnimeSailProvider/`, `KuronimeProvider/`, `LayarKaca21Provider/` (masing-masing `Selectors.kt`, `*Provider.kt`, `*Plugin.kt`, `build.gradle.kts`)
- `tests/` (Python unittest), laporan: `detection_report.md`, `playback_report.md`, `playback_state.json`

## 3. Alur
`domains.yml` → `registry.py` (gerbang) → `sync_plugins.py` → `apply_domains.py` (mainUrl + version) → `generate_json.py repo` → `detect_selectors.py` → Gradle build → `generate_json.py plugins` → branch `builds`.
Runtime: `AdaptiveProvider` memakai selector (auto-detect → `SiteConfig` → bawaan → heuristik) untuk daftar/metadata/episode, lalu `loadLinks` (video tag → extractor bawaan → halaman embed → iframe bersarang → WebView sniff).
Domain: `domain-watch.yml` → `check_domains.py --apply` → registry+tes → PR `auto/domain-update` → manusia merge → `build.yml`.

## 4. Status fitur
| Fitur | Status |
|---|---|
| Validasi registry | SELESAI (tes lulus) |
| Adopsi domain lewat PR + keyword per plugin + retry | SELESAI di kode; BELUM dijalankan di Actions |
| Versi naik saat `shared/` berubah | BELUM |
| Status DISABLED tanpa menghapus folder | BELUM |
| Tes parser berbasis fixture HTML | BELUM |
| Metadata lengkap (rating, backdrop, status, judul alternatif, season, tipe film) | BELUM |
| Monitoring per domain + Issue/Telegram/Discord + dedup | BELUM |
| Publikasi bertahap/prerelease + riwayat rollback | BELUM |
| Playback terverifikasi | BELUM untuk SEMUA sumber (AnimeSail/LayarKaca21 BLOCKED, Kuronime PARTIAL) |

## 5. Perubahan sesi ini (tahap 2)
- `check_domains.py` ditulis ulang: vonis OK/MOVED/BLOCKED/PARKED/DEAD/UNVERIFIED, retry 3x, verifikasi langsung origin baru, keyword minimal 4 huruf, `--apply/--report/--summary`. Alasan: temuan audit 1 (risiko supply-chain) dan 2 (keyword salah).
- `build.yml`: langkah check_domains dihapus (build tidak lagi menulis domain sendiri).
- Baru: `domain-watch.yml`, `pr-check.yml`, `domain_keywords.yml`, `tests/test_check_domains.py`. README dan `docs/AUDIT.md` diperbarui.

## 6. Perintah
- Tes: `python3 -m unittest discover -s tests -v` — registry: `python3 .github/scripts/registry.py`
- Pantau domain lokal (perlu jaringan): `python3 .github/scripts/check_domains.py --report r.json --summary s.md`
- Build: `gradle make makePluginsJson --no-daemon` (JDK 17, Gradle 8.11.1) — TIDAK pernah dijalankan di sesi ini.

## 7. Hasil tes terakhir (14 Okt 2026)
27 tes Python lulus (12 registry + 15 domain). Smoke test `check_domains.py` offline: semua DEAD (sandbox tanpa jaringan), `domains.yml` tidak berubah. YAML keempat workflow valid. Kotlin/Gradle tidak dikompilasi.

## 8. Masalah terbuka
Lihat `docs/AUDIT.md` temuan 3–11. Khusus: PR buatan `GITHUB_TOKEN` tidak memicu `pr-check.yml` (gerbang tes sudah ada di dalam `domain-watch.yml`); `health.yml` masih `|| true` pada push.

## 9. Keputusan arsitektur
Satu repo public cukup; tidak ada repo tambahan. Domain baru lewat PR agar ada review manusia. Cloudflare tidak dipakai di infrastruktur (hanya `CloudflareKiller` di app).

## 10. Secrets/variabel
Belum ada yang wajib. Direncanakan (opsional, tahap 5): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_WEBHOOK_URL`. Setting repo: izinkan Actions membuat PR.

## 11. Workflow
`build.yml` (push main + tiap 6 jam), `health.yml` (tiap 12 jam, uji pemutaran), `domain-watch.yml` (tiap 6 jam), `pr-check.yml` (PR). Publish masih `git push --force` ke `builds` (belum ada rollback).

## 12. Tugas berikutnya
Lihat `NEXT_STEPS.md`.

## 13. INSTRUKSI UNTUK CLAUDE BERIKUTNYA
Baca dokumen ini, `PROJECT_STATE.md`, `NEXT_STEPS.md`, `docs/AUDIT.md`. Periksa ulang kode terhadap klaim di sini, jalankan tes, lalu kerjakan tugas prioritas tertinggi di `NEXT_STEPS.md`. Jangan klaim build/playback berhasil sebelum benar-benar dijalankan.

## 14. Belum diverifikasi
Semua hal yang butuh jaringan: domain aktif sekarang, build Gradle, kompatibilitas Kotlin 2.4.0, `domain-watch.yml` di Actions nyata, playback di Android.
