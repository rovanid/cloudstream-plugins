// @auto-detect | detected: default | score: 0
// File ini dibuat/diperbarui otomatis oleh .github/scripts/detect_selectors.py.
// Hapus baris "@auto-detect" di baris pertama untuk MENGUNCI dan mengedit manual.
package com.cloudstreamid.animesailprovider

object Sel {
    const val ITEM = "article"
    const val TITLE = "h2, h3"
    const val SEARCH = "/?s={q}"
    const val PAGE_STYLE = "path"
    const val PAGE_PARAM = "page"
    const val POSTER = ""
    const val DESC = ""
    const val GENRE = ""
    const val EPISODE = ""
    const val EPISODES_DESC = true
    const val USE_OG_IMAGE = true
    const val USE_OG_DESC = true
    const val PLAYER = "iframe"
    val PLAYER_ATTRS = listOf("src", "data-src", "data-lazy-src", "data-litespeed-src", "value", "data-video", "data-embed", "data-iframe", "data-url")
    val CATEGORIES = listOf("/" to "Terbaru")
}
