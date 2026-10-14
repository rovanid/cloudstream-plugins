package com.cloudstreamid.kuramanimeprovider

import com.cloudstreamid.common.AdaptiveProvider
import com.cloudstreamid.common.SiteConfig
import android.util.Log
import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.network.CloudflareKiller
import com.lagradost.cloudstream3.utils.*
import java.net.URLEncoder

class KuramanimeProvider : AdaptiveProvider() {
    // JANGAN ubah format baris mainUrl ini, dipakai apply_domains.py
    override var mainUrl = "https://v20.kuramanime.ing"
    override var name = "Kuramanime"
    override var lang = "id"
    override val supportedTypes = setOf(TvType.Anime, TvType.AnimeMovie, TvType.OVA)

    // Nilai Sel.* diisi otomatis oleh detect_selectors.py (kalau situs bisa dijangkau dari CI).
    // Semuanya hanya KANDIDAT: mesin memilih yang bekerja saat dijalankan di aplikasi.
    // Bagian "tuning" di bawah adalah pengetahuan struktur situs dan tidak ditimpa script.
    override val config = SiteConfig(
        item = Sel.ITEM,
        title = Sel.TITLE,
        search = Sel.SEARCH,
        pageStyle = Sel.PAGE_STYLE,
        pageParam = Sel.PAGE_PARAM,
        poster = Sel.POSTER,
        desc = Sel.DESC,
        genre = Sel.GENRE,
        episode = Sel.EPISODE,
        episodesDesc = Sel.EPISODES_DESC,
        useOgImage = Sel.USE_OG_IMAGE,
        useOgDesc = Sel.USE_OG_DESC,
        player = Sel.PLAYER,
        playerAttrs = Sel.PLAYER_ATTRS,
        // Kategori ASLI situs (opsi urutan di /anime). Ditulis manual, tidak ditimpa script.
        categories = listOf(
            "/anime?order_by=latest&page={page}" to "Terbaru",
            "/anime?order_by=updated&page={page}" to "Baru Diperbarui",
            "/anime?order_by=popular&page={page}" to "Terpopuler",
            "/anime?order_by=ascending&page={page}" to "A-Z"
        ),
        extraItems = listOf("div#animeList div.product__item", "div.product__item"),
        extraTitle = listOf(".product__item__text h5"),
        extraSearch = listOf("/anime?search={q}&order_by=latest"),
        extraPoster = listOf(".anime__details__pic"),
        extraDesc = listOf("#synopsisField", ".anime__details__text p"),
        extraEpisode = listOf("#episodeLists"),
        episodePages = 8,
        extraPlayer = listOf("video#player source", "select#changeServer option"),
    )

    // ------------------------------------------------------------------------------------
    // Alur pemutar asli Kuramanime (hasil membaca anime-episode.min.js + halaman tersimpan):
    //  1. Halaman episode TIDAK memuat <video>. Pemutar baru muncul setelah halaman diminta ulang
    //     dengan token:  <episode>?<PAGE_TOKEN_KEY>=<token>&<STREAM_SERVER_KEY>=<server>&page=1
    //  2. Nama parameter + lokasi file token ada di file env (nama file = atribut data-kk di
    //     halaman). Nilainya DIGANTI-GANTI situs, jadi dibaca ulang setiap kali, tidak ditulis mati.
    //  3. Token diambil dari  /<MIX_PREFIX_AUTH_ROUTE_PARAM><MIX_AUTH_ROUTE_PARAM>
    //  4. Respons berisi <video id=player src=...> dan <source size=720/480>.
    // ------------------------------------------------------------------------------------
    private val cf by lazy { CloudflareKiller() }
    private val ua = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"

    private fun env(js: String, key: String): String? =
        Regex("""$key\s*:\s*['"]([^'"]*)['"]""").find(js)?.groupValues?.get(1)

    private fun looksLikeToken(t: String) =
        t.length in 4..64 && !t.contains('<') && !t.contains(' ') && !t.contains('{')

    private suspend fun get(url: String, ref: String, headers: Map<String, String> = emptyMap()) =
        app.get(url, referer = ref, headers = mapOf("User-Agent" to ua) + headers, interceptor = cf)

    override suspend fun loadLinks(
        data: String,
        isCasting: Boolean,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit
    ): Boolean {
        val ok = try {
            kuramaLinks(data.substringBefore("?"), subtitleCallback, callback)
        } catch (e: Exception) {
            Log.e("Kuramanime", "alur token gagal: ${e.message}")
            false
        }
        // cadangan: mesin generik
        return ok || super.loadLinks(data, isCasting, subtitleCallback, callback)
    }

    private suspend fun kuramaLinks(
        episodeUrl: String,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit
    ): Boolean {
        val base = episodeUrl.substringBefore("/anime/").ifBlank { mainUrl }.trimEnd('/')
        val page = get(episodeUrl, "$base/").document

        // --- 1. env (nama parameter & file token) ---
        val kk = page.selectFirst("[data-kk]")?.attr("data-kk")
            ?: throw ErrorLoadingException("data-kk tidak ditemukan, struktur halaman berubah")
        var envJs: String? = null
        for (path in listOf("/assets/$kk.js", "/$kk.js", "/storage/$kk.js")) {
            val r = runCatching { get(base + path, episodeUrl) }.getOrNull() ?: continue
            if (r.isSuccessful && r.text.contains("MIX_PAGE_TOKEN_KEY")) { envJs = r.text; break }
        }
        envJs ?: throw ErrorLoadingException("file env $kk.js tidak ditemukan")
        val prefix = env(envJs, "MIX_PREFIX_AUTH_ROUTE_PARAM") ?: "assets/"
        val route = env(envJs, "MIX_AUTH_ROUTE_PARAM") ?: throw ErrorLoadingException("route token kosong")
        val tokenKey = env(envJs, "MIX_PAGE_TOKEN_KEY") ?: throw ErrorLoadingException("PAGE_TOKEN_KEY kosong")
        val serverKey = env(envJs, "MIX_STREAM_SERVER_KEY") ?: throw ErrorLoadingException("STREAM_SERVER_KEY kosong")
        val authKey = env(envJs, "MIX_AUTH_KEY")
        val authToken = env(envJs, "MIX_AUTH_TOKEN")

        // --- 2. ambil token halaman ---
        // getStTk ada di leviathan.js (tidak kita punya), jadi dicoba beberapa cara berurutan.
        val tokenUrl = "$base/${prefix.trimStart('/')}$route"
        val attempts = buildList<Pair<String, Map<String, String>>> {
            add(tokenUrl to emptyMap())
            if (authKey != null && authToken != null) {
                add("$tokenUrl?$authKey=$authToken" to emptyMap())
                add(tokenUrl to mapOf(authKey to authToken))
            }
        }
        var token: String? = null
        for ((u, h) in attempts) {
            val t = runCatching { get(u, episodeUrl, h).text.trim() }.getOrNull() ?: continue
            if (looksLikeToken(t)) { token = t; break }
        }
        token ?: throw ErrorLoadingException("token halaman gagal diambil dari $route")

        // --- 3. server yang tersedia (kuramadrive, mega, doodstream, filemoon, ...) ---
        val servers = page.select("select#changeServer option").map { it.attr("value") }
            .filter { it.isNotBlank() }.ifEmpty { listOf("kuramadrive") }
            .sortedBy { if (it.startsWith("kuramadrive")) 0 else 1 }  // server langsung dulu

        var ok = false
        val seen = HashSet<String>()
        for (server in servers) {
            val u = "$episodeUrl?$tokenKey=${enc(token)}&$serverKey=${enc(server)}&page=1"
            val doc = runCatching { get(u, episodeUrl).document }.getOrNull() ?: continue
            val label = "$name ${server.replaceFirstChar { it.uppercase() }}"

            // sumber langsung (mp4 / m3u8 bertanda tangan)
            val direct = LinkedHashMap<String, Int>()
            doc.select("video#player source[src], video source[src]").forEach {
                val q = it.attr("size").toIntOrNull() ?: Qualities.Unknown.value
                direct[it.attr("src")] = q
            }
            doc.selectFirst("video#player")?.let { v ->
                v.attr("src").takeIf { it.isNotBlank() }?.let { direct.putIfAbsent(it, qualityFromUrl(it)) }
                v.attr("data-hls-src").takeIf { it.isNotBlank() }?.let { direct.putIfAbsent(it, Qualities.Unknown.value) }
            }
            for ((src, q) in direct) {
                if (!seen.add(src)) continue
                callback.invoke(
                    newExtractorLink(name, label, src,
                        if (src.contains(".m3u8")) ExtractorLinkType.M3U8 else ExtractorLinkType.VIDEO) {
                        this.referer = "$base/"
                        this.quality = q
                    }
                )
                ok = true
            }

            // server pihak ketiga: iframe / tautan embed -> extractor bawaan CloudStream
            if (direct.isEmpty()) {
                val embeds = doc.select("iframe[src], iframe[data-src]")
                    .map { it.attr("src").ifBlank { it.attr("data-src") } }
                    .plus(doc.select("#animeVideoPlayer a[href], .anime__video__player a[href]").map { it.attr("href") })
                    .filter { it.startsWith("http") && !it.startsWith(base) }
                    .distinct()
                for (e in embeds) {
                    if (runCatching { loadExtractor(e, "$base/", subtitleCallback, callback) }.isSuccess) ok = true
                }
            }
        }
        Log.d("Kuramanime", "loadLinks ok=$ok server=${servers.joinToString()}")
        return ok
    }

    private fun enc(v: String) = URLEncoder.encode(v, "UTF-8")

    private fun qualityFromUrl(u: String): Int =
        Regex("""(\d{3,4})p""").find(u)?.groupValues?.get(1)?.toIntOrNull() ?: Qualities.Unknown.value
}
