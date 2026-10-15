package com.cloudstreamid.sflixprovider

import android.util.Log
import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.network.WebViewResolver
import com.lagradost.cloudstream3.utils.ExtractorLink
import com.lagradost.cloudstream3.utils.ExtractorLinkType
import com.lagradost.cloudstream3.utils.Qualities
import com.lagradost.cloudstream3.utils.loadExtractor
import com.lagradost.cloudstream3.utils.newExtractorLink
import org.jsoup.Jsoup
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

    /** GET ke ajax.php seperti yang dilakukan JS situs; hasilnya potongan HTML. */
    private suspend fun ajaxDoc(url: String, referer: String): Document? {
        return try {
            val txt: String = app.get(
                fixUrl(url), referer = referer,
                headers = mapOf("X-Requested-With" to "XMLHttpRequest")
            ).text
            val d: Document = Jsoup.parse(txt)
            d
        } catch (e: Exception) {
            Log.w(TAG, "ajax gagal: ${e.javaClass.simpleName} ${url.take(80)}")
            null
        }
    }

    private fun episodesOf(doc: Document, out: LinkedHashMap<String, Episode>) {
        val names = HashMap<String, String>()
        for (a: Element in doc.select("h3.film-name a[href]")) {
            val t: String = a.text().trim()
            if (t.isNotBlank()) names[a.attr("href")] = t
        }
        for (a: Element in doc.select("a[href]")) {
            val raw: String = a.attr("href").trim()
            val href = fixUrlNull(raw) ?: continue
            val m = epHref.find(href) ?: continue
            if (out.containsKey(href)) continue
            val s = m.groupValues[1].toInt()
            val e = m.groupValues[2].toInt()
            out[href] = newEpisode(href) {
                this.name = names[raw]?.takeIf { it.isNotBlank() }
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

        // Serial: episode TIDAK ada di HTML mentah. Dimuat JS lewat ajax.php?episode=<token>; tiap musim
        // punya token sendiri di <a class="ss-item" data-ss data-id>. Kita lakukan GET yang sama.
        val episodes = LinkedHashMap<String, Episode>()
        val html = doc.html()
        val tokens = ArrayList<String>()
        for (a: Element in doc.select(Sel.SEASON_ITEM)) {
            val t: String = a.attr("data-id").trim()
            if (t.isNotBlank()) tokens.add("$mainUrl/ajax/ajax.php?episode=$t")
        }
        if (tokens.isEmpty()) CURRENT_URL_RE.find(html)?.groupValues?.get(1)?.let { tokens.add(it) }
        for (u in tokens) {
            ajaxDoc(u, pageUrl)?.let { episodesOf(it, episodes) }
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
    private fun serversOf(doc: Document?): List<Pair<String, String>> {
        if (doc == null) return emptyList()
        val out = ArrayList<Pair<String, String>>()
        for (li: Element in doc.select(Sel.SERVER)) {
            val id: String = li.attr("data-id").trim()
            if (id.startsWith("http")) out.add(li.attr("data-srv").trim() to id)
        }
        return out.distinctBy { it.second }
    }

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
        val pageHtml: String = app.get(data, referer = "$mainUrl/").text
        // Server TIDAK ada di HTML mentah: JS memuatnya dari const pl_url (ajax.php?vdkz=/vds=<token>)
        var servers: List<Pair<String, String>> = emptyList()
        val pl = PL_URL_RE.find(pageHtml)?.groupValues?.get(1)
        if (pl != null) servers = serversOf(ajaxDoc(pl, data))
        if (servers.isEmpty()) servers = serversOf(Jsoup.parse(pageHtml))
        if (servers.isEmpty()) throw ErrorLoadingException("Daftar server kosong di halaman $data")

        // UpCloud (/mv/) dan Vidmoly (/vmf/) di 0123movie.space sama-sama 302 ke embed Byse
        // (mfw09.org/e/<kode>). Ikuti redirect-nya supaya duplikat terbuang dan host aslinya terlihat.
        val resolved = ArrayList<Pair<String, String>>()
        for ((srv, u) in servers) {
            var target = u
            if (u.contains("0123movie.space")) {
                try {
                    val r = app.get(u, referer = "$mainUrl/", allowRedirects = false)
                    val loc: String? = r.headers["Location"]
                    if (!loc.isNullOrBlank() && loc.startsWith("http")) target = loc
                } catch (e: Exception) {
                    Log.w(TAG, "redirect $srv gagal: ${e.javaClass.simpleName}")
                }
            }
            resolved.add(srv to target)
        }
        val embeds = resolved.distinctBy { it.second }
        Log.d(TAG, "embed: " + embeds.joinToString { "${it.first}=${it.second.take(60)}" })

        var ok = false
        for ((_, url) in embeds) {
            try {
                ok = loadExtractor(url, "$mainUrl/", subtitleCallback, callback) || ok
            } catch (e: Exception) {
                Log.w(TAG, "extractor gagal $url: ${e.javaClass.simpleName}")
            }
        }
        if (ok) return true

        // Pemutar Byse/JW dirender JS dan memuat HLS sesudah dimainkan. WebView menangkap request
        // .m3u8/.mp4 (iklan dibuang lewat regex) dan skrip kecil mencoba menekan tombol putar.
        val seen = HashSet<String>()
        for ((srv, url) in embeds.take(3)) {
            val found = try {
                app.get(
                    url, referer = "$mainUrl/",
                    interceptor = WebViewResolver(MEDIA_RE, script = AUTOPLAY_JS)
                ).url
            } catch (e: Exception) {
                Log.w(TAG, "webview $srv gagal: ${e.javaClass.simpleName}")
                continue
            }
            if (!MEDIA_RE.containsMatchIn(found) || !seen.add(found)) {
                Log.w(TAG, "webview $srv: tidak ada media")
                continue
            }
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
        if (!ok) throw ErrorLoadingException("Tautan tidak ditemukan [$name] embed: " + embeds.joinToString { it.second.take(50) })
        return true
    }

    private companion object {
        const val TAG = "SFlixProvider"
        // media asli saja: buang host iklan yang juga memuat .mp4
        val MEDIA_RE = Regex("""(?i)^(?!.*(?:onclickperformance|doubleclick|googlesyndication|adsterra|popads)).*\.(?:m3u8|mp4)(?:\?|$)""")
        // dijalankan sekali setelah halaman dimuat: coba tekan tombol putar secara berkala (maks 25 dtk)
        const val AUTOPLAY_JS = "(function(){var n=0;var t=setInterval(function(){n++;" +
            "var b=document.querySelector('.jw-icon-display,.jw-display-icon-container,.vjs-big-play-button,button[aria-label*=\"lay\"]');" +
            "if(b){try{b.click()}catch(e){}}" +
            "var v=document.querySelector('video');if(v){try{v.muted=true;v.play()}catch(e){}}" +
            "if(n>30)clearInterval(t)},800)})();"
        val PL_URL_RE = Regex("""pl_url\s*=\s*['"]([^'"]+)['"]""")
        val CURRENT_URL_RE = Regex("""current_url\s*=\s*['"]([^'"]+)['"]""")
    }
}
