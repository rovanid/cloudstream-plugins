# NEXT_STEPS (urut prioritas; diperbarui 14 Okt 2026)
1. Pengguna: aktifkan "Allow GitHub Actions to create pull requests", jalankan `domain-watch.yml` manual, laporkan hasilnya (verifikasi tahap 2 di dunia nyata).
2. Tahap 3: naikkan `version` plugin otomatis saat `shared/` berubah; status DISABLED yang tidak menghapus folder (`sync_plugins.py`).
3. Playback (prioritas produk): tes parser berbasis fixture HTML; `emitDirect` jangan anggap URL ditemukan = sukses; kualitas mp4 jangan ditebak.
4. Metadata di `load()`: rating, backdrop, status, judul alternatif, season, tipe film.
5. Tahap 5: monitoring per domain + GitHub Issue (dedup/cooldown/pulih), Telegram/Discord opsional.
6. Tahap 6: prerelease dulu, riwayat build untuk rollback (ganti `--amend` + force push); patok versi Kotlin/Gradle/cloudstream3.
7. Rapikan `health.yml` (hapus `|| true`, konflik push dengan `build.yml`).
