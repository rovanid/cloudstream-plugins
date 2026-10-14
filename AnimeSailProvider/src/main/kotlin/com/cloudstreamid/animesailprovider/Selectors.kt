// DIKUNCI MANUAL (tidak ada baris @auto-detect): detect_selectors.py tidak akan menimpa file ini.
// Sumber: fixture nyata tests/kotlin/fixtures/AnimeSailProvider (anisail.com, 14 Okt 2026).
package com.cloudstreamid.animesailprovider

object Sel {
    const val ITEM = "article.bs"
    const val TITLE = ".tt h2"
    const val SEARCH = ""
    const val PAGE_STYLE = "path"
    const val PAGE_PARAM = "page"
    const val POSTER = ""
    const val DESC = ""
    const val GENRE = ""
    const val EPISODE = "ul.daftar li a"
    const val EPISODES_DESC = true
    const val USE_OG_IMAGE = true
    const val USE_OG_DESC = true
    const val PLAYER = "select.mirror option[data-em]"
    val PLAYER_ATTRS = listOf("src", "data-src", "data-lazy-src", "data-litespeed-src", "value", "data-video", "data-embed", "data-iframe", "data-url", "data-em")
    val CATEGORIES: List<Pair<String, String>> = listOf()
}
