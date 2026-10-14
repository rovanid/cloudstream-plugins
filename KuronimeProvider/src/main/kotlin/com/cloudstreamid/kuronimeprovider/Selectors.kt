// @auto-detect | detected: 2026-10-14 | score: 4
// File ini dibuat/diperbarui otomatis oleh .github/scripts/detect_selectors.py.
// Hapus baris "@auto-detect" di baris pertama untuk MENGUNCI dan mengedit manual.
package com.cloudstreamid.kuronimeprovider

object Sel {
    const val ITEM = "div.serieslist.pop > ul > li"
    const val TITLE = "h2"
    const val SEARCH = ""
    const val PAGE_STYLE = "none"
    const val PAGE_PARAM = "page"
    const val POSTER = ""
    const val DESC = "[itemprop=description]"
    const val GENRE = ""
    const val EPISODE = "span.lchx a"
    const val EPISODES_DESC = true
    const val USE_OG_IMAGE = true
    const val USE_OG_DESC = true
    const val PLAYER = "iframe"
    val PLAYER_ATTRS = listOf("src", "data-src", "data-lazy-src", "data-litespeed-src", "value", "data-video", "data-embed", "data-iframe", "data-url", "data-em")
    val CATEGORIES: List<Pair<String, String>> = listOf()
}
