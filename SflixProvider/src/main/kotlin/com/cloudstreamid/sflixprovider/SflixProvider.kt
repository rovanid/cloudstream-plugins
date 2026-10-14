package com.cloudstreamid.sflixprovider

import com.cloudstreamid.common.AdaptiveProvider
import com.cloudstreamid.common.SiteConfig
import com.lagradost.cloudstream3.*

class SflixProvider : AdaptiveProvider() {
    // JANGAN ubah format baris mainUrl ini, dipakai apply_domains.py
    override var mainUrl = "https://sflix.blue"
    override var name = "Sflix"
    override var lang = "en"
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
        // Kategori ASLI sflix.blue (dari menu situs / tab di /movies/ dan beranda).
        // Format halaman berikutnya belum terverifikasi: dicoba "/page/N/" lalu "?page=N" (lihat catatan).
        categories = listOf(
            "/latest-movie/" to "Film Terbaru",
            "/popular-movie/" to "Film Populer",
            "/top-rated-movie/" to "Film Rating Tertinggi",
            "/upcoming-movie/" to "Film Segera Tayang",
            "/airing-today-tv/" to "Serial Tayang Hari Ini",
            "/popular-tv/" to "Serial Populer",
            "/on-the-air-tv/" to "Serial Sedang Tayang",
            "/top-rated-tv/" to "Serial Rating Tertinggi"
        ),
        // Struktur kartu (dari HTML /movies/): div.ml-item > a.ml-mask[title][href] > img.mli-thumb[data-original]
        extraItems = listOf("div.ml-item"),
        extraTitle = listOf(".mli-info h2", "a.ml-mask[title]"),
        extraPoster = listOf("img.mli-thumb", "img.lazy"),
        // Detail film: /movie/<slug>-<id>/   Detail serial: /tv/<id>/<slug>/
        seriesLinkHints = listOf("/tv/"),
    )
}
