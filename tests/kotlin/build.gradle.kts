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

sourceSets {
    test {
        // Selectors.kt tiap plugin (isi `object Sel`, paket berbeda-beda) dan SiteConfig.kt dipakai
        // apa adanya, tanpa salinan, jadi tes selalu menguji kode yang sama dengan yang dibuild.
        // AdaptiveProvider.kt sengaja TIDAK ikut (butuh class Cloudstream/Android).
        kotlin.srcDir("../../shared/kotlin/com/cloudstreamid/common")
        kotlin.srcDir("../../AnimeSailProvider/src/main/kotlin/com/cloudstreamid/animesailprovider")
        kotlin.srcDir("../../KuronimeProvider/src/main/kotlin/com/cloudstreamid/kuronimeprovider")
        kotlin.srcDir("../../LayarKaca21Provider/src/main/kotlin/com/cloudstreamid/layarkaca21provider")
        kotlin.exclude("**/*Provider.kt", "**/*Plugin.kt")
    }
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        events("passed", "skipped", "failed")
        showStandardStreams = true
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
