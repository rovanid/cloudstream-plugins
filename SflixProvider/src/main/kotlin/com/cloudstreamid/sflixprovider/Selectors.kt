// @auto-detect | detected: 2026-10-14 | score: 5 | fixtures: 49318b44
// Dibuat otomatis oleh .github/scripts/detect_selectors.py dari HTML nyata di tests/kotlin/fixtures/SflixProvider/
// Hapus baris "@auto-detect" di baris pertama untuk MENGUNCI dan mengedit manual.
package com.cloudstreamid.sflixprovider

object Sel {
    const val ITEM = "div.ml-item"
    const val TITLE = "h2"
    const val SEARCH = ""
    const val PAGE_STYLE = "none"
    const val PAGE_PARAM = "page"
    const val POSTER = ""
    const val DESC = ".desc"
    const val GENRE = ""
    const val EPISODE = ""
    const val EPISODES_DESC = true
    const val USE_OG_IMAGE = true
    const val USE_OG_DESC = true
    const val PLAYER = "iframe"
    val PLAYER_ATTRS = listOf("src", "data-src", "data-lazy-src", "data-litespeed-src", "value", "data-video", "data-embed", "data-iframe", "data-url", "data-em")
    val CATEGORIES: List<Pair<String, String>> = listOf(
        "/latest-movie/" to "Latest Movie",
        "/popular-movie/" to "Popular Movie",
        "/top-rated-movie/" to "Top Rated Movie",
        "/upcoming-movie/" to "Upcoming Movie",
        "/airing-today-tv/" to "Airing Today TV",
        "/popular-tv/" to "Popular TV",
        "/on-the-air-tv/" to "On The Air TV",
        "/top-rated-tv/" to "Top Rated TV"
    )
}
