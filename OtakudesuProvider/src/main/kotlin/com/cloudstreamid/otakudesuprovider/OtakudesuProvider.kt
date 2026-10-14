package com.cloudstreamid.otakudesuprovider

import com.cloudstreamid.common.AdaptiveProvider
import com.cloudstreamid.common.SiteConfig
import com.lagradost.cloudstream3.*

class OtakudesuProvider : AdaptiveProvider() {
    // JANGAN ubah format baris mainUrl ini, dipakai apply_domains.py
    override var mainUrl = "https://otakudesu.blog"
    override var name = "Otakudesu"
    override var lang = "id"
    override val supportedTypes = setOf(TvType.Anime, TvType.AnimeMovie, TvType.OVA)

    // Nilai Sel.* diisi otomatis oleh detect_selectors.py (kalau situs bisa dijangkau dari CI).
    // Semuanya hanya KANDIDAT: mesin memilih yang bekerja saat dijalankan di aplikasi.
    // Bagian "tuning" di bawah adalah pengetahuan struktur situs dan tidak ditimpa script.
    override val config = SiteConfig(
        item = Sel.ITEM,
        title = Sel.TITLE,
        search = Sel.SEARCH,
        pageStyle = Sel.PAGE_STYLE,
        pageParam = Sel.PAGE_PARAM,
        poster = Sel.POSTER,
        desc = Sel.DESC,
        genre = Sel.GENRE,
        episode = Sel.EPISODE,
        episodesDesc = Sel.EPISODES_DESC,
        useOgImage = Sel.USE_OG_IMAGE,
        useOgDesc = Sel.USE_OG_DESC,
        player = Sel.PLAYER,
        playerAttrs = Sel.PLAYER_ATTRS,
        // Kategori ASLI situs (ditulis manual, tidak ditimpa script). Tanpa "Terbaru" otomatis.
        categories = listOf(
            "/ongoing-anime/page/{page}/" to "Ongoing",
            "/complete-anime/page/{page}/" to "Completed"
        ),
        // Beranda berisi episode terbaru; load() mencari tautan "/anime/..." induknya
        extraItems = listOf("div.venz ul li", "ul.chivsrc li"),
        extraTitle = listOf(".jdlflm", "h2"),
        extraSearch = listOf("/?s={q}&post_type=anime"),
        seriesLinkHints = listOf("div.flir a[href*='/anime/']", "a[href*='/anime/']"),
        extraEpisode = listOf("div.episodelist ul li a"),
        extraPoster = listOf(".fotoanime img"),
        extraDesc = listOf(".sinopc"),
        extraGenre = listOf(".infozingle a[href*='/genres/']"),
        extraPlayer = listOf("#embed_holder iframe", ".responsive-embed-stream iframe"),
    )
}
