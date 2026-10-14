rootProject.name = "CloudstreamPlugins"

// Setiap folder yang punya build.gradle.kts otomatis jadi plugin.
// Untuk menonaktifkan sementara sebuah plugin, tulis nama foldernya di sini.
val disabled = listOf<String>()

File(rootDir, ".").listFiles()
    ?.filter { it.isDirectory && !disabled.contains(it.name) && File(it, "build.gradle.kts").exists() }
    ?.forEach { include(it.name) }
