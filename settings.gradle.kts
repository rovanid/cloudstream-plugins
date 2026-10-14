rootProject.name = "CloudstreamPlugins"

// Setiap folder yang punya build.gradle.kts otomatis jadi plugin, KECUALI yang dinonaktifkan.
// Nonaktif = baris `#NamaProvider: https://host` (di-#) di domains.yml. Foldernya tetap ada,
// hanya tidak dibuild. Daftar `disabled` di bawah untuk penonaktifan manual tambahan.
val disabled = mutableSetOf<String>()

val disabledEntry = Regex("""^#\s*([A-Za-z][A-Za-z0-9]*Provider)\s*:\s*https?://\S+""")
File(rootDir, "domains.yml").takeIf { it.exists() }?.readLines()?.forEach { line ->
    disabledEntry.find(line.trim())?.let { disabled.add(it.groupValues[1]) }
}

File(rootDir, ".").listFiles()
    ?.filter { it.isDirectory && !disabled.contains(it.name) && File(it, "build.gradle.kts").exists() }
    ?.forEach { include(it.name) }
