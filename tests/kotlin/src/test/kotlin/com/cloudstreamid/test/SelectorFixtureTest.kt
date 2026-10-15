package com.cloudstreamid.test

import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.TestFactory
import java.io.File

/**
 * Menguji selector di Selectors.kt tiap plugin terhadap HTML ASLI yang disimpan di
 * tests/kotlin/fixtures/<NamaProvider>/{list,detail,episode}.html.
 * Fixture belum ada -> tes DILEWATI (bukan gagal), dan namanya tercetak di log.
 * Daftar plugin mengikuti domains.yml otomatis (tambah / hapus / edit / nonaktifkan baris).
 */
class SelectorFixtureTest {

    private class Site(
        val name: String,
        val item: String,
        val title: String,
        val episode: String,
        val player: String,
    )

    /**
     * Daftar plugin dibaca LANGSUNG dari domains.yml setiap tes dijalankan (aturan sama dengan registry.py):
     *   - `NamaProvider: https://host`   -> AKTIF, diuji
     *   - `#NamaProvider: https://host`  -> NONAKTIF, dilewati (folder tetap ada, tidak dibuild)
     *   - baris dihapus                  -> tidak diuji lagi
     *   - baris baru                     -> otomatis ikut diuji (fixture belum ada -> dilewati, bukan gagal)
     * `object Sel` tiap plugin aktif dibaca lewat refleksi; build.gradle.kts tes memasukkan Selectors.kt
     * plugin aktif ke classpath dengan membaca domains.yml yang sama, jadi tidak ada daftar yang ditulis manual.
     */
    private class Registry(val active: List<String>, val disabled: List<String>)

    private val repoRoot = File("../..")

    private val registry: Registry? = readRegistry()

    private fun readRegistry(): Registry? {
        val f = File(repoRoot, "domains.yml")
        if (!f.exists()) return null
        val nameRe = Regex("[A-Za-z][A-Za-z0-9]*Provider")
        val commented = Regex("^#\\s*([A-Za-z][A-Za-z0-9]*Provider)\\s*:\\s*https?://\\S+")
        val active = linkedSetOf<String>()
        val disabled = linkedSetOf<String>()
        for (raw in f.readLines()) {
            val s = raw.trim()
            if (s.isEmpty()) continue
            if (s.startsWith("#")) {
                commented.find(s)?.let { disabled.add(it.groupValues[1]) }
                continue
            }
            val line = s.substringBefore("#")
            if (!line.contains(":")) continue
            val name = line.substringBefore(":").trim()
            if (nameRe.matches(name)) active.add(name)
        }
        disabled.removeAll(active)
        return Registry(active.toList(), disabled.toList())
    }

    private val sites: List<Site> = (registry?.active ?: emptyList())
        .mapNotNull { name ->
            val cls = try {
                Class.forName("com.cloudstreamid.${name.lowercase()}.Sel")
            } catch (e: ClassNotFoundException) {
                println("[LEWATI] $name: aktif di domains.yml tetapi Selectors.kt belum ada / belum dibuat")
                return@mapNotNull null
            }
            fun str(field: String): String = cls.getField(field).get(null) as String
            Site(name, str("ITEM"), str("TITLE"), str("EPISODE"), str("PLAYER"))
        }
        .also { list ->
            registry?.disabled?.forEach { println("[NONAKTIF] $it: di-# di domains.yml, tidak diuji") }
            println("[INFO] diuji: ${list.joinToString { it.name }.ifEmpty { "(tidak ada)" }}")
        }

    @Test
    fun domains_yml_terbaca() {
        val reg = registry
        check(reg != null) { "domains.yml tidak ditemukan di ${repoRoot.canonicalPath}" }
        check(reg.active.isNotEmpty()) { "domains.yml tidak punya entri aktif" }
    }

    private fun fixture(site: String, kind: String): Document? {
        val f = File("fixtures/$site/$kind.html")
        if (!f.exists()) {
            println("[LEWATI] fixture tidak ada: ${f.path}")
            return null
        }
        return Jsoup.parse(extractHtml(f.readText()), "https://example.invalid/")
    }

    /**
     * Fixture dari Chrome "Simpan halaman" berformat MHTML ("Saved by Blink"): HTML asli ada di
     * bagian text/html pertama. Jsoup tidak boleh membaca file mentahnya. HTML biasa dikembalikan apa adanya.
     */
    private fun extractHtml(raw: String): String {
        if (!raw.trimStart().startsWith("From:") || !raw.contains("Saved by Blink")) return raw
        val boundary = Regex("boundary=\"?([^\"\\r\\n;]+)\"?").find(raw)?.groupValues?.get(1) ?: return raw
        for (part in raw.split("--$boundary").drop(1)) {
            val sep = Regex("\\r?\\n\\r?\\n").find(part) ?: continue
            val headers = part.substring(0, sep.range.first)
            if (!Regex("(?i)content-type:\\s*text/html").containsMatchIn(headers)) continue
            return decodePart(headers, part.substring(sep.range.last + 1))
        }
        return raw
    }

    /**
     * Dekode isi bagian MIME sesuai Content-Transfer-Encoding. Chrome memakai quoted-printable untuk sebagian
     * situs (atribut tampil sebagai `class=3D"x"`, baris dipotong `=` + newline) dan `binary` untuk yang lain.
     * Sama dengan _decode_part di .github/scripts/fixture_utils.py.
     */
    private fun decodePart(headers: String, body: String): String {
        val cte = Regex("(?i)content-transfer-encoding:\\s*([\\w-]+)").find(headers)
            ?.groupValues?.get(1)?.lowercase() ?: ""
        val charsetName = Regex("(?i)charset\\s*=\\s*\"?([\\w.:-]+)").find(headers)?.groupValues?.get(1) ?: "utf-8"
        val charset = try {
            java.nio.charset.Charset.forName(charsetName)
        } catch (e: Exception) {
            Charsets.UTF_8
        }
        return when (cte) {
            "quoted-printable" -> String(decodeQuotedPrintable(body), charset)
            "base64" -> String(java.util.Base64.getMimeDecoder().decode(body.trim()), charset)
            else -> body
        }
    }

    private fun decodeQuotedPrintable(s: String): ByteArray {
        val out = java.io.ByteArrayOutputStream(s.length)
        var i = 0
        while (i < s.length) {
            val c = s[i]
            if (c == '=') {
                if (i + 1 < s.length && s[i + 1] == '\n') { i += 2; continue }                      // soft break LF
                if (i + 2 < s.length && s[i + 1] == '\r' && s[i + 2] == '\n') { i += 3; continue } // soft break CRLF
                if (i + 2 < s.length) {
                    val h = Character.digit(s[i + 1], 16)
                    val l = Character.digit(s[i + 2], 16)
                    if (h >= 0 && l >= 0) { out.write(h * 16 + l); i += 3; continue }
                }
                out.write('='.code)
                i++
            } else {
                if (c.code < 128) out.write(c.code) else out.write(c.toString().toByteArray(Charsets.UTF_8))
                i++
            }
        }
        return out.toByteArray()
    }

    @TestFactory
    fun daftar_memiliki_kartu_valid() = sites.map { s ->
        DynamicTest.dynamicTest("${s.name}: list.html") {
            val doc = fixture(s.name, "list")
            assumeTrue(doc != null, "list.html belum ada")
            assumeTrue(s.item.isNotBlank(), "ITEM kosong")
            val cards = doc!!.select(s.item)
            check(cards.size >= 3) { "ITEM '${s.item}' hanya menemukan ${cards.size} kartu (minimal 3)" }
            val withLink = cards.count { it.selectFirst("a[href]") != null }
            check(withLink >= cards.size * 0.8) { "hanya $withLink dari ${cards.size} kartu punya tautan" }
            if (s.title.isNotBlank()) {
                val withTitle = cards.count { (it.selectFirst(s.title)?.text() ?: "").isNotBlank() }
                check(withTitle >= cards.size * 0.8) {
                    "TITLE '${s.title}' kosong di ${cards.size - withTitle} dari ${cards.size} kartu"
                }
            }
        }
    }

    @TestFactory
    fun detail_memiliki_episode() = sites.map { s ->
        DynamicTest.dynamicTest("${s.name}: detail.html") {
            val doc = fixture(s.name, "detail")
            assumeTrue(doc != null, "detail.html belum ada")
            assumeTrue(s.episode.isNotBlank(), "EPISODE kosong")
            val eps = doc!!.select(s.episode).filter { it.hasAttr("href") || it.selectFirst("a[href]") != null }
            check(eps.isNotEmpty()) { "EPISODE '${s.episode}' tidak menemukan tautan episode" }
        }
    }

    @TestFactory
    fun episode_memiliki_pemutar() = sites.map { s ->
        DynamicTest.dynamicTest("${s.name}: episode.html") {
            val doc = fixture(s.name, "episode")
            assumeTrue(doc != null, "episode.html belum ada")
            val player = doc!!.select(s.player.ifBlank { "iframe" })
            val anyEmbed = doc.select("iframe, video, [data-embed], [data-src*=embed]")
            check(player.isNotEmpty() || anyEmbed.isNotEmpty()) {
                "tidak ada elemen pemutar (PLAYER '${s.player}') di episode.html"
            }
        }
    }
}
