package com.cloudstreamid.layarkaca21provider

import com.cloudstreamid.common.AdaptiveProvider
import com.cloudstreamid.common.SiteConfig
import com.lagradost.cloudstream3.*

class LayarKaca21Provider : AdaptiveProvider() {
    // JANGAN ubah format baris mainUrl ini, dipakai apply_domains.py
    override var mainUrl = "https://tv12.lk21official.cc"
    override var name = "LayarKaca21"
    override var lang = "id"
    override val supportedTypes = setOf(TvType.Movie, TvType.TvSeries)

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
            "/populer/page/{page}" to "Terpopuler",
            "/rating/page/{page}" to "Rating Tertinggi",
            "/latest/page/{page}" to "Upload Terbaru"
        ),
        extraItems = listOf("article"),
        extraTitle = listOf(".poster-title", "h3"),
        extraDesc = listOf(".synopsis", "blockquote"),
        extraPlayer = listOf("ul#player-list li a", "iframe#main-player", "#player-list a"),
    )
}
