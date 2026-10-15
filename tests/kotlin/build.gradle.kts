plugins {
    kotlin("jvm") version "2.0.21"
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.jsoup:jsoup:1.18.3")
    testImplementation(platform("org.junit:junit-bom:5.11.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

kotlin { jvmToolchain(17) }

// Daftar plugin diambil dari domains.yml (baris AKTIF saja, aturan sama dengan registry.py), bukan ditulis manual:
// tambah / hapus / edit / nonaktifkan(#) baris di domains.yml -> srcDir di bawah ikut berubah sendiri.
val providerName = Regex("[A-Za-z][A-Za-z0-9]*Provider")
val activeProviders: List<String> = file("../../domains.yml").takeIf { it.exists() }?.readLines().orEmpty()
    .map { it.trim() }
    .filter { it.isNotEmpty() && !it.startsWith("#") && it.substringBefore("#").contains(":") }
    .map { it.substringBefore("#").substringBefore(":").trim() }
    .filter { providerName.matches(it) }
    .distinct()

sourceSets {
    test {
        // Selectors.kt tiap plugin aktif (isi `object Sel`, paket berbeda-beda) dan SiteConfig.kt dipakai
        // apa adanya, tanpa salinan, jadi tes selalu menguji kode yang sama dengan yang dibuild.
        // AdaptiveProvider.kt sengaja TIDAK ikut (butuh class Cloudstream/Android).
        kotlin.srcDir("../../shared/kotlin/com/cloudstreamid/common")
        activeProviders.forEach { name ->
            val dir = file("../../$name/src/main/kotlin/com/cloudstreamid/${name.lowercase()}")
            if (dir.isDirectory) kotlin.srcDir(dir)
        }
        kotlin.exclude("**/*Provider.kt", "**/*Plugin.kt")
    }
}

tasks.test {
    useJUnitPlatform()
    // domains.yml dan fixture dibaca saat tes jalan -> perubahan keduanya harus memicu tes ulang.
    inputs.file("../../domains.yml").optional()
    inputs.dir("fixtures").optional()
    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = true
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
