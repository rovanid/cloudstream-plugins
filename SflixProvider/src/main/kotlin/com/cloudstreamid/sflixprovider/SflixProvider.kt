package com.cloudstreamid.sflixprovider

import com.cloudstreamid.common.AdaptiveProvider
import com.cloudstreamid.common.SiteConfig
import com.lagradost.cloudstream3.*

class SflixProvider : AdaptiveProvider() {
    // JANGAN ubah format baris mainUrl ini, dipakai apply_domains.py
    override var mainUrl = "https://ssflix.pro"
    override var name = "Sflix"
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
        // Beranda "/" hanya halaman SEO; daftar film ada di halaman-halaman ini (dari menu situs).
        // Format paginasi belum diketahui: "?page={page}" adalah tebakan.
        categories = listOf(
            "/latest-movies?page={page}" to "Film Terbaru",
            "/popular-movies?page={page}" to "Film Populer",
            "/tv-series?page={page}" to "Serial TV",
            "/top-imdb?page={page}" to "Top IMDb",
            "/anime?page={page}" to "Anime"
        ),
        // Situs ini memuat daftar & pemutar lewat JavaScript; hasil bisa kosong di beberapa domain.
    )
}
