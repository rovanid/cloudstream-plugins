// @auto-detect | detected: 2026-10-15 | score: 6 | fixtures: 70a971e4
// Dibuat otomatis oleh .github/scripts/detect_selectors.py dari HTML nyata di tests/kotlin/fixtures/MyFlixerProvider/
// Hapus baris "@auto-detect" di baris pertama untuk MENGUNCI dan mengedit manual.
package com.cloudstreamid.myflixerprovider

object Sel {
    const val ITEM = "div.flw-item"
    const val TITLE = "h3.film-name"
    const val SEARCH = "/search?keyword={q}"
    const val PAGE_STYLE = "none"
    const val PAGE_PARAM = "page"
    const val POSTER = "img[class*=poster]"
    const val DESC = "div.description"
    const val GENRE = ""
    const val EPISODE = ""
    const val EPISODES_DESC = true
    const val USE_OG_IMAGE = false
    const val USE_OG_DESC = true
    const val PLAYER = "li.nav-item a[data-id]"
    val PLAYER_ATTRS = listOf("src", "data-src", "data-lazy-src", "data-litespeed-src", "value", "data-video", "data-embed", "data-iframe", "data-url", "data-em", "data-id")
    val CATEGORIES: List<Pair<String, String>> = listOf(
        "/movies/" to "Movies",
        "/tv-series/" to "TV Shows",
        "/genre/drama/" to "Drama",
        "/genre/comedy/" to "Comedy",
        "/genre/thriller/" to "Thriller",
        "/genre/documentary/" to "Documentary",
        "/genre/horror/" to "Horror",
        "/genre/romance/" to "Romance"
    )
}
