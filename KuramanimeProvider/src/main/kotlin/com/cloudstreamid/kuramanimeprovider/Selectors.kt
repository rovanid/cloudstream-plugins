// DIKUNCI MANUAL (tidak ada baris @auto-detect): detect_selectors.py tidak akan menimpa file ini.
// Sumber: fixture nyata tests/kotlin/fixtures/KuramanimeProvider (v20.kuramanime.ing, 15 Okt 2026).
// Alasan dikunci: detektor otomatis memilih ITEM 'div.mx-auto' (salah). Kartu Kuramanime berupa
// <a> di dalam div.filter__gallery, posternya di atribut data-setbg (bukan <img>), dan tautannya
// mengarah ke halaman EPISODE terbaru, bukan halaman seri.
package com.cloudstreamid.kuramanimeprovider

object Sel {
    // list.html: 18 kartu "div.filter__gallery > a"; judul "h5.sidebar-title-h5"; poster dibaca mesin dari data-setbg
    const val ITEM = "div.filter__gallery > a"
    const val TITLE = "h5.sidebar-title-h5"
    // form situs: GET /anime dengan input "search"; order_by=latest = tampilan kartu (order_by=text = daftar teks tanpa poster)
    const val SEARCH = "/anime?search={q}&order_by=latest"
    const val PAGE_STYLE = "query"
    const val PAGE_PARAM = "page"
    const val POSTER = ""
    // detail.html: <p id="synopsisField">
    const val DESC = "#synopsisField"
    const val GENRE = ".anime__details__widget a[href*='/properties/genre/']"
    // Daftar episode TIDAK berupa tautan biasa: HTML-nya disimpan di atribut data-content milik a#episodeLists.
    // Dibaca oleh jalur khusus di AdaptiveProvider.episodeAnchors, jadi dikosongkan di sini.
    const val EPISODE = ""
    const val EPISODES_DESC = false
    const val USE_OG_IMAGE = true
    const val USE_OG_DESC = false
    // episode.html: <video id="player"> dengan <source size="720|480|360"> (MP4 langsung)
    const val PLAYER = "video source[src]"
    val PLAYER_ATTRS = listOf("src", "data-src", "data-lazy-src", "data-litespeed-src", "value", "data-video", "data-embed", "data-iframe", "data-url", "data-em")
    val CATEGORIES: List<Pair<String, String>> = listOf()
}
