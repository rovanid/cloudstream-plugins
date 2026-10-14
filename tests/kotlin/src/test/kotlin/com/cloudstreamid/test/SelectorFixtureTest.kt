package com.cloudstreamid.test

import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.junit.jupiter.api.Assumptions.assumeTrue
import org.junit.jupiter.api.DynamicTest
import org.junit.jupiter.api.TestFactory
import java.io.File

/**
 * Menguji selector di Selectors.kt tiap plugin terhadap HTML ASLI yang disimpan di
 * tests/kotlin/fixtures/<NamaProvider>/{list,detail,episode}.html.
 * Fixture belum ada -> tes DILEWATI (bukan gagal), dan namanya tercetak di log.
 */
class SelectorFixtureTest {

    private class Site(
        val name: String,
        val item: String,
        val title: String,
        val episode: String,
        val player: String,
    )

    private val sites = listOf(
        Site(
            "AnimeSailProvider",
            com.cloudstreamid.animesailprovider.Sel.ITEM, com.cloudstreamid.animesailprovider.Sel.TITLE,
            com.cloudstreamid.animesailprovider.Sel.EPISODE, com.cloudstreamid.animesailprovider.Sel.PLAYER
        ),
        Site(
            "KuronimeProvider",
            com.cloudstreamid.kuronimeprovider.Sel.ITEM, com.cloudstreamid.kuronimeprovider.Sel.TITLE,
            com.cloudstreamid.kuronimeprovider.Sel.EPISODE, com.cloudstreamid.kuronimeprovider.Sel.PLAYER
        ),
        Site(
            "LayarKaca21Provider",
            com.cloudstreamid.layarkaca21provider.Sel.ITEM, com.cloudstreamid.layarkaca21provider.Sel.TITLE,
            com.cloudstreamid.layarkaca21provider.Sel.EPISODE, com.cloudstreamid.layarkaca21provider.Sel.PLAYER
        ),
    )

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
            return part.substring(sep.range.last + 1)
        }
        return raw
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
