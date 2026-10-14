package com.cloudstreamid.common

/**
 * Konfigurasi satu situs. Field tanpa "extra" berasal dari Selectors.kt (auto-detect).
 * Semua selector berupa KANDIDAT: mesin mencoba berurutan lalu memakai yang benar-benar
 * menghasilkan data di perangkat pengguna, jadi selector yang salah tidak lagi membuat
 * daftar kosong.
 */
data class SiteConfig(
    val item: String = "",
    val title: String = "",
    val search: String = "",
    val pageStyle: String = "path",          // path | query | none
    val pageParam: String = "page",
    val poster: String = "",
    val desc: String = "",
    val genre: String = "",
    val episode: String = "",
    val episodesDesc: Boolean = true,
    val useOgImage: Boolean = true,
    val useOgDesc: Boolean = true,
    val player: String = "iframe",
    val playerAttrs: List<String> = DEFAULT_PLAYER_ATTRS,
    val categories: List<Pair<String, String>> = listOf("/" to "Terbaru"),

    // ---- tuning manual per situs (opsional) ----
    val extraCategories: List<Pair<String, String>> = emptyList(),
    val extraItems: List<String> = emptyList(),
    val extraTitle: List<String> = emptyList(),
    val extraSearch: List<String> = emptyList(),
    val extraPoster: List<String> = emptyList(),
    val extraDesc: List<String> = emptyList(),
    val extraGenre: List<String> = emptyList(),
    val extraEpisode: List<String> = emptyList(),
    val extraPlayer: List<String> = emptyList(),
    val seriesLinkHints: List<String> = emptyList(),
    /** Contoh "/anime/": item beranda yang berupa halaman episode diubah ke halaman seri. */
    val seriesPrefix: String = "",
    /** Mengambil episode dari ?page=1..N (Kuramanime). 1 = tanpa paginasi. */
    val episodePages: Int = 1,
) {
    companion object {
        val DEFAULT_PLAYER_ATTRS = listOf(
            "src", "data-src", "data-lazy-src", "data-litespeed-src", "value",
            "data-video", "data-embed", "data-iframe", "data-url", "data-em"
        )
    }
}
