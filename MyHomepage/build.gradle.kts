// Dinaikkan otomatis oleh bump_versions.py kalau isi folder ini berubah
version = 1

android {
    buildFeatures {
        // BuildConfig.LIBRARY_PACKAGE_NAME dipakai untuk membaca layout/drawable plugin
        buildConfig = true
    }
}

cloudstream {
    description = "Beranda kustom: gabungkan kategori beranda dari plugin lain (tanpa sync)"
    authors = listOf("Plugin ID")
    status = 3 // Beta-only. Ubah ke 1 setelah dicoba di aplikasi
    tvTypes = listOf("Movie", "TvSeries", "Anime")
    language = "id"
    requiresResources = true
}
