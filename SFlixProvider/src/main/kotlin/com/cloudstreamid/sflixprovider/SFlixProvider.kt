package com.cloudstreamid.sflixprovider

import android.util.Log
import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.network.WebViewResolver
import com.lagradost.cloudstream3.utils.ExtractorLink
import com.lagradost.cloudstream3.utils.ExtractorLinkType
import com.lagradost.cloudstream3.utils.Qualities
import com.lagradost.cloudstream3.utils.loadExtractor
import com.lagradost.cloudstream3.utils.newExtractorLink
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element
import java.net.URLEncoder

class SFlixProvider : MainAPI() {
    // JANGAN ubah format baris mainUrl ini, dipakai apply_domains.py
    override var mainUrl = "https://sflix.win"
    override var name = "SFlix"
    override var lang = "en"
    override val hasMainPage = true
    override val supportedTypes = setOf(TvType.Movie, TvType.TvSeries)

    // Kategori asli situs: /movies/ dan /tv-series/ (paginasi: /movies/page/2/)
    override val mainPage: List<MainPageData>
        get() = mainPageOf(
            "$mainUrl/movies/" to "Movies",
            "$mainUrl/tv-series/" to "TV Shows"
        )

    private fun pageUrl(base: String, page: Int): String =
        if (page <= 1) base else base.trimEnd('/') + "/page/$page/"

    // Helper bertipe eksplisit: jangan biarkan Kotlin menyimpulkan tipe Jsoup (anotasi jspecify tidak ada di classpath)
    private fun first(root: Element, sel: String): Element? = root.selectFirst(sel)

    private fun imgUrl(el: Element?, vararg attrs: String): String? {
        if (el == null) return null
        for (a in attrs) {
            val v: String = el.attr(a).trim()
            if (v.isNotBlank() && !v.startsWith("data:")) return v
        }
        return null
    }

    // ------------------------------------------------------------------ daftar
    private fun toCard(el: Element): SearchResponse? {
        val a = first(el, Sel.TITLE) ?: first(el, Sel.POSTER_LINK) ?: return null
        val href = fixUrlNull(a.attr("href").trim()) ?: return null
        if (!href.contains("/movie/") && !href.contains("/series/")) return null
        val title = a.attr("title").ifBlank { a.text() }.trim().ifBlank { return null }
        val poster = imgUrl(first(el, Sel.POSTER), "data-src", "data-lazy-src", "src")
            ?.replace("/w185/", "/w500/")
        return if (href.contains("/series/")) {
            newTvSeriesSearchResponse(title, href, TvType.TvSeries) { this.posterUrl = poster }
        } else {
            newMovieSearchResponse(title, href, TvType.Movie) { this.posterUrl = poster }
        }
    }

    private fun cardsOf(doc: Document): List<SearchResponse> =
        doc.select(Sel.ITEM).mapNotNull { toCard(it) }.distinctBy { it.url }

    override suspend fun getMainPage(page: Int, request: MainPageRequest): HomePageResponse {
        val doc = app.get(pageUrl(request.data, page), referer = "$mainUrl/").document
        val items = cardsOf(doc)
        if (items.isEmpty() && page == 1) {
            throw ErrorLoadingException("Daftar kosong. Situs mungkin memblokir akses, domain berubah, atau tampilannya berubah.")
        }
        return newHomePageResponse(request.name, items, hasNext = items.isNotEmpty())
    }

    override suspend fun search(query: String): List<SearchResponse> {
        val q = URLEncoder.encode(query, "UTF-8")
        return cardsOf(app.get("$mainUrl${Sel.SEARCH}$q", referer = "$mainUrl/").document)
    }

    // ------------------------------------------------------------------ detail
    private fun rowOf(doc: Document, label: String): Element? =
        doc.select(Sel.D_ROW).firstOrNull { first(it, "strong")?.text()?.trim()?.startsWith(label, true) == true }

    private val epHref = Regex("""/series/[^/]+/(\d+)-(\d+)/?$""")

    private fun episodesOf(doc: Document, out: LinkedHashMap<String, Episode>) {
        val names = doc.select("h3.film-name a.eps-item[href]").associate { it.attr("href") to it.text().trim() }
        for (a in doc.select(Sel.EPISODE)) {
            val href = fixUrlNull(a.attr("href").trim()) ?: continue
            val m = epHref.find(href) ?: continue
            if (out.containsKey(href)) continue
            val s = m.groupValues[1].toInt()
            val e = m.groupValues[2].toInt()
            out[href] = newEpisode(href) {
                this.name = names[a.attr("href")]?.takeIf { it.isNotBlank() }
                this.season = s
                this.episode = e
            }
        }
    }

    override suspend fun load(url: String): LoadResponse {
        // jangan pakai tautan di h2.heading-name (di situs kadang menunjuk judul lain); pakai URL halaman
        val doc = app.get(url, referer = "$mainUrl/").document
        val pageUrl = first(doc, "link[rel=canonical]")?.attr("href")?.takeIf { it.startsWith("http") } ?: url
        val title = first(doc, Sel.D_TITLE)?.text()?.trim()
            ?: doc.title().removePrefix("Watch ").substringBefore(" Online").trim()
        val poster = imgUrl(first(doc, Sel.D_POSTER), "data-src", "src")?.replace("/w185/", "/w500/")
        val plot = first(doc, Sel.D_DESC)?.ownText()?.trim()?.takeIf { it.isNotBlank() }
        val tags = rowOf(doc, "Genre")?.select("a")?.map { it.text().trim() }?.filter { it.isNotEmpty() }
        val cast = rowOf(doc, "Casts")?.select("a")?.map { it.text().trim() }?.filter { it.isNotEmpty() }
        val year = (rowOf(doc, "Released")?.text() ?: rowOf(doc, "Year")?.text())
            ?.let { Regex("""(19|20)\d{2}""").find(it)?.value?.toIntOrNull() }
        val minutes = first(doc, Sel.D_DURATION)?.text()?.let { Regex("""\d+""").find(it)?.value?.toIntOrNull() }

        if (!pageUrl.contains("/series/")) {
            return newMovieLoadResponse(title, pageUrl, TvType.Movie, pageUrl) {
                this.posterUrl = poster
                this.plot = plot
                this.year = year
                this.tags = tags
                this.duration = minutes
                this.actors = cast?.map { ActorData(Actor(it)) }
            }
        }

        // Serial: halaman seri hanya memuat episode musim yang aktif. Musim lain dicoba lewat
        // /series/slug-ID/<musim>-1/ (pola URL episode situs). BELUM terverifikasi: lihat catatan.
        val episodes = LinkedHashMap<String, Episode>()
        episodesOf(doc, episodes)
        val seasons = doc.select(Sel.SEASON_ITEM).mapNotNull { it.attr("data-ss").toIntOrNull() }.distinct().sorted()
        val have = episodes.values.mapNotNull { it.season }.toSet()
        for (s in seasons) {
            if (s in have) continue
            try {
                episodesOf(app.get(pageUrl.trimEnd('/') + "/$s-1/", referer = pageUrl).document, episodes)
            } catch (e: Exception) {
                Log.w(TAG, "musim $s gagal dimuat: ${e.javaClass.simpleName}")
            }
        }
        val sorted = episodes.values.sortedWith(compareBy({ it.season ?: 0 }, { it.episode ?: 0 }))
        return newTvSeriesLoadResponse(title, pageUrl, TvType.TvSeries, sorted) {
            this.posterUrl = poster
            this.plot = plot
            this.year = year
            this.tags = tags
            this.actors = cast?.map { ActorData(Actor(it)) }
        }
    }

    // ------------------------------------------------------------------- video
    /**
     * Halaman film/episode memuat daftar server sebagai <li class="sv-item" data-srv data-id="URL embed">.
     * Embed berupa host pihak ketiga (0123movie.space, vidsrc.cc, player.videasy.net). Urutan: ekstraktor
     * bawaan CloudStream dulu; kalau tidak ada yang cocok, WebView menangkap request .m3u8/.mp4.
     */
    override suspend fun loadLinks(
        data: String,
        isCasting: Boolean,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit
    ): Boolean {
        val doc = app.get(data, referer = "$mainUrl/").document
        val servers = doc.select(Sel.SERVER)
            .map { it.attr("data-srv").trim() to it.attr("data-id").trim() }
            .filter { it.second.startsWith("http") }
            .distinctBy { it.second }
        if (servers.isEmpty()) throw ErrorLoadingException("Daftar server kosong di halaman $data")

        var ok = false
        for ((_, url) in servers) {
            try {
                ok = loadExtractor(url, "$mainUrl/", subtitleCallback, callback) || ok
            } catch (e: Exception) {
                Log.w(TAG, "extractor gagal $url: ${e.javaClass.simpleName}")
            }
        }
        if (ok) return true

        val seen = HashSet<String>()
        for ((srv, url) in servers.take(3)) {
            val found = try {
                app.get(url, referer = "$mainUrl/", interceptor = WebViewResolver(MEDIA_RE)).url
            } catch (e: Exception) {
                Log.w(TAG, "webview $srv gagal: ${e.javaClass.simpleName}")
                continue
            }
            if (!MEDIA_RE.containsMatchIn(found) || !seen.add(found)) continue
            val q = Regex("""(?<!\d)(2160|1440|1080|720|480|360)(?!\d)""").find(found)?.value?.toIntOrNull()
            callback.invoke(
                newExtractorLink(name, "$name $srv", found,
                    if (found.contains(".m3u8", true)) ExtractorLinkType.M3U8 else ExtractorLinkType.VIDEO) {
                    this.referer = url
                    this.quality = q ?: Qualities.Unknown.value
                }
            )
            ok = true
            break
        }
        if (!ok) throw ErrorLoadingException("Tautan tidak ditemukan [$name] server: " + servers.joinToString { it.first })
        return true
    }

    private companion object {
        const val TAG = "SFlixProvider"
        val MEDIA_RE = Regex("""(?i)\.(m3u8|mp4)(\?|$)""")
    }
}
