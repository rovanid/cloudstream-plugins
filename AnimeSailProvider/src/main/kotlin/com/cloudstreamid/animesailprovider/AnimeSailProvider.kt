package com.cloudstreamid.animesailprovider

import com.cloudstreamid.common.AdaptiveProvider
import com.cloudstreamid.common.SiteConfig
import com.lagradost.cloudstream3.*

class AnimeSailProvider : AdaptiveProvider() {
    // JANGAN ubah format baris mainUrl ini, dipakai apply_domains.py
    override var mainUrl = "https://anisail.com"
    override var name = "AnimeSail"
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
            "/movie-terbaru/page/{page}/" to "Movie Terbaru",
            "/genres/donghua/page/{page}/" to "Donghua"
        ),
        // Beranda AnimeSail berisi halaman EPISODE; load() otomatis naik ke halaman seri /anime/slug/
        extraItems = listOf("div.listupd article", "article.bs"),
        extraTitle = listOf(".tt h2"),
        seriesPrefix = "/anime/",
        seriesLinkHints = listOf("a[href*='/anime/']"),
        extraEpisode = listOf("ul.daftar li a"),
        extraPlayer = listOf(".mobius .mirror option", "select.mirror option"),
        extraDesc = listOf(".entry-content p"),
    )
}
