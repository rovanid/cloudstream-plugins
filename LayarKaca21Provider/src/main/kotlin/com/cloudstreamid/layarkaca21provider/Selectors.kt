// @auto-detect | detected: 2026-10-15 | score: 7 | fixtures: 900a1766
// Dibuat otomatis oleh .github/scripts/detect_selectors.py dari HTML nyata di tests/kotlin/fixtures/LayarKaca21Provider/
// Hapus baris "@auto-detect" di baris pertama untuk MENGUNCI dan mengedit manual.
package com.cloudstreamid.layarkaca21provider

object Sel {
    const val ITEM = "li.slider"
    const val TITLE = "h3.poster-title"
    const val SEARCH = "/search?s={q}"
    const val PAGE_STYLE = "path"
    const val PAGE_PARAM = "page"
    const val POSTER = ""
    const val DESC = "div.synopsis.collapsed"
    const val GENRE = ""
    const val EPISODE = ""
    const val EPISODES_DESC = true
    const val USE_OG_IMAGE = true
    const val USE_OG_DESC = true
    const val PLAYER = "body[data-search_url]"
    val PLAYER_ATTRS = listOf("src", "data-src", "data-lazy-src", "data-litespeed-src", "value", "data-video", "data-embed", "data-iframe", "data-url", "data-em", "data-search_url")
    val CATEGORIES: List<Pair<String, String>> = listOf(
        "/populer/" to "Terpopuler",
        "/rekomendasi-film-pintar/" to "Rekomendasi",
        "/latest/" to "Post Terbaru",
        "/top-series-today/" to "SERIES UNGGULAN",
        "/latest-series/" to "SERIES UPDATE",
        "/genre/action/" to "Action",
        "/genre/adventure/" to "Adventure",
        "/genre/animation/" to "Animation"
    )
}
