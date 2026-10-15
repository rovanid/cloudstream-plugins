// DIKUNCI manual (tanpa @auto-detect)
package com.cloudstreamid.layarkaca21provider

object Sel {
    const val ITEM = "article[itemscope]"
    const val TITLE = "h3.poster-title"
    const val SEARCH = "/search?s={q}"
    const val PAGE_STYLE = "path"
    const val PAGE_PARAM = "page"
    const val POSTER = "img[itemprop=image]"
    const val DESC = "div.synopsis"
    const val GENRE = ""
    const val EPISODE = ""
    const val EPISODES_DESC = true
    const val USE_OG_IMAGE = true
    const val USE_OG_DESC = true
    const val PLAYER = "ul#player-list li a[data-url]"
    val PLAYER_ATTRS = listOf("data-url", "href", "src", "data-src", "data-lazy-src", "data-litespeed-src", "value", "data-video", "data-embed", "data-iframe")
    val CATEGORIES: List<Pair<String, String>> = listOf(
        "/latest" to "Film Terbaru",
        "/populer" to "Film Populer",
        "/nonton-bareng-keluarga" to "Film Keluarga"
    )
}
