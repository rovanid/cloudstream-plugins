package com.cloudstreamid.common

import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.network.CloudflareKiller
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
    private var homeHrefs: Set<String> = emptySet()

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
    override val mainPage: List<MainPageData>
        get() = mainPageOf(
            *(config.categories + config.extraCategories)
                .distinctBy { it.first }
                .map { (p, l) -> absUrl(p) to l }
                .toTypedArray()
        )

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
        if (page == 1 && homeHrefs.isEmpty()) homeHrefs = home.map { it.url }.toSet()
        val hasNext = (request.data.contains("{page}") || config.pageStyle != "none") && home.isNotEmpty()
        return newHomePageResponse(request.name, home, hasNext)
    }

    // ------------------------------------------------------------------ pencarian
    override suspend fun search(query: String): List<SearchResponse> {
        val q = URLEncoder.encode(query, "UTF-8")
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
            if (homeHrefs.isNotEmpty() && results.map { it.url }.toSet() == homeHrefs) continue
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
        return try {
            val d = base64Decode(v)
            if (d.contains("http") || d.contains("<iframe", true)) d else null
        } catch (e: Exception) {
            null
        }
    }

    private fun addEmbedUrl(raw: String, pageUrl: String, out: MutableSet<String>) {
        var u = raw.trim()
        if (u.startsWith("//")) u = "https:$u"
        else if (u.startsWith("/")) u = fixUrl(u)
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

    override suspend fun loadLinks(
        data: String,
        isCasting: Boolean,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit
    ): Boolean {
        val doc = fetch(data)
        var ok = false

        // <video><source size=720> (Kuramanime dan sejenisnya)
        for (src in doc.select("video source[src], video[src]")) {
            val u = fixUrlNull(src.attr("src").trim()) ?: continue
            val q = src.attr("size").toIntOrNull() ?: src.attr("res").toIntOrNull()
            callback.invoke(
                newExtractorLink(name, name, u, typeFor(u)) {
                    this.referer = "$mainUrl/"
                    this.quality = q ?: Qualities.Unknown.value
                }
            )
            ok = true
        }

        val embeds = LinkedHashSet<String>()
        val sels = (listOf(config.player) + config.extraPlayer + BUILTIN_PLAYER).filter { it.isNotBlank() }.distinct()
        for (s in sels) {
            for (el in safeSelect(doc, s)) {
                val attrs = if (el.tagName() == "a") ANCHOR_ATTRS else config.playerAttrs
                for (a in attrs) {
                    val v = el.attr(a)
                    if (v.isNotBlank()) addEmbed(v, data, embeds)
                }
            }
        }

        if (embeds.isEmpty() && !ok) {
            val html = doc.html().replace("\\/", "/")
            for (m in Regex("""https?://[^\s"'<>\\]+?\.(?:m3u8|mp4)[^\s"'<>\\]*""").findAll(html)) {
                addEmbedUrl(m.value, data, embeds)
            }
        }

        for (u in embeds) {
            if (isDirect(u)) {
                callback.invoke(
                    newExtractorLink(name, name, u, typeFor(u)) {
                        this.referer = "$mainUrl/"
                        this.quality = Qualities.Unknown.value
                    }
                )
                ok = true
            } else {
                val r = loadExtractor(u, data, subtitleCallback, callback)
                ok = ok || r
            }
        }
        return ok
    }

    companion object {
        private val NAV_TAGS = setOf("header", "footer", "nav", "aside")
        private val IMG_ATTRS = listOf("data-src", "data-lazy-src", "data-original", "data-lazyload", "data-setbg", "data-bg", "src")
        private val ANCHOR_ATTRS = listOf("data-url", "data-src", "data-iframe", "data-embed", "data-em", "href")
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
