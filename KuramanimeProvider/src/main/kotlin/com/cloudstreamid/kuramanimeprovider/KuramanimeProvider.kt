package com.cloudstreamid.kuramanimeprovider

import com.cloudstreamid.common.AdaptiveProvider
import com.cloudstreamid.common.SiteConfig
import com.lagradost.cloudstream3.*

class KuramanimeProvider : AdaptiveProvider() {
    // JANGAN ubah format baris mainUrl ini, dipakai apply_domains.py
    override var mainUrl = "https://v20.kuramanime.ing"
    override var name = "Kuramanime"
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
        // Kategori ASLI situs (opsi urutan di /anime). Ditulis manual, tidak ditimpa script.
        categories = listOf(
            "/anime?order_by=latest&page={page}" to "Terbaru",
            "/anime?order_by=updated&page={page}" to "Baru Diperbarui",
            "/anime?order_by=popular&page={page}" to "Terpopuler",
            "/anime?order_by=ascending&page={page}" to "A-Z"
        ),
        extraItems = listOf("div#animeList div.product__item", "div.product__item"),
        extraTitle = listOf(".product__item__text h5"),
        extraSearch = listOf("/anime?search={q}&order_by=latest"),
        extraPoster = listOf(".anime__details__pic"),
        extraDesc = listOf("#synopsisField", ".anime__details__text p"),
        extraEpisode = listOf("#episodeLists"),
        episodePages = 8,
        extraPlayer = listOf("video#player source", "select#changeServer option"),
    )
}
