package com.cloudstreamid.sflixprovider

import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.utils.*
import org.jsoup.nodes.Element
import java.net.URLEncoder

class SflixProvider : MainAPI() {
    // JANGAN ubah format baris mainUrl ini, dipakai apply_domains.py
    override var mainUrl = "https://sflix.example"
    override var name = "Sflix"
    override var lang = "id"
    override val hasMainPage = true
    override val supportedTypes = setOf(TvType.Movie, TvType.TvSeries)

    // Kategori dan semua selector diisi otomatis oleh detect_selectors.py (lihat Selectors.kt)
    override val mainPage = mainPageOf(
        *Sel.CATEGORIES.map { (path, label) -> "$mainUrl$path" to label }.toTypedArray()
    )

    private val imgAttrs = listOf("data-src", "data-lazy-src", "data-original", "data-lazyload", "src")
    private val skipHosts = listOf("facebook.com", "disqus.com", "googletagmanager.com", "google.com/recaptcha")

    private fun firstNotBlank(vararg v: String?): String? =
        v.firstOrNull { !it.isNullOrBlank() }?.trim()

    private fun Element.pick(sel: String): Element? =
        if (sel.isBlank()) null else selectFirst(sel)

    private fun Element.imageUrl(): String? {
        val img = (if (tagName() == "img") this else selectFirst("img")) ?: return null
        for (a in imgAttrs) {
            val v = img.attr(a)
            if (v.isNotBlank() && !v.startsWith("data:")) return fixUrlNull(v)
        }
        return null
    }

    private fun pageUrl(base: String, page: Int): String = when {
        page <= 1 -> base
        Sel.PAGE_STYLE == "path" -> base.trimEnd('/') + "/page/$page/"
        Sel.PAGE_STYLE == "query" ->
            base + (if (base.contains("?")) "&" else "?") + Sel.PAGE_PARAM + "=" + page
        else -> base
    }

    override suspend fun getMainPage(page: Int, request: MainPageRequest): HomePageResponse {
        val document = app.get(pageUrl(request.data, page)).document
        val home = document.select(Sel.ITEM).mapNotNull { it.toSearchResult() }
        return newHomePageResponse(request.name, home, hasNext = Sel.PAGE_STYLE != "none")
    }

    private fun Element.toSearchResult(): SearchResponse? {
        val link = if (tagName() == "a" && hasAttr("href")) this else selectFirst("a[href]")
        val href = fixUrlNull(link?.attr("href")) ?: return null
        val title = firstNotBlank(
            pick(Sel.TITLE)?.text(),
            link?.attr("title"),
            selectFirst("img")?.attr("alt")
        ) ?: return null
        val poster = imageUrl()
        return newMovieSearchResponse(title, href, TvType.Movie) {
            this.posterUrl = poster
        }
    }

    override suspend fun search(query: String): List<SearchResponse> {
        if (Sel.SEARCH.isBlank()) return emptyList()
        val q = URLEncoder.encode(query, "UTF-8")
        val document = app.get(mainUrl + Sel.SEARCH.replace("{q}", q)).document
        return document.select(Sel.ITEM).mapNotNull { it.toSearchResult() }
    }

    override suspend fun load(url: String): LoadResponse {
        val document = app.get(url).document
        val title = firstNotBlank(
            document.selectFirst("h1")?.text(),
            document.selectFirst("meta[property=og:title]")?.attr("content")
        ) ?: throw ErrorLoadingException("Judul tidak ditemukan")

        val ogImage = if (Sel.USE_OG_IMAGE)
            document.selectFirst("meta[property=og:image]")?.attr("content") else null
        val poster = fixUrlNull(firstNotBlank(ogImage, document.pick(Sel.POSTER)?.imageUrl()))

        val ogDesc = if (Sel.USE_OG_DESC)
            document.selectFirst("meta[property=og:description]")?.attr("content") else null
        val description = firstNotBlank(document.pick(Sel.DESC)?.text(), ogDesc)

        val tags = if (Sel.GENRE.isBlank()) emptyList() else
            document.select(Sel.GENRE).map { it.text().trim() }.filter { it.isNotBlank() }.distinct()

        val episodes = if (Sel.EPISODE.isBlank()) emptyList() else
            document.select(Sel.EPISODE).mapNotNull { a ->
                val href = fixUrlNull(a.attr("href")) ?: return@mapNotNull null
                val label = a.text().trim()
                newEpisode(href) {
                    this.name = label
                    this.episode = Regex("(\\d+)").find(label)?.value?.toIntOrNull()
                }
            }.distinctBy { it.data }.let { if (Sel.EPISODES_DESC) it.reversed() else it }

        if (episodes.isNotEmpty()) {
            return newTvSeriesLoadResponse(title, url, TvType.TvSeries, episodes) {
                this.posterUrl = poster
                this.plot = description
                this.tags = tags
            }
        }
        return newMovieLoadResponse(title, url, TvType.Movie, url) {
            this.posterUrl = poster
            this.plot = description
            this.tags = tags
        }
    }

    override suspend fun loadLinks(
        data: String,
        isCasting: Boolean,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit
    ): Boolean {
        if (Sel.PLAYER.isBlank()) return false
        val document = app.get(data).document
        var found = false
        for (el in document.select(Sel.PLAYER)) {
            val src = Sel.PLAYER_ATTRS.firstNotNullOfOrNull { a ->
                el.attr(a).takeIf { it.isNotBlank() }
            } ?: continue
            if (!(src.startsWith("http") || src.startsWith("//"))) continue
            if (skipHosts.any { src.contains(it) }) continue
            loadExtractor(fixUrl(src), data, subtitleCallback, callback)
            found = true
        }
        return found
    }
}
