# lanjut.md — dokumen utama kesinambungan proyek

Diperbarui: 14 Okt 2026 (sesi tahap 3 + patch kecil). Dokumen ini adalah SUMBER UTAMA. `PROJECT_STATE.md` (status fitur) dan `NEXT_STEPS.md` (tugas) melengkapinya; `docs/AUDIT.md` berisi temuan audit.

## 1. Proyek
Repo plugin CloudStream (`rovanid/cloudstream-plugins`, dari `repo.json`) untuk sumber anime/film berbahasa Indonesia. Sasaran: domain di `domains.yml` dikelola otomatis dan aman; metadata dan pemutaran video benar; ada pemantauan, notifikasi, dan CI/CD.

## 2. File penting
- `domains.yml` registry (format `NamaProvider: https://host`), `plugin_types.yml` (anime|movie), `domain_keywords.yml` (keyword per plugin)
- `.github/scripts/`: `registry.py` (validator), `check_domains.py` (pemantau, hanya mengusulkan), `sync_plugins.py`, `apply_domains.py` (hanya mainUrl), `bump_versions.py` (satu-satunya yang menaikkan version), `generate_json.py`, `detect_selectors.py`, `check_playback.py`
- `.github/workflows/`: `build.yml`, `health.yml`, `domain-watch.yml`, `pr-check.yml`
- `shared/kotlin/com/cloudstreamid/common/AdaptiveProvider.kt` (mesin parser generik, 992 baris) dan `SiteConfig.kt`
- Plugin: `AnimeSailProvider/`, `KuronimeProvider/`, `LayarKaca21Provider/` (masing-masing `Selectors.kt`, `*Provider.kt`, `*Plugin.kt`, `build.gradle.kts`)
- `tests/` (Python unittest), laporan: `detection_report.md`, `playback_report.md`, `playback_state.json`

## 3. Alur
`domains.yml` → `registry.py` (gerbang) → `sync_plugins.py` → `apply_domains.py` (mainUrl) → `generate_json.py repo` → `detect_selectors.py` → `bump_versions.py` (version) → commit → Gradle build → `generate_json.py plugins` → branch `builds`.
Runtime: `AdaptiveProvider` memakai selector (auto-detect → `SiteConfig` → bawaan → heuristik) untuk daftar/metadata/episode, lalu `loadLinks` (video tag → extractor bawaan → halaman embed → iframe bersarang → WebView sniff).
Domain: `domain-watch.yml` → `check_domains.py --apply` → registry+tes → PR `auto/domain-update` → manusia merge → `build.yml`.

## 4. Status fitur
| Fitur | Status |
|---|---|
| Validasi registry | SELESAI (tes lulus) |
| Adopsi domain lewat PR + keyword per plugin + retry | SELESAI di kode; DIJALANKAN di Actions 14 Okt 2026 (lihat bagian 7); jalur PR sungguhan belum teruji |
| Versi naik saat `shared/`, kode plugin, mainUrl, atau selector berubah | SELESAI di kode + tes; BELUM dijalankan di Actions |
| Status DISABLED tanpa menghapus folder (`#Nama: url`) | SELESAI di kode + tes; `settings.gradle.kts` BELUM dikompilasi Gradle |
| Tes parser berbasis fixture HTML | BELUM |
| Metadata lengkap (rating, backdrop, status, judul alternatif, season, tipe film) | BELUM |
| Monitoring per domain + Issue/Telegram/Discord + dedup | BELUM |
| Publikasi bertahap/prerelease + riwayat rollback | BELUM |
| Playback terverifikasi | BELUM untuk SEMUA sumber (AnimeSail/LayarKaca21 BLOCKED, Kuronime PARTIAL) |

## 5. Perubahan sesi ini (tahap 2)
- `check_domains.py` ditulis ulang: vonis OK/MOVED/BLOCKED/PARKED/DEAD/UNVERIFIED, retry 3x, verifikasi langsung origin baru, keyword minimal 4 huruf, `--apply/--report/--summary`. Alasan: temuan audit 1 (risiko supply-chain) dan 2 (keyword salah).
- `build.yml`: langkah check_domains dihapus (build tidak lagi menulis domain sendiri).
- Baru: `domain-watch.yml`, `pr-check.yml`, `domain_keywords.yml`, `tests/test_check_domains.py`. README dan `docs/AUDIT.md` diperbarui.

## 5b. Perubahan sesi tahap 3 (14 Okt 2026)
- Baru `.github/scripts/bump_versions.py` + `plugin_hashes.json` (baseline sudah disertakan): hash SHA-256 `shared/kotlin` + folder tiap plugin aktif; hash berbeda → `version` plugin itu naik 1. Baris `version =` dan tanggal di header `// @auto-detect` Selectors.kt dikecualikan dari hash (kalau tidak, naik terus-menerus). Plugin baru hanya dicatat (baseline), tidak naik.
- Penaikan versi DIPINDAHKAN ke skrip ini saja: `bump_version` dihapus dari `apply_domains.py` dan `detect_selectors.py` (kalau tidak, versi naik dua kali). `build.yml` menjalankannya sesudah `detect_selectors.py`, sebelum commit.
- DISABLED: `#Nama: https://host` di `domains.yml` = folder DIPERTAHANKAN tetapi tidak dibuild (`settings.gradle.kts` membaca baris ber-# itu; `sync_plugins.py` tidak menghapusnya; `registry.py` tidak memperingatkan). Menghapus baris sama sekali tetap menghapus folder. PERUBAHAN PERILAKU: dulu `#` = hapus folder.
- Tes baru: `tests/test_bump_versions.py` (12), `tests/test_sync_plugins.py` (6); `test_registry.py` disesuaikan dengan aturan `#`.

## 6. Perintah
- Tes: `python3 -m unittest discover -s tests -v` — registry: `python3 .github/scripts/registry.py`
- Pantau domain lokal (perlu jaringan): `python3 .github/scripts/check_domains.py --report r.json --summary s.md`
- Build: `gradle make makePluginsJson --no-daemon` (JDK 17, Gradle 8.11.1) — TIDAK pernah dijalankan di sesi ini.

## 7. Hasil tes terakhir (14 Okt 2026)
- Lokal (sandbox, tanpa jaringan): 46 tes Python lulus. Smoke test end-to-end di salinan repo: baseline → tanpa perubahan tidak naik → ubah `shared/` naik 1 sekali (tidak naik lagi saat dijalankan ulang) → ganti domain naik 1 → `#` pada plugin menyisakan foldernya. YAML keempat workflow valid. Kotlin/Gradle tidak dikompilasi (termasuk `settings.gradle.kts` baru).
- GitHub Actions nyata (dilaporkan pengguna lewat screenshot): izin "Allow GitHub Actions to create and approve pull requests" sudah dicentang; `domain-watch.yml` jalan sukses (6 dtk) dan tes registry 27/27 lulus. Hasil domain: AnimeSail (`anisail.com`) dan LayarKaca21 (`tv12.lk21official.cc`) BLOCKED HTTP 403 dari CI (tidak bisa diverifikasi, domains.yml tidak diubah); Kuronime (`kuronime.sbs`) OK. Tidak ada usulan sehingga PR belum pernah dibuat: jalur pembuatan PR belum teruji.
- Catatan: dua dari tiga sumber tidak bisa dipantau dari runner GitHub karena memblokir bot; pemantauan domain mereka praktis manual.

## 7b. Hasil Actions nyata tambahan (14 Okt 2026, laporan pengguna lewat screenshot)
- `build.yml` #23 sukses (1m33s): `settings.gradle.kts` lolos Gradle; step "Naikkan versi" menulis `[SAMA]` untuk ketiga plugin (baseline, wajar); bot meng-commit hasil build.
- `health.yml` #2 sukses: AnimeSail/LayarKaca21 BLOCKED (bot), Kuronime PARTIAL (embed hidup, video tidak bisa diekstrak script; cek manual di aplikasi).
- `domain-watch.yml` #2 (manual) sukses: hasil sama seperti bagian 7, tanpa usulan; jalur PR masih belum teruji.
- Temuan + perbaikan (belum diuji di Actions): `__pycache__` ikut ter-commit karena `git add -A` -> `.gitignore` ditambah `__pycache__/` dan `*.pyc` (folder lama perlu `git rm -r --cached .github/scripts/__pycache__`). `ubuntu-latest` pindah ke Ubuntu 26 mulai 19 Okt 2026 -> semua workflow dipatok `ubuntu-24.04`. Peringatan Node.js 20 deprecated pada actions v4/v5 belum ditangani.

## 8. Masalah terbuka
Lihat `docs/AUDIT.md` temuan 6–11 (3 dan 4 selesai di kode, belum diuji di Actions). Khusus: `plugin_hashes.json` baru terisi baseline; di build nyata pertama, `detect_selectors.py` bisa mengubah Selectors.kt sehingga versi naik (itu benar). PR buatan `GITHUB_TOKEN` tidak memicu `pr-check.yml` (gerbang tes sudah ada di dalam `domain-watch.yml`); `health.yml` masih `|| true` pada push.

## 9. Keputusan arsitektur
Satu repo public cukup; tidak ada repo tambahan. Domain baru lewat PR agar ada review manusia. Cloudflare tidak dipakai di infrastruktur (hanya `CloudflareKiller` di app).

## 10. Secrets/variabel
Belum ada yang wajib. Direncanakan (opsional, tahap 5): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DISCORD_WEBHOOK_URL`. Setting repo: izinkan Actions membuat PR.

## 11. Workflow
(Semua berjalan di `ubuntu-24.04`.) `build.yml` (push main + tiap 6 jam), `health.yml` (tiap 12 jam, uji pemutaran), `domain-watch.yml` (tiap 6 jam), `pr-check.yml` (PR). Publish masih `git push --force` ke `builds` (belum ada rollback).

## 12. Tugas berikutnya
Lihat `NEXT_STEPS.md`.

## 13. INSTRUKSI UNTUK CLAUDE BERIKUTNYA
Baca dokumen ini, `PROJECT_STATE.md`, `NEXT_STEPS.md`, `docs/AUDIT.md`. Periksa ulang kode terhadap klaim di sini, jalankan tes, lalu kerjakan tugas prioritas tertinggi di `NEXT_STEPS.md`. Jangan klaim build/playback berhasil sebelum benar-benar dijalankan.

## 14. Belum diverifikasi
Semua hal yang butuh jaringan: domain aktif sekarang, build Gradle, kompatibilitas Kotlin 2.4.0, `domain-watch.yml` di Actions nyata, playback di Android.
