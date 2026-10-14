#!/usr/bin/env python3
"""
Uji pemutaran berkala: apakah tiap plugin masih menghasilkan URL video yang benar-benar hidup?

Per plugin (alur meniru AdaptiveProvider):
  beranda/kategori -> item -> halaman episode -> daftar embed (iframe, mirror, data-*, base64)
  -> halaman embed (termasuk JS ter-pack dan iframe bersarang) -> URL .m3u8/.mp4
  -> diverifikasi: playlist valid + segmen pertama bisa diunduh, atau mp4 bisa di-Range.

Hasil per plugin:
  OK           ada URL video yang terbukti bisa diputar
  PARTIAL      embed hidup tapi videonya tidak bisa diekstrak script (mungkin ditangani extractor
               CloudStream); dianggap sehat, tidak mengubah apa pun
  FAIL         halaman terbuka, tetapi tidak ada embed / semua embed mati  -> workflow merah
  BLOCKED      diblokir bot (Cloudflare dll.), tidak bisa dipastikan       -> diabaikan
  INCONCLUSIVE daftar dimuat lewat JavaScript, tidak bisa diuji dari CI    -> diabaikan
  URL_CHANGED  domain/URL situs berganti (redirect ke host lain)           -> DIKECUALIKAN
  URL_ISSUE    situs tidak terjangkau/error server                         -> DIKECUALIKAN

URL_CHANGED/URL_ISSUE sengaja bukan kegagalan: itu urusan check_domains.py / domains.yml.
Status plugin di build.gradle.kts hanya diubah otomatis kalau AUTO_STATUS=1
(Down setelah FAIL_THRESHOLD kali FAIL berturut-turut, Ok lagi saat pulih).
Butuh: pip install beautifulsoup4
"""
import base64
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from detect_selectors import EP_RE, UA, card_href, detect_episodes, find_items  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

ROOT = Path(os.environ.get("PLAYBACK_ROOT") or Path(__file__).resolve().parents[2])
STATE = ROOT / "playback_state.json"
REPORT = ROOT / "playback_report.md"
DELAY = float(os.environ.get("PLAYBACK_DELAY", "0.3"))
AUTO_STATUS = os.environ.get("AUTO_STATUS") == "1"
FAIL_THRESHOLD = int(os.environ.get("FAIL_THRESHOLD", "2"))
MAX_ITEMS, MAX_EMBEDS, MAX_DEPTH = 3, 6, 3

MEDIA_RE = re.compile(r"""https?://[^\s"'<>\\]+?\.(?:m3u8|mp4)[^\s"'<>\\]*""")
JUNK_MEDIA = re.compile(r"(?i)(doubleclick|/ads?/|adserver|banner|promo|sprite)")
SKIP_HOSTS = ("facebook.com", "disqus.com", "googletagmanager.com", "google.com/recaptcha", "histats.com",
              "doubleclick", "youtube.com", "youtu.be", "twitter.com", "instagram.com", "t.me/", "wa.me/")
DEAD_TEXT = re.compile(r"(?i)(file not found|video not found|has been removed|been deleted|no longer available|"
                       r"tidak ditemukan|telah dihapus|sudah dihapus|video dihapus)")
WATCH_TEXT = re.compile(r"(?i)\b(nonton|tonton|watch|play|streaming)\b")
ATTRS = ["src", "data-src", "data-lazy-src", "data-litespeed-src", "value", "data-video", "data-embed",
         "data-iframe", "data-url", "data-em", "data-link", "data-player"]
PLAYER_SELS = ["iframe", "option", "[data-video]", "[data-embed]", "[data-iframe]", "[data-url]", "[data-em]",
               "ul#player-list li a", "#player-list a", ".server-list a", "a[data-server]"]
RANK = {"playable": 4, "alive": 3, "blocked": 2, "dead": 1, "none": 0}


# ------------------------------------------------------------------ jaringan
class Resp:
    def __init__(self, status=0, final="", body=b"", ctype="", err=""):
        self.status, self.final, self.body, self.ctype, self.err = status, final, body, ctype, err

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "ignore")

    @property
    def blocked(self) -> bool:
        head = self.body[:20000].decode("utf-8", "ignore").lower()
        return self.status in (403, 429, 503) or "just a moment" in head or "cf-chl" in head


def http(url: str, referer: str = "", rng: bool = False, limit: int = 1_500_000) -> Resp:
    time.sleep(DELAY)
    headers = {"User-Agent": UA, "Accept-Language": "id,en;q=0.8"}
    if referer:
        headers["Referer"] = referer
    if rng:
        headers["Range"] = "bytes=0-2047"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            return Resp(r.status, r.geturl(), r.read(limit), r.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as e:
        try:
            body = e.read(200_000)
        except Exception:
            body = b""
        return Resp(e.code, e.geturl() or url, body, e.headers.get("Content-Type", "") if e.headers else "")
    except Exception as e:  # DNS, timeout, TLS, dll.
        return Resp(0, url, b"", "", str(e))


def host_of(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def domain_key(url: str) -> str:
    return ".".join(host_of(url).split(".")[-2:])


def origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/"


# ------------------------------------------------------------ baca konfigurasi
def read_flat(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def list_block(src: str, key: str) -> str:
    """Isi `key ... listOf( ... )` dengan kurung seimbang ('' kalau tidak ada)."""
    m = re.search(rf"\b{key}\b[^=\n]*=\s*listOf(?:<[^>]*>)?\(", src)
    if not m:
        return ""
    depth, i = 1, m.end()
    while i < len(src) and depth:
        depth += {"(": 1, ")": -1}.get(src[i], 0)
        i += 1
    return src[m.end():i - 1]


def categories_of(folder: Path) -> list:
    for kt in folder.rglob("*Provider.kt"):
        block = list_block(kt.read_text(encoding="utf-8"), "categories")
        pairs = re.findall(r'"([^"]+)"\s+to\s+"([^"]+)"', block)
        if pairs:
            return pairs
    for kt in folder.rglob("Selectors.kt"):
        pairs = re.findall(r'"([^"]+)"\s+to\s+"([^"]+)"', list_block(kt.read_text(encoding="utf-8"), "CATEGORIES"))
        if pairs:
            return pairs
    return [("/", "Beranda")]


# --------------------------------------------------------------------- embed
def unpack(src: str) -> str:
    """Pembuka JS ter-pack (p,a,c,k,e,d)."""
    m = re.search(r"\}\('(.*)',\s*(\d+),\s*(\d+),\s*'(.*?)'\.split\('\|'\)", src, re.S)
    if not m:
        return ""
    try:
        payload = m.group(1).replace("\\'", "'").replace("\\\\", "\\")
        radix, count, sym = int(m.group(2)), int(m.group(3)), m.group(4).split("|")
        chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

        def enc(c):
            return ("" if c < radix else enc(c // radix)) + chars[c % radix]

        table = {enc(i): (sym[i] if i < len(sym) and sym[i] else enc(i)) for i in range(count)}
        return re.sub(r"\b\w+\b", lambda x: table.get(x.group(0), x.group(0)), payload)
    except Exception:
        return ""


def b64_html(v: str) -> str:
    if len(v) < 12 or not re.fullmatch(r"[A-Za-z0-9+/=_-]+", v):
        return ""
    try:
        d = base64.b64decode(v.replace("-", "+").replace("_", "/") + "=" * (-len(v) % 4)).decode("utf-8", "ignore")
    except Exception:
        return ""
    return d if ("http" in d or "<iframe" in d.lower()) else ""


def add_embed(raw: str, base: str, out: list) -> None:
    v = (raw or "").strip()
    if not v:
        return
    html = v if v.startswith("<") else ("" if v.startswith(("http", "/")) else b64_html(v))
    if html:
        found = [e.get("src") or e.get("data-src") or "" for e in BeautifulSoup(html, "html.parser").select("iframe, source")]
        cands = [f for f in found if f] or re.findall(r"https?://[^\s\"'<>]+", html)
    else:
        cands = [v]
    for c in cands:
        if c.startswith(("#", "javascript", "data:", "about:")):
            continue
        u = urljoin(base, c.replace(" ", "%20"))
        if u.startswith("http") and not any(h in u.lower() for h in SKIP_HOSTS) \
                and u.rstrip("/") != base.rstrip("/") and u not in out:
            out.append(u)


def extract(soup, base: str):
    """-> (embeds, media langsung) dari satu halaman."""
    embeds, media = [], []
    for sel in PLAYER_SELS:
        for el in soup.select(sel):
            for a in ATTRS + (["href"] if el.name == "a" else []):
                add_embed(el.get(a) or "", base, embeds)
    for s in soup.select("video source[src], video[src]"):
        u = urljoin(base, (s.get("src") or "").strip())
        if u.startswith("http") and u not in media:
            media.append(u)
    return embeds, media


# ----------------------------------------------------------------- verifikasi
def verify_media(url: str, referer: str) -> str:
    """playable | dead | blocked | alive"""
    if JUNK_MEDIA.search(url):
        return "dead"
    if ".m3u8" in url.lower():
        r = http(url, referer, limit=300_000)
        if r.status == 0:
            return "dead"
        if r.status in (403, 429):
            return "blocked"
        if r.status != 200 or not r.text.lstrip("\ufeff \n").startswith("#EXTM3U"):
            return "dead"
        for _ in range(2):  # master -> variant -> segmen
            lines = [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("#")]
            if not lines:
                return "dead"
            nxt = urljoin(r.final, lines[0])
            if "#EXT-X-STREAM-INF" in r.text:
                r = http(nxt, referer, limit=300_000)
                if r.status != 200 or "#EXTM3U" not in r.text:
                    return "dead"
                continue
            seg = http(nxt, referer, rng=True, limit=4096)
            if seg.status in (200, 206):
                return "playable"
            if seg.status in (404, 410):
                return "dead"
            return "blocked" if seg.status in (403, 429) else "alive"
        return "alive"
    r = http(url, referer, rng=True, limit=4096)
    if r.status in (200, 206) and (r.ctype.lower().startswith(("video/", "application/octet-stream"))
                                   or b"ftyp" in r.body[:64]):
        return "playable"
    if r.status in (403, 429):
        return "blocked"
    return "dead" if r.status in (0, 404, 410) or r.status >= 400 else "alive"


def best(statuses) -> str:
    return max(statuses, key=lambda s: RANK[s], default="none")


def check_embed(embed: str, referer: str, depth: int, seen: set) -> str:
    if embed in seen:
        return "none"
    seen.add(embed)
    if re.search(r"(?i)\.(m3u8|mp4)(\?|$)", embed):
        return verify_media(embed, referer)
    r = http(embed, referer)
    if r.status == 0 or r.status in (404, 410) or r.status >= 500:
        return "dead"
    if r.blocked:
        return "blocked"
    if r.status != 200:
        return "dead"
    body = r.text.replace("\\/", "/")
    text = body + "\n" + unpack(body).replace("\\/", "/")
    res = [verify_media(m.group(0).rstrip(",;)\\."), r.final) for m in MEDIA_RE.finditer(text)
           if not any(h in m.group(0).lower() for h in SKIP_HOSTS)][:6]
    soup = BeautifulSoup(r.text, "html.parser")
    nested, direct = extract(soup, r.final)
    res += [verify_media(u, r.final) for u in direct[:3]]
    if "playable" in res:
        return "playable"
    if depth < MAX_DEPTH:
        res += [check_embed(n, r.final, depth + 1, seen) for n in nested[:3]]
    if not res and not nested:
        return "dead" if DEAD_TEXT.search(body[:50000]) else "alive"  # halaman hidup, extractor CloudStream mungkin menangani
    return best(res) if res else "alive"


# --------------------------------------------------------------------- halaman
def episode_links(soup, url: str) -> list:
    host = host_of(url)
    sel, _ = detect_episodes(soup, url)
    anchors = list(soup.select(sel)) if sel else []
    for el in soup.select("[data-content]"):  # daftar episode di atribut (Kuramanime)
        if "<a" in (el.get("data-content") or ""):
            anchors += BeautifulSoup(el["data-content"], "html.parser").find_all("a", href=True)
    if not anchors:
        anchors = [a for a in soup.find_all("a", href=True) if EP_RE.search(a.get_text(" ", strip=True) + a["href"])]
    out = []
    for a in anchors:
        h = a.get("href") or ""
        u = urljoin(url, h)
        if h and not h.startswith("#") and host_of(u) == host and u.rstrip("/") != url.rstrip("/") and u not in out:
            out.append(u)
    return out


def watch_links(soup, url: str) -> list:
    out = []
    for a in soup.find_all("a", href=True):
        if any(p.name in ("header", "footer", "nav", "aside") for p in a.parents):
            continue
        u = urljoin(url, a["href"])
        if WATCH_TEXT.search(a.get_text(" ", strip=True)) and host_of(u) == host_of(url) \
                and u.rstrip("/") != url.rstrip("/") and urlparse(u).path.strip("/") and u not in out:
            out.append(u)
    return out[:2]


def check_player_page(url: str, referer: str, seen: set) -> str:
    r = http(url, referer)
    if r.blocked:
        return "blocked"
    if r.status != 200:
        return "none"
    soup = BeautifulSoup(r.text, "html.parser")
    embeds, media = extract(soup, r.final)
    res = [verify_media(m, r.final) for m in media[:3]]
    res += [check_embed(e, r.final, 0, seen) for e in embeds[:MAX_EMBEDS]]
    if best(res) in ("none", "dead"):
        for w in watch_links(soup, r.final):
            res.append(check_player_page_simple(w, r.final, seen))
    return best(res)


def check_player_page_simple(url: str, referer: str, seen: set) -> str:
    r = http(url, referer)
    if r.blocked:
        return "blocked"
    if r.status != 200:
        return "none"
    embeds, media = extract(BeautifulSoup(r.text, "html.parser"), r.final)
    return best([verify_media(m, r.final) for m in media[:3]] +
                [check_embed(e, r.final, 0, seen) for e in embeds[:MAX_EMBEDS]])


def check_item(site: str, href: str) -> str:
    r = http(href, site + "/")
    if r.blocked:
        return "blocked"
    if r.status != 200:
        return "none"
    soup = BeautifulSoup(r.text, "html.parser")
    seen: set = set()
    if EP_RE.search(href):  # item beranda = halaman episode
        return check_player_page(href, site + "/", seen)
    eps = episode_links(soup, r.final)
    target = eps[0] if eps else r.final
    return check_player_page(target, r.final, seen)


def check_plugin(name: str, site: str, folder: Path) -> dict:
    cats = categories_of(folder)
    first = http(urljoin(site + "/", cats[0][0].replace("{page}", "1").lstrip("/")), site + "/")
    if first.status == 0 or first.status >= 500 or first.status == 404:
        return {"verdict": "URL_ISSUE", "detail": f"tidak terjangkau (status {first.status} {first.err[:60]})"}
    if first.blocked:
        return {"verdict": "BLOCKED", "detail": "diblokir bot"}
    if host_of(first.final) != host_of(site):
        return {"verdict": "URL_CHANGED", "detail": f"{host_of(site)} -> {host_of(first.final)} (ubah di domains.yml)"}
    if first.status != 200:
        return {"verdict": "URL_ISSUE", "detail": f"status {first.status}"}

    # kategori: tiap URL harus benar-benar memuat daftar item
    bad = []
    for path, label in cats:
        r = first if path == cats[0][0] else http(urljoin(site + "/", path.replace("{page}", "1").lstrip("/")), site + "/")
        ok = r.status == 200 and not r.blocked and find_items(BeautifulSoup(r.text, "html.parser")) is not None
        if not ok and not r.blocked:
            bad.append(label)
    cat_info = {"total": len(cats), "bad": bad}

    items = find_items(BeautifulSoup(first.text, "html.parser"))
    if not items:
        return {"verdict": "INCONCLUSIVE", "detail": "daftar item tidak terbaca (dimuat JavaScript?)", "cats": cat_info}
    hrefs = []
    for c in items[1][:12]:
        h = card_href(c)
        u = urljoin(first.final, h) if h else ""
        if u and domain_key(u) == domain_key(site) and u not in hrefs:
            hrefs.append(u)
    results = [check_item(site, h) for h in hrefs[:MAX_ITEMS]]
    top = best(results)
    verdict = {"playable": "OK", "alive": "PARTIAL", "blocked": "BLOCKED"}.get(top, "FAIL")
    detail = {"OK": "URL video terverifikasi bisa diputar",
              "PARTIAL": "embed hidup, video tidak bisa diekstrak script (cek manual di aplikasi)",
              "BLOCKED": "diblokir bot saat menguji",
              "FAIL": "tidak ada embed / semua embed mati (" + ", ".join(results) + ")"}[verdict]
    return {"verdict": verdict, "detail": detail, "cats": cat_info}


# --------------------------------------------------------------- status & state
def set_status(folder: Path, new: int) -> bool:
    g = folder / "build.gradle.kts"
    t = g.read_text(encoding="utf-8")
    m = re.search(r"^(\s*status\s*=\s*)(\d)", t, re.M)
    if not m or int(m.group(2)) == new:
        return False
    g.write_text(t[:m.start(2)] + str(new) + t[m.end(2):], encoding="utf-8")
    return True


def current_status(folder: Path):
    g = folder / "build.gradle.kts"
    m = re.search(r"^\s*status\s*=\s*(\d)", g.read_text(encoding="utf-8"), re.M) if g.exists() else None
    return int(m.group(1)) if m else None


def main() -> int:
    only = set(sys.argv[1:])
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows, any_fail = [], False
    for name, url in read_flat(ROOT / "domains.yml").items():
        folder = ROOT / name
        if not folder.is_dir() or (only and name not in only):
            continue
        res = check_plugin(name, url.rstrip("/"), folder)
        v = res["verdict"]
        st = state.setdefault(name, {"fails": 0, "auto_down": False})
        if v == "FAIL":
            st["fails"] += 1
            any_fail = True
        elif v in ("OK", "PARTIAL", "URL_CHANGED", "URL_ISSUE"):
            st["fails"] = 0          # BLOCKED/INCONCLUSIVE: hitungan dibiarkan
        st["last"], st["checked"] = v, now

        note = ""
        if AUTO_STATUS:
            cur = current_status(folder)
            if v == "FAIL" and st["fails"] >= FAIL_THRESHOLD and cur == 1 and set_status(folder, 0):
                st["auto_down"], note = True, " -> status Down"
            elif v in ("OK", "PARTIAL") and st["auto_down"] and cur == 0 and set_status(folder, 1):
                st["auto_down"], note = False, " -> status Ok"
        cats = res.get("cats")
        cat_txt = "-" if not cats else (f"{cats['total'] - len(cats['bad'])}/{cats['total']}"
                                        + (f" (rusak: {', '.join(cats['bad'])})" if cats["bad"] else ""))
        print(f"[{v}] {name}: {res['detail']}{note} | kategori {cat_txt}")
        rows.append((name, v, res["detail"] + note, cat_txt, st["fails"]))

    if not only:
        STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    icon = {"OK": "✅", "PARTIAL": "🟡", "FAIL": "❌", "BLOCKED": "⏸️", "INCONCLUSIVE": "⏸️",
            "URL_CHANGED": "🔁", "URL_ISSUE": "🔁"}
    lines = ["# Laporan uji pemutaran", "", f"Terakhir dijalankan: {now} (`check_playback.py`).", "",
             "✅ terbukti bisa diputar · 🟡 embed hidup tapi tidak bisa diverifikasi · ❌ gagal · "
             "⏸️ tidak bisa diuji dari CI · 🔁 URL berganti/tidak terjangkau (dikecualikan, bukan kegagalan)", "",
             "| Plugin | Hasil | Keterangan | Kategori OK | FAIL berturut |", "|---|---|---|---|---|"]
    lines += [f"| {n} | {icon[v]} {v} | {d} | {c} | {f} |" for n, v, d, c, f in rows]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
