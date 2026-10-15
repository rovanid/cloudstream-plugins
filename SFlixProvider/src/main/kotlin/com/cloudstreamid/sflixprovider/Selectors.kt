// DIKUNCI MANUAL (tidak ada baris @auto-detect): detect_selectors.py tidak akan menimpa file ini.
// Sumber: fixture nyata tests/kotlin/fixtures/SFlixProvider (sflix.win, 15 Okt 2026).
// SFlixProvider ditulis mandiri (MainAPI), bukan AdaptiveProvider: situs ini punya musim/episode dan
// daftar server embed di <li data-id>, yang tidak ditangani mesin generik.
package com.cloudstreamid.sflixprovider

object Sel {
    // list.html: kartu "div.film_list-wrap > div.flw-item"; judul "h3.film-name a"; poster "img.film-poster-img"
    const val ITEM = "div.film_list-wrap div.flw-item"
    const val TITLE = "h3.film-name a"
    const val POSTER = "img.film-poster-img"
    const val POSTER_LINK = "a.film-poster-ahref"
    // kategori beranda: halaman bernomor gaya path /movies/page/N/ (terlihat di paginasi situs)
    const val SEARCH = "/search?keyword="
    // detail.html / episode.html
    const val D_TITLE = "h2.heading-name a"
    const val D_POSTER = ".dp-i-c-poster img"
    const val D_DESC = ".description"
    const val D_ROW = ".elements .row-line"
    const val D_DURATION = ".film-stats .duration"
    const val SEASON_ITEM = "a[data-ss]"
    const val EPISODE = "a.eps-item[href]"
    const val SERVER = "li.sv-item[data-id]"
}
