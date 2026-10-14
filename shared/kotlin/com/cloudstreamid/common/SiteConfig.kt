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
    /**
     * Kategori beranda aplikasi: pasangan (path/URL, nama). HANYA kategori yang benar-benar ada
     * di situs. Tidak ada kategori "Terbaru" otomatis. Kalau dikosongkan, mesin memakai satu
     * entri "Beranda" (halaman utama situs) supaya plugin tidak kosong sama sekali.
     * Path relatif ikut domain di mainUrl, jadi aman saat domain diganti lewat domains.yml.
     */
    val categories: List<Pair<String, String>> = emptyList(),

    // ---- tuning manual per situs (opsional) ----
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
