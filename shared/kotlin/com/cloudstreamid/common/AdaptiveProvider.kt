package com.cloudstreamid.common

import android.util.Log
import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.network.CloudflareKiller
import com.lagradost.cloudstream3.network.WebViewResolver
import com.lagradost.cloudstream3.utils.*
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element
import java.net.URI
import java.net.URLEncoder

/**
 * Provider generik yang MENYESUAIKAN DIRI saat dijalankan di aplikasi (bukan di GitHub Actions).
 *
 * Kenapa: deteksi selector di CI hampir selalu diblokir Cloudflare, sehingga Selectors.kt
 * tertinggal di nilai default dan daftar tampil kosong / salah. Di sini setiap selector hanya
 * KANDIDAT. Mesin mencoba berurutan (hasil auto-detect -> tuning manual -> bawaan -> heuristik
 * struktur) dan memakai yang benar-benar menghasilkan kartu/episode/pemutar yang valid.
 */
abstract class AdaptiveProvider : MainAPI() {
    abstract val config: SiteConfig

    override val hasMainPage = true

    private val cf by lazy { CloudflareKiller() }
    private var searchTemplate: String? = null
    private var homeHrefs: Set<String>? = null

    private val isAnime: Boolean
        get() = supportedTypes.contains(TvType.Anime) || supportedTypes.contains(TvType.AnimeMovie)

    // ------------------------------------------------------------------ util
    private fun String.cleanSpaces(): String = replace(Regex("\\s+"), " ").trim()

    private fun absUrl(p: String): String =
        if (p.startsWith("http")) p else mainUrl.trimEnd('/') + (if (p.startsWith("/")) p else "/$p")

    private suspend fun fetch(url: String, referer: String? = null): Document =
        app.get(url, referer = referer ?: "$mainUrl/", interceptor = cf).document

    private fun safeSelect(root: Element, sel: String): List<Element> {
        if (sel.isBlank()) return emptyList()
        return try {
            root.select(sel).toList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    private fun domainKey(host: String?): String {
        val h = (host ?: "").lowercase()
        val p = h.split(".")
        return if (p.size >= 2) p.takeLast(2).joinToString(".") else h
    }

    private fun pathOf(href: String): String =
        try {
            (URI(href).path ?: "").trim('/')
        } catch (e: Exception) {
            href.substringAfter("://").substringAfter('/', "").substringBefore('?').trim('/')
        }

    private fun isRootOrJunk(href: String): Boolean {
        val uri = try {
            URI(href)
        } catch (e: Exception) {
            return false
        }
        val mine = try {
            URI(mainUrl).host
        } catch (e: Exception) {
            null
        }
        if (uri.host != null && domainKey(uri.host) != domainKey(mine)) return true
        val path = (uri.path ?: "").trim('/')
        if (path.isEmpty()) return true
        val first = path.substringBefore('/').lowercase()
        return first in JUNK_FIRST_SEGMENTS || first.startsWith("wp-")
    }

    private fun validAnchor(a: Element): Boolean {
        val h = a.attr("href").trim()
        return h.isNotEmpty() && !h.startsWith("#") &&
            !h.startsWith("javascript", true) && !h.startsWith("mailto", true)
    }

    private fun linkOf(el: Element): Element? =
        if (el.tagName() == "a" && validAnchor(el)) el
        else el.select("a[href]").firstOrNull { validAnchor(it) }

    private fun cardHref(el: Element): String? = fixUrlNull(linkOf(el)?.attr("href")?.trim())

    // ------------------------------------------------------------ judul/poster
    private fun cardTitle(el: Element): String? {
        val sels = listOf(config.title) + config.extraTitle + TITLE_SELECTORS
        for (s in sels) {
            val t = safeSelect(el, s).firstOrNull()?.text()?.cleanSpaces()
            if (!t.isNullOrBlank() && t.length >= 2) return t
        }
        val candidates = listOf(
            linkOf(el)?.attr("title"),
            el.selectFirst("img[alt]")?.attr("alt"),
            if (el.tagName() == "a") el.text() else null
        )
        return candidates.firstOrNull { !it.isNullOrBlank() && it.trim().length >= 2 }?.cleanSpaces()
    }

    private fun usableImage(v: String?): String? {
        val s = v?.trim() ?: return null
        if (s.isEmpty() || s.startsWith("data:")) return null
        if (Regex("(?i)(placeholder|blank\\.|loading|spacer|lazy\\.)").containsMatchIn(s)) return null
        return fixUrlNull(s)
    }

    private fun posterOf(el: Element): String? {
        val nodes = listOf(el) + el.select("img, [data-setbg], [data-bg], [style*=background]").toList()
        for (n in nodes) {
            for (a in IMG_ATTRS) usableImage(n.attr(a))?.let { return it }
            val srcset = n.attr("srcset").trim()
            if (srcset.isNotEmpty()) usableImage(srcset.split(",").first().trim().substringBefore(" "))?.let { return it }
            val style = n.attr("style")
            if (style.contains("url(")) {
                val m = Regex("url\\((['\"]?)(.+?)\\1\\)").find(style)
                usableImage(m?.groupValues?.getOrNull(2))?.let { return it }
            }
        }
        return null
    }

    private fun tidyTitle(raw: String, stripEpisode: Boolean): String {
        var t = raw.cleanSpaces()
        t = t.replace(Regex("(?i)^(nonton|streaming|download)\\s+(film|anime|movie|donghua|drama)?\\s*"), "")
        t = t.replace(Regex("(?i)\\s*[-–|]?\\s*(subtitle|sub)\\s+indo(nesia)?\\s*$"), "")
        if (stripEpisode) t = t.replace(Regex("(?i)\\s*[-–]?\\s*(episode|eps?)\\s*\\d+.*$"), "")
        t = t.trim()
        return if (t.isBlank()) raw.cleanSpaces() else t
    }

    // ------------------------------------------------------------------ kartu
    private fun isValidCard(el: Element): Boolean {
        if (el.parents().any { it.tagName() in NAV_TAGS }) return false
        val href = cardHref(el) ?: return false
        if (isRootOrJunk(href)) return false
        return cardTitle(el) != null
    }

    private fun stableClass(c: String): Boolean =
        Regex("[A-Za-z_][\\w-]*").matches(c) && c.length <= 40 && !Regex("\\d{2,}").containsMatchIn(c)

    /** Heuristik terakhir: kartu = leluhur tertinggi yang hanya memuat satu <img>. */
    private fun structuralCards(doc: Document): List<Element> {
        val groups = LinkedHashMap<String, MutableList<Element>>()
        for (img in doc.select("img")) {
            if (img.parents().any { it.tagName() in NAV_TAGS }) continue
            var card: Element? = null
            var anc: Element? = img.parent()
            while (anc != null && anc.tagName() != "body" && anc.tagName() != "html") {
                if (anc.select("img").size != 1) break
                card = anc
                anc = anc.parent()
            }
            if (card == null || cardHref(card) == null) continue
            val key = card.tagName() + "." + card.classNames().filter { stableClass(it) }.sorted().joinToString(".")
            groups.getOrPut(key) { mutableListOf() }.add(card)
        }
        val best = groups.values.maxByOrNull { it.size } ?: return emptyList()
        return if (best.size >= 4) best else emptyList()
    }

    private fun findCards(doc: Document, minCount: Int): List<Element> {
        val cands = (listOf(config.item) + config.extraItems + BUILTIN_ITEMS).filter { it.isNotBlank() }.distinct()
        for (sel in cands) {
            val cards = safeSelect(doc, sel).filter { isValidCard(it) }.distinctBy { cardHref(it) }
            if (cards.size >= minCount) return cards
        }
        return structuralCards(doc).filter { isValidCard(it) }.distinctBy { cardHref(it) }
    }

    private fun toSearchResult(el: Element): SearchResponse? {
        val href = cardHref(el) ?: return null
        val raw = cardTitle(el) ?: return null
        val stripEp = config.seriesPrefix.isNotBlank() || config.seriesLinkHints.isNotEmpty()
        val title = tidyTitle(raw, stripEp)
        val poster = posterOf(el)
        return if (isAnime) {
            newAnimeSearchResponse(title, href, TvType.Anime) {
                this.posterUrl = poster
            }
        } else {
            val hint = el.text() + " " + href
            if (SERIES_HINT.containsMatchIn(hint)) {
                newTvSeriesSearchResponse(title, href, TvType.TvSeries) {
                    this.posterUrl = poster
                }
            } else {
                newMovieSearchResponse(title, href, TvType.Movie) {
                    this.posterUrl = poster
                }
            }
        }
    }

    // ------------------------------------------------------------- halaman utama
    // Hanya kategori yang didefinisikan di config (kategori asli situs). Tidak ada "Terbaru"
    // otomatis. Entri "Beranda" hanya cadangan kalau tidak ada satu pun kategori.
    override val mainPage: List<MainPageData>
        get() {
            val cats = config.categories.distinctBy { it.first }
                .ifEmpty { listOf("/" to "Beranda") }
            return mainPageOf(*cats.map { (p, l) -> absUrl(p) to l }.toTypedArray())
        }

    private fun pageUrl(base: String, page: Int): String = when {
        base.contains("{page}") -> base.replace("{page}", page.toString())
        page <= 1 -> base
        config.pageStyle == "path" -> base.trimEnd('/') + "/page/$page/"
        config.pageStyle == "query" ->
            base + (if (base.contains("?")) "&" else "?") + config.pageParam + "=" + page
        else -> base
    }

    override suspend fun getMainPage(page: Int, request: MainPageRequest): HomePageResponse {
        val doc = fetch(pageUrl(request.data, page))
        val home = findCards(doc, 2).mapNotNull { toSearchResult(it) }.distinctBy { it.url }
        if (home.isEmpty() && page == 1) {
            throw ErrorLoadingException(
                "Daftar kosong. Situs mungkin memblokir akses, domain berubah, atau tampilannya berubah."
            )
        }
        val hasNext = (request.data.contains("{page}") || config.pageStyle != "none") && home.isNotEmpty()
        return newHomePageResponse(request.name, home, hasNext)
    }

    // ------------------------------------------------------------------ pencarian
    /** Tautan kartu di beranda asli situs (dicache). Dipakai untuk menolak "pencarian" palsu. */
    private suspend fun homepageHrefs(): Set<String> {
        homeHrefs?.let { return it }
        val set = try {
            findCards(fetch(mainUrl), 1).mapNotNull { cardHref(it) }.toSet()
        } catch (e: Exception) {
            emptySet()
        }
        homeHrefs = set
        return set
    }

    override suspend fun search(query: String): List<SearchResponse> {
        val q = URLEncoder.encode(query, "UTF-8")
        val home = homepageHrefs()
        val templates = (listOfNotNull(searchTemplate) + listOf(config.search) + config.extraSearch + BUILTIN_SEARCH)
            .filter { it.isNotBlank() }.distinct()
        for (t in templates) {
            val doc = try {
                fetch(absUrl(t.replace("{q}", q)))
            } catch (e: Exception) {
                continue
            }
            val results = findCards(doc, 1).mapNotNull { toSearchResult(it) }.distinctBy { it.url }
            if (results.isEmpty()) continue
            // situs sering mengembalikan beranda untuk parameter yang tidak dikenal
            if (home.isNotEmpty() && results.map { it.url }.toSet() == home) continue
            searchTemplate = t
            return results
        }
        return emptyList()
    }

    // -------------------------------------------------------------------- detail
    private fun looksEpisodeUrl(url: String): Boolean = EPISODE_URL.containsMatchIn(url)

    private fun slugTokens(url: String): Set<String> =
        pathOf(url).substringAfterLast('/').lowercase().split("-")
            .filter { it.isNotBlank() && it !in SLUG_NOISE && !it.all { c -> c.isDigit() } }.toSet()

    private fun related(candidate: String, current: String): Boolean {
        val a = slugTokens(candidate)
        val b = slugTokens(current)
        if (a.isEmpty() || b.isEmpty()) return false
        return a.count { it in b } >= Math.ceil(0.7 * a.size).toInt()
    }

    private fun findSeriesLink(doc: Document, url: String): String? {
        val sels = config.seriesLinkHints + listOf(
            "a[href*='/anime/']", "a[href*='/series/']", "a[rel=up]", "div.flir a",
            ".breadcrumb a", "#breadcrumbs a", ".breadcrumbs a"
        )
        for (s in sels) {
            val minSegs = if (s.contains("href*=")) 2 else 1
            for (a in safeSelect(doc, s)) {
                val h = fixUrlNull(a.attr("href").trim()) ?: continue
                if (h.trimEnd('/') == url.trimEnd('/') || looksEpisodeUrl(h) || isRootOrJunk(h)) continue
                if (pathOf(h).split("/").size < minSegs) continue
                if (related(h, url)) return h
            }
        }
        return null
    }

    private fun derivedSeriesUrl(url: String): String? {
        val prefix = config.seriesPrefix
        if (prefix.isBlank()) return null
        val slug = pathOf(url).substringAfterLast('/')
        val base = slug.replace(Regex("(?i)-(episode|eps?|movie|ova|special)\\b.*$"), "")
        if (base.isBlank() || base == slug) return null
        return mainUrl.trimEnd('/') + "/" + prefix.trim('/') + "/" + base + "/"
    }

    private fun isEpisodeAnchor(a: Element, pageUrl: String): Boolean {
        if (!validAnchor(a)) return false
        val href = fixUrlNull(a.attr("href").trim()) ?: return false
        if (href.trimEnd('/') == pageUrl.trimEnd('/') || isRootOrJunk(href)) return false
        val text = a.text().cleanSpaces()
        if (text.length > 90) return false
        return EP_RE.containsMatchIn("$text $href")
    }

    private fun episodeAnchors(doc: Document, pageUrl: String): List<Element> {
        val sels = (listOf(config.episode) + config.extraEpisode + BUILTIN_EPISODE).filter { it.isNotBlank() }.distinct()
        for (s in sels) {
            val found = safeSelect(doc, s).flatMap {
                if (it.tagName() == "a") listOf(it) else it.select("a[href]").toList()
            }
            val good = found.filter { isEpisodeAnchor(it, pageUrl) }.distinctBy { it.attr("href") }
            if (good.size >= 2) return good
        }
        // daftar episode disimpan sebagai HTML di atribut (Kuramanime)
        for (el in doc.select("[data-content]")) {
            val html = el.attr("data-content")
            if (!html.contains("<a")) continue
            val good = Jsoup.parse(html).select("a[href]").filter { isEpisodeAnchor(it, pageUrl) }
                .distinctBy { it.attr("href") }
            if (good.isNotEmpty()) return good
        }
        val all = doc.select("a[href]").filter { isEpisodeAnchor(it, pageUrl) }.distinctBy { it.attr("href") }
        return if (all.size >= 3) all else emptyList()
    }

    private fun epNumber(label: String, href: String): Int? {
        Regex("(?i)(?:episode|eps?|ep)[ ._-]*(\\d{1,4})").find(label)?.groupValues?.get(1)?.toIntOrNull()?.let { return it }
        Regex("(?i)(?:episode|eps?|ep)[-/_ ]*(\\d{1,4})").find(href)?.groupValues?.get(1)?.toIntOrNull()?.let { return it }
        return Regex("(\\d{1,4})").findAll(label).lastOrNull()?.value?.toIntOrNull()
    }

    private suspend fun episodesOf(doc: Document, pageUrl: String): List<Episode> {
        var anchors = episodeAnchors(doc, pageUrl)
        if (anchors.isNotEmpty() && config.episodePages > 1) {
            val seen = anchors.map { it.attr("href") }.toMutableSet()
            val extra = mutableListOf<Element>()
            for (i in 2..config.episodePages) {
                val d = try {
                    fetch(pageUrl.trimEnd('/') + "?page=$i", pageUrl)
                } catch (e: Exception) {
                    break
                }
                val more = episodeAnchors(d, pageUrl).filter { seen.add(it.attr("href")) }
                if (more.isEmpty()) break
                extra.addAll(more)
            }
            anchors = anchors + extra
        }
        if (anchors.isEmpty()) return emptyList()

        data class Raw(val href: String, val label: String, val num: Int?)

        val raws = anchors.mapNotNull { a ->
            val href = fixUrlNull(a.attr("href").trim()) ?: return@mapNotNull null
            val label = a.text().cleanSpaces()
            Raw(href, label, epNumber(label, href))
        }.distinctBy { it.href }

        val numbered = raws.count { it.num != null }
        val unique = raws.mapNotNull { it.num }.toSet().size
        val ordered = if (numbered >= raws.size * 0.7 && unique >= raws.size * 0.8) {
            raws.sortedBy { it.num ?: Int.MAX_VALUE }
        } else if (config.episodesDesc) raws.reversed() else raws

        return ordered.map { r ->
            newEpisode(r.href) {
                this.name = r.label.takeIf { it.isNotBlank() }
                this.episode = r.num
            }
        }
    }

    private fun titleOf(doc: Document): String? {
        for (s in listOf(".anime__details__title h3", "h1.entry-title", "h1.title", "h1")) {
            val t = doc.selectFirst(s)?.text()?.cleanSpaces()
            if (!t.isNullOrBlank()) return t
        }
        val og = doc.selectFirst("meta[property=og:title]")?.attr("content")?.cleanSpaces()
        return og?.replace(Regex("(?i)\\s*[-–|]\\s*" + Regex.escape(name) + "\\s*$"), "")?.takeIf { it.isNotBlank() }
    }

    private fun posterOfPage(doc: Document): String? {
        val sels = listOf(config.poster) + config.extraPoster + BUILTIN_POSTER
        for (s in sels) {
            val el = safeSelect(doc, s).firstOrNull() ?: continue
            posterOf(el)?.let { return it }
        }
        if (config.useOgImage) {
            usableImage(doc.selectFirst("meta[property=og:image]")?.attr("content"))?.let { return it }
        }
        return null
    }

    private fun descOf(doc: Document): String? {
        val sels = listOf(config.desc) + config.extraDesc + BUILTIN_DESC
        for (s in sels) {
            for (el in safeSelect(doc, s)) {
                val t = el.text().cleanSpaces()
                if (t.length >= 40) return t
            }
        }
        if (config.useOgDesc) {
            val og = doc.selectFirst("meta[property=og:description]")?.attr("content")?.cleanSpaces()
            if (!og.isNullOrBlank()) return og
        }
        return doc.selectFirst("meta[name=description]")?.attr("content")?.cleanSpaces()?.takeIf { it.isNotBlank() }
    }

    private fun tagsOf(doc: Document): List<String> {
        val sels = listOf(config.genre) + config.extraGenre + BUILTIN_GENRE
        for (s in sels) {
            val tags = safeSelect(doc, s).map { it.text().cleanSpaces() }
                .filter { it.isNotBlank() && it.length <= 30 }.distinct()
            if (tags.isNotEmpty()) return tags.take(12)
        }
        return emptyList()
    }

    override suspend fun load(url: String): LoadResponse {
        var pageUrl = url
        var doc = fetch(url)
        var episodes: List<Episode> = emptyList()

        if (looksEpisodeUrl(url)) {
            // item beranda berupa halaman episode -> cari halaman seri induknya
            val candidates = listOfNotNull(findSeriesLink(doc, url), derivedSeriesUrl(url)).distinct()
            for (c in candidates) {
                val d = try {
                    fetch(c, url)
                } catch (e: Exception) {
                    continue
                }
                val eps = episodesOf(d, c)
                if (eps.isNotEmpty()) {
                    doc = d
                    pageUrl = c
                    episodes = eps
                    break
                }
            }
        } else {
            episodes = episodesOf(doc, pageUrl)
        }

        val rawTitle = titleOf(doc) ?: throw ErrorLoadingException("Judul tidak ditemukan")
        val title = tidyTitle(rawTitle, episodes.isNotEmpty() && pageUrl != url)
        val poster = posterOfPage(doc)
        val description = descOf(doc)
        val tags = tagsOf(doc)
        val year = Regex("\\(((?:19|20)\\d{2})\\)").find(rawTitle)?.groupValues?.get(1)?.toIntOrNull()

        return if (isAnime) {
            if (episodes.isNotEmpty()) {
                newAnimeLoadResponse(title, pageUrl, TvType.Anime) {
                    this.posterUrl = poster
                    this.plot = description
                    this.tags = tags
                    this.year = year
                    addEpisodes(DubStatus.Subbed, episodes)
                }
            } else {
                newMovieLoadResponse(title, pageUrl, TvType.AnimeMovie, pageUrl) {
                    this.posterUrl = poster
                    this.plot = description
                    this.tags = tags
                    this.year = year
                }
            }
        } else {
            if (episodes.isNotEmpty()) {
                newTvSeriesLoadResponse(title, pageUrl, TvType.TvSeries, episodes) {
                    this.posterUrl = poster
                    this.plot = description
                    this.tags = tags
                    this.year = year
                }
            } else {
                newMovieLoadResponse(title, pageUrl, TvType.Movie, pageUrl) {
                    this.posterUrl = poster
                    this.plot = description
                    this.tags = tags
                    this.year = year
                }
            }
        }
    }

    // -------------------------------------------------------------------- pemutar
    private fun tryBase64(v: String): String? {
        if (v.length < 12 || !Regex("^[A-Za-z0-9+/=_-]+$").matches(v)) return null
        val n = v.replace('-', '+').replace('_', '/')
        val padded = n + "=".repeat((4 - n.length % 4) % 4)
        return try {
            val d = base64Decode(padded)
            if (d.contains("http") || d.contains("<iframe", true)) d else null
        } catch (e: Exception) {
            null
        }
    }

    /** Ubah URL relatif/protocol-relative menjadi absolut terhadap halaman asalnya. */
    private fun resolveUrl(raw: String, base: String): String? {
        val r = raw.trim()
        if (r.isEmpty() || r.startsWith("#") || r.startsWith("javascript", true) ||
            r.startsWith("data:", true) || r.startsWith("about:", true)
        ) return null
        return try {
            URI(base).resolve(r.replace(" ", "%20")).toString()
        } catch (e: Exception) {
            fixUrlNull(r)
        }
    }

    private fun addEmbedUrl(raw: String, pageUrl: String, out: MutableSet<String>) {
        val u = resolveUrl(raw, pageUrl) ?: return
        if (!u.startsWith("http")) return
        if (SKIP_HOSTS.any { u.contains(it, true) }) return
        if (u.trimEnd('/') == pageUrl.trimEnd('/')) return
        out.add(u)
    }

    private fun addEmbed(raw: String, pageUrl: String, out: MutableSet<String>) {
        val v = raw.trim()
        if (v.isEmpty()) return
        val html: String? = when {
            v.startsWith("<") -> v
            v.startsWith("http") || v.startsWith("//") || v.startsWith("/") -> null
            else -> tryBase64(v)
        }
        if (html == null) {
            addEmbedUrl(v, pageUrl, out)
            return
        }
        val parsed = Jsoup.parse(html).select("iframe[src], iframe[data-src], source[src]")
        if (parsed.isNotEmpty()) {
            for (e in parsed) addEmbedUrl(e.attr("src").ifBlank { e.attr("data-src") }, pageUrl, out)
        } else {
            for (m in Regex("https?://[^\\s\"'<>]+").findAll(html)) addEmbedUrl(m.value, pageUrl, out)
        }
    }

    private fun isDirect(u: String): Boolean = DIRECT_VIDEO.containsMatchIn(u)

    private fun typeFor(u: String): ExtractorLinkType =
        if (u.contains(".m3u8", true)) ExtractorLinkType.M3U8 else ExtractorLinkType.VIDEO

    private fun qualityOf(vararg hints: String?): Int {
        for (h in hints) {
            val m = QUALITY_RE.find(h ?: continue) ?: continue
            return m.groupValues[1].toInt()
        }
        return Qualities.Unknown.value
    }

    private fun hostLabel(u: String): String {
        val h = try {
            URI(u).host?.removePrefix("www.")
        } catch (e: Exception) {
            null
        }
        return if (h.isNullOrBlank()) name else "$name $h"
    }

    private fun cleanMedia(u: String): String = u.trimEnd(',', ';', ')', '\\', '.')

    /** Kirim satu tautan langsung ke aplikasi (sekali saja per URL). */
    private suspend fun emitDirect(
        url: String,
        referer: String,
        label: String,
        quality: Int?,
        callback: (ExtractorLink) -> Unit,
        seen: MutableSet<String>
    ): Boolean {
        if (JUNK_MEDIA.containsMatchIn(url) || !seen.add(url)) return false
        callback.invoke(
            newExtractorLink(name, label, url, typeFor(url)) {
                this.referer = referer
                this.quality = quality ?: qualityOf(url, label)
            }
        )
        return true
    }

    /** Semua kandidat embed di sebuah halaman situs (iframe, mirror, atribut data-*, base64). */
    private fun collectEmbeds(doc: Document, pageUrl: String): LinkedHashSet<String> {
        val embeds = LinkedHashSet<String>()
        // gabungkan dengan bawaan supaya data-em dkk tidak hilang kalau Selectors.kt tidak memuatnya
        val attrs = (config.playerAttrs + SiteConfig.DEFAULT_PLAYER_ATTRS).distinct()
        val sels = (listOf(config.player) + config.extraPlayer + BUILTIN_PLAYER).filter { it.isNotBlank() }.distinct()
        for (s in sels) {
            for (el in safeSelect(doc, s)) {
                for (a in (if (el.tagName() == "a") ANCHOR_ATTRS else attrs)) {
                    val v = el.attr(a)
                    if (v.isNotBlank()) addEmbed(v, pageUrl, embeds)
                }
            }
        }
        return embeds
    }

    /** <video><source> yang langsung ada di halaman. */
    private suspend fun pageSources(
        doc: Document,
        pageUrl: String,
        label: String,
        callback: (ExtractorLink) -> Unit,
        seen: MutableSet<String>
    ): Boolean {
        var ok = false
        for (src in doc.select("video source[src], video[src]")) {
            val u = resolveUrl(src.attr("src"), pageUrl) ?: continue
            if (!u.startsWith("http")) continue
            val q = src.attr("size").toIntOrNull() ?: src.attr("res").toIntOrNull()
            ok = emitDirect(u, pageUrl, label, q, callback, seen) || ok
        }
        return ok
    }

    /**
     * Mengubah satu embed menjadi tautan putar:
     *  1. extractor bawaan CloudStream (kalau host dikenal),
     *  2. kalau tidak ada hasil: buka halaman embed, cari m3u8/mp4 (termasuk JS yang di-pack),
     *  3. kalau masih kosong: ikuti iframe di dalam embed (maksimal MAX_EMBED_DEPTH tingkat).
     * Semua langkah dibungkus try/catch supaya satu host rusak tidak menggagalkan host lain.
     */
    private suspend fun resolveEmbed(
        embed: String,
        referer: String,
        depth: Int,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit,
        seen: MutableSet<String>,
        visited: MutableSet<String>,
        log: MutableList<String>
    ): Boolean {
        if (!visited.add(embed)) return false
        val label = hostLabel(embed)
        val short = hostLabel(embed).removePrefix(name).trim()
        val tag = "d$depth $short"
        if (isDirect(embed)) {
            log.add("$tag: langsung")
            return emitDirect(embed, referer, label, null, callback, seen)
        }

        val viaExtractor = try {
            loadExtractor(embed, referer, subtitleCallback, callback)
        } catch (e: Exception) {
            log.add("$tag: extractor error ${e.javaClass.simpleName}")
            false
        }
        if (viaExtractor) {
            log.add("$tag: extractor bawaan OK")
            return true
        }
        if (depth >= MAX_EMBED_DEPTH) return false

        val resp = try {
            app.get(embed, referer = referer)
        } catch (e: Exception) {
            log.add("$tag: gagal dibuka ${e.javaClass.simpleName}")
            return false
        }
        val html = resp.text
        log.add("$tag: extractor tidak kenal, halaman HTTP ${resp.code} ${html.length}B")

        val body = html.replace("\\/", "/")
        val unpacked = if (body.contains("eval(function(p,a,c,k,e,d)")) {
            try {
                getAndUnpack(body).replace("\\/", "/")
            } catch (e: Exception) {
                ""
            }
        } else ""

        var ok = false
        for (m in MEDIA_RE.findAll(body + "\n" + unpacked)) {
            val u = cleanMedia(m.value)
            if (SKIP_HOSTS.any { u.contains(it, true) }) continue
            ok = emitDirect(u, embed, label, null, callback, seen) || ok
        }

        val parsed = Jsoup.parse(html)
        ok = pageSources(parsed, embed, label, callback, seen) || ok
        if (ok) {
            log.add("$tag: media ditemukan di halaman embed")
            return true
        }

        val nested = LinkedHashSet<String>()
        for (e in parsed.select("iframe[src], iframe[data-src]")) {
            addEmbedUrl(e.attr("src").ifBlank { e.attr("data-src") }, embed, nested)
        }
        log.add("$tag: tanpa media langsung, iframe bersarang ${nested.size}")
        for (n in nested) {
            ok = resolveEmbed(n, embed, depth + 1, subtitleCallback, callback, seen, visited, log) || ok
        }
        return ok
    }

    /**
     * Pemutar yang dirender JavaScript: muat halaman di WebView tersembunyi dan tangkap
     * request .m3u8/.mp4 yang dikirim pemutarnya. Hanya dipakai kalau semua cara lain gagal.
     */
    private suspend fun sniff(
        url: String,
        referer: String,
        label: String,
        callback: (ExtractorLink) -> Unit,
        seen: MutableSet<String>,
        log: MutableList<String>
    ): Boolean {
        val short = hostLabel(url).removePrefix(name).trim()
        val found = try {
            app.get(url, referer = referer, interceptor = WebViewResolver(SNIFF_RE)).url
        } catch (e: Exception) {
            log.add("webview $short: error ${e.javaClass.simpleName}")
            return false
        }
        val good = SNIFF_RE.containsMatchIn(found) && SKIP_HOSTS.none { found.contains(it, true) }
        log.add("webview $short: " + (if (good) "dapat media" else "tidak ada media"))
        return good && emitDirect(found, url, label, null, callback, seen)
    }

    /** Terakhir: URL bergaya embed yang tertulis di dalam script halaman. */
    private fun scriptEmbedCandidates(doc: Document, pageUrl: String): List<String> {
        val out = LinkedHashSet<String>()
        val html = doc.html().replace("\\/", "/")
        for (m in SCRIPT_EMBED_RE.findAll(html)) {
            val u = m.value.trimEnd(',', ';', ')', '\\')
            if (ASSET_EXT.containsMatchIn(u)) continue
            addEmbedUrl(u, pageUrl, out)
        }
        return out.toList()
    }

    /** Tombol "Nonton/Tonton" yang membuka halaman pemutar terpisah (bukan menu navigasi). */
    private fun watchLinks(doc: Document, pageUrl: String): List<String> =
        doc.select("a[href]")
            .filter { a -> a.parents().none { it.tagName() in NAV_TAGS } }
            .filter { WATCH_TEXT.containsMatchIn(it.text()) }
            .mapNotNull { resolveUrl(it.attr("href"), pageUrl) }
            .filter { it.startsWith("http") && it.trimEnd('/') != pageUrl.trimEnd('/') && !isRootOrJunk(it) }
            .distinct()
            .take(2)

    override suspend fun loadLinks(
        data: String,
        isCasting: Boolean,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit
    ): Boolean {
        val doc = fetch(data)
        val seen = HashSet<String>()      // URL yang sudah dikirim ke aplikasi
        val visited = HashSet<String>()   // embed yang sudah dibuka
        val log = ArrayList<String>()     // jejak diagnosis (logcat + pesan error)
        var ok = pageSources(doc, data, name, callback, seen)

        val embeds = collectEmbeds(doc, data)
        val nIframe = doc.select("iframe").size
        val nOption = doc.select("option").size
        val nVideo = doc.select("video").size
        val pageTitle = doc.title().take(30)
        log.add("halaman ${doc.html().length}B title=$pageTitle iframe=$nIframe option=$nOption video=$nVideo embed=${embeds.size}")
        for (u in embeds) {
            ok = resolveEmbed(u, data, 0, subtitleCallback, callback, seen, visited, log) || ok
        }

        // pemutar ada di halaman lain (tombol "Nonton")
        if (!ok) {
            for (w in watchLinks(doc, data)) {
                val d = try {
                    fetch(w, data)
                } catch (e: Exception) {
                    continue
                }
                val es = collectEmbeds(d, w)
                val wShort = w.substringAfter("://").take(40)
                log.add("halaman nonton $wShort embed=${es.size}")
                ok = pageSources(d, w, name, callback, seen) || ok
                for (u in es) {
                    ok = resolveEmbed(u, w, 0, subtitleCallback, callback, seen, visited, log) || ok
                }
                if (ok) break
            }
        }

        // cadangan: media langsung / URL embed yang tertulis di script
        if (!ok) {
            val html = doc.html().replace("\\/", "/")
            for (m in MEDIA_RE.findAll(html)) {
                val u = cleanMedia(m.value)
                if (SKIP_HOSTS.any { u.contains(it, true) }) continue
                ok = emitDirect(u, data, name, null, callback, seen) || ok
            }
        }
        if (!ok) {
            val cands = scriptEmbedCandidates(doc, data).take(8)
            log.add("kandidat embed dari script=${cands.size}")
            for (u in cands) {
                ok = resolveEmbed(u, data, 0, subtitleCallback, callback, seen, visited, log) || ok
            }
        }

        // terakhir: WebView (maksimal 3 percobaan: 2 embed pertama, lalu halaman episode)
        if (!ok) {
            for (u in embeds.take(2)) {
                ok = sniff(u, data, hostLabel(u), callback, seen, log) || ok
                if (ok) break
            }
            if (!ok) ok = sniff(data, "$mainUrl/", name, callback, seen, log)
        }

        if (!ok) {
            val msg = "Tautan tidak ditemukan [$name] " + log.joinToString(" | ")
            Log.d("AdaptiveProvider", msg)
            throw ErrorLoadingException(msg.take(600))
        }
        return true
    }

    companion object {
        private val NAV_TAGS = setOf("header", "footer", "nav", "aside")
        private val IMG_ATTRS = listOf("data-src", "data-lazy-src", "data-original", "data-lazyload", "data-setbg", "data-bg", "src")
        private val ANCHOR_ATTRS = listOf(
            "data-url", "data-src", "data-iframe", "data-embed", "data-em", "data-link", "data-player", "href"
        )
        private const val MAX_EMBED_DEPTH = 3
        private val SNIFF_RE = Regex("""(?i)(\.m3u8|\.mp4|googlevideo\.com/videoplayback)""")
        private val MEDIA_RE = Regex("""https?://[^\s"'<>\\]+?\.(?:m3u8|mp4)[^\s"'<>\\]*""")
        private val QUALITY_RE = Regex("(?<!\\d)(2160|1440|1080|720|480|360|240)(?!\\d)")
        private val JUNK_MEDIA = Regex("(?i)(doubleclick|/ads?/|adserver|banner|promo|sprite)")
        private val WATCH_TEXT = Regex("(?i)\\b(nonton|tonton|watch|play|streaming)\\b")
        private val ASSET_EXT = Regex("(?i)\\.(js|css|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|json|xml|php)(\\?|$)")
        private val SCRIPT_EMBED_RE = Regex(
            """https?://[^\s"'<>\\]+(?:embed|/e/|/v/|player|iframe|stream)[^\s"'<>\\]*""",
            RegexOption.IGNORE_CASE
        )
        private val JUNK_FIRST_SEGMENTS = setOf(
            "genre", "genres", "category", "kategori", "tag", "page", "author", "login", "register",
            "daftar", "dmca", "contact", "kontak", "about", "privacy", "feed", "search", "jadwal", "schedule"
        )
        private val SLUG_NOISE = setOf(
            "episode", "eps", "ep", "subtitle", "sub", "indonesia", "indo", "movie", "ova", "special",
            "nonton", "streaming", "download", "the", "a", "of", "end", "batch"
        )
        private val SKIP_HOSTS = listOf(
            "facebook.com", "disqus.com", "googletagmanager.com", "google.com/recaptcha", "histats.com",
            "doubleclick", "youtube.com", "youtu.be", "twitter.com", "instagram.com", "t.me/", "wa.me/"
        )
        private val EP_RE = Regex("(?i)(episode|\\beps?\\b[ ._-]?\\d+|\\bep[ ._-]?\\d+|/eps?[-/]|-episode-)")
        private val EPISODE_URL = Regex("(?i)(-episode-\\d|/episode/|/eps?[-/]\\d|-eps?-\\d)")
        private val SERIES_HINT = Regex("(?i)(\\bseries\\b|\\bseason\\b|\\bs\\d{1,2}e\\d{1,3}\\b|\\bepisode\\b|/series/|/tv/|/drama/)")
        private val DIRECT_VIDEO = Regex("(?i)\\.(m3u8|mp4|mkv|webm)(\\?|$)")

        private val TITLE_SELECTORS = listOf(
            "h2", "h3", "h4", "h5", ".tt h2", ".tt", ".entry-title", ".jdlflm", ".poster-title",
            "[class*=title]", ".name"
        )
        private val BUILTIN_ITEMS = listOf(
            "div.listupd article", "article.bs", "div.product__item", "div.venz ul li", "ul.chivsrc li",
            "div.ml-item", "article.item", "div.bsx", "li.item", "article", "div.item"
        )
        private val BUILTIN_SEARCH = listOf(
            "/?s={q}", "/search?keyword={q}", "/search?q={q}", "/anime?search={q}&order_by=latest",
            "/?s={q}&post_type=anime", "/search/{q}", "/?search={q}", "/search?query={q}"
        )
        private val BUILTIN_EPISODE = listOf(
            "ul.daftar li a", "div.eplister ul li a", ".episodelist ul li a", "#episodeLists a",
            "ul.episodios li a", ".episodes a", ".eps-list a", "ul#episode_by_temp li a", "ul.episodelist a"
        )
        private val BUILTIN_PLAYER = listOf(
            "iframe", "iframe[data-src]", "#embed_holder iframe", ".mobius select option", "select.mirror option",
            "option[data-em]", "[data-video]", "[data-embed]", "[data-iframe]", "[data-url]",
            "ul#player-list li a", "#player-list a", ".server-list a", "a[data-server]", "ul.server li a"
        )
        private val BUILTIN_POSTER = listOf(
            ".anime__details__pic", ".fotoanime img", ".thumb img", ".poster img", "img.wp-post-image",
            "img[class*=poster]", "img[class*=cover]", ".detail img", "figure img", ".entry-content img"
        )
        private val BUILTIN_DESC = listOf(
            ".synopsis", ".sinopsis", ".sinopc", "[itemprop=description]", "#synopsisField",
            ".anime__details__text p", ".description", ".desc", ".summary", ".entry-content p"
        )
        private val BUILTIN_GENRE = listOf(
            "a[rel=tag]", ".genre a", ".genres a", ".genxed a", ".mgen a",
            "a[href*='/genre/']", "a[href*='/genres/']", "a[href*='/properties/genre']",
            "a[href*='/category/']", "a[href*='/kategori/']"
        )
    }
}
