# NEXT_STEPS (urut prioritas; diperbarui 14 Okt 2026, sesi tahap 3)
Selesai: izin PR diaktifkan dan `domain-watch.yml` dijalankan (hasil di `lanjut.md` bagian 7); Tahap 3 (versi otomatis + DISABLED) selesai di kode dan tes.

1. Pengguna: commit zip ini ke `main`, jalankan `build.yml` manual (workflow_dispatch), lalu laporkan: apakah step "Naikkan versi" menulis `[SAMA]`/`[NAIK]`, apakah build Gradle lolos (`settings.gradle.kts` baru belum pernah dikompilasi), dan apakah `plugin_hashes.json` ikut ter-commit.
2. Pengguna (opsional, uji jalur PR): ubah `domains.yml` Kuronime ke domain palsu di branch uji, jalankan `domain-watch.yml`, lihat apakah PR `auto/domain-update` dibuat; lalu kembalikan.
3. Playback (prioritas produk): tes parser berbasis fixture HTML; `emitDirect` jangan anggap URL ditemukan = sukses; kualitas mp4 jangan ditebak. AnimeSail/LayarKaca21 berstatus 1 (Ok) tanpa bukti: pertimbangkan status 3 (Beta) sampai terverifikasi.
4. Metadata di `load()`: rating, backdrop, status, judul alternatif, season, tipe film.
5. Tahap 5: monitoring per domain + GitHub Issue (dedup/cooldown/pulih), Telegram/Discord opsional. Catatan: AnimeSail/LayarKaca21 selalu 403 dari CI, jadi pantau dengan keadaan "BLOCKED" tersendiri, jangan dihitung gagal.
6. Tahap 6: prerelease dulu, riwayat build untuk rollback (ganti `--amend` + force push); patok versi Kotlin/Gradle/cloudstream3.
7. Rapikan `health.yml` (hapus `|| true`, konflik push dengan `build.yml`).

8. (Selesai sesi ini) `.gitignore` kini mengabaikan `__pycache__/` dan `*.pyc`; runner dipatok `ubuntu-24.04` (ubuntu-latest pindah ke Ubuntu 26 mulai 19 Okt 2026). Pengguna: jalankan `git rm -r --cached .github/scripts/__pycache__` bila folder itu masih ada di repo. Build #23, health #2, domain-watch #2 sukses di Actions.
9. (Selesai) status AnimeSail/LayarKaca21 -> 3 (Beta). Berikutnya: ambil fixture HTML nyata (simpan halaman daftar/detail/episode tiap situs dari browser ke `tests/fixtures/`), lalu tes parser dijalankan di CI.
10. Pengguna: buat branch `test/awal`, upload zip, jalankan `kotlin-test.yml` (atau push). Kirim isi Job summary / log merah ke Claude untuk diperbaiki. Lalu simpan fixture HTML asli ke `tests/kotlin/fixtures/` dan ulangi. Setelah itu: refactor parsing murni dari AdaptiveProvider agar bisa dites.
