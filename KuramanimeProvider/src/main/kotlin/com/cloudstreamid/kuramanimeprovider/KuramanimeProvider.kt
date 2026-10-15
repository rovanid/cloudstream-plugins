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
        // Kategori dari menu asli situs. order_by=latest = tampilan kartu berposter (terbukti di fixture
        // hanya untuk /quick/ongoing; kategori lain memakai pola URL yang sama tetapi belum diuji ke situs).
        // "Segera Tayang" sengaja tidak dimasukkan: belum punya episode.
        categories = listOf(
            "/quick/ongoing?order_by=latest&page={page}" to "Sedang Tayang",
            "/quick/finished?order_by=latest&page={page}" to "Selesai Tayang",
            "/quick/movie?order_by=latest&page={page}" to "Film Layar Lebar",
            "/quick/donghua?order_by=latest&page={page}" to "Donghua"
        ),
        // Daftar episode bisa berhalaman (?page=N). Mesin berhenti di halaman pertama yang tidak
        // menambah episode baru, jadi batas besar tidak menambah permintaan untuk seri pendek.
        episodePages = 30,
    )

    /**
     * Kartu beranda/kategori Kuramanime menautkan ke halaman EPISODE terbaru
     * (/anime/ID/slug/episode/N). Pencarian halaman seri di AdaptiveProvider membandingkan slug dari
     * segmen URL terakhir ("N"), jadi gagal dan judul terbuka sebagai film satu tautan.
     * Di sini URL dipotong ke halaman seri /anime/ID/slug sebelum diproses mesin.
     */
    override suspend fun load(url: String): LoadResponse {
        val res = super.load(seriesUrlOf(url))
        // tautan genre di situs berbentuk "Action," (koma ikut teks)
        res.tags = res.tags
            ?.map { it.trim().trimEnd(',').trim() }
            ?.filter { it.isNotEmpty() }
            ?.distinct()
        return res
    }

    private fun seriesUrlOf(url: String): String =
        if (url.contains("/anime/") && url.contains("/episode/")) url.substringBefore("/episode/") else url
}
