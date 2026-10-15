import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import org.jetbrains.kotlin.gradle.tasks.KotlinJvmCompile

// Dinaikkan otomatis oleh bump_versions.py kalau isi folder ini berubah
version = 2

android {
    buildFeatures {
        // BuildConfig.LIBRARY_PACKAGE_NAME dipakai untuk membaca layout/drawable plugin
        buildConfig = true
    }
    // Root memakai JVM 1.8 untuk plugin scraper. MyHomepage memanggil fungsi inline Cloudstream yang
    // dibuild dengan JVM 11, jadi modul ini menimpanya ke 11 (plugin lain tidak terpengaruh).
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
}

tasks.withType<KotlinJvmCompile> {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_11)
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

// UI pengaturan (BottomSheet/AppCompat), JSON (Jackson), dan coroutine tidak disediakan stub Cloudstream;
// root repo ini hanya menambahkan NiceHttp dan jsoup. Versi sama dengan repo asal yang terbukti build.
dependencies {
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.annotation:annotation:1.9.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("com.fasterxml.jackson.module:jackson-module-kotlin:2.20.1")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.20.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
}
