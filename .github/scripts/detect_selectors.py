#!/usr/bin/env python3
"""
Hasilkan Selectors.kt tiap plugin SECARA OTOMATIS dari fixture HTML nyata.

Sumber SATU-SATUNYA adalah tests/kotlin/fixtures/<Plugin>/{list,detail,episode}.html (unggahan manual,
format MHTML Chrome "Simpan halaman" juga dibaca). Skrip ini TIDAK mengakses situs: hasilnya
deterministik, tidak terhalang Cloudflare/JavaScript, dan selalu mencerminkan HTML yang Anda unggah.

Yang dideteksi dari HTML nyata:
  daftar item, judul, pagination (tautan "berikutnya"), pencarian (<form> GET), kategori (menu situs),
  deskripsi, genre, poster, daftar episode (+ urutannya), dan pemutar (iframe/mirror/atribut data-*).

Aturan:
  - Plugin AKTIF tanpa fixture lengkap -> GAGAL (exit 1), Selectors.kt tidak ditulis. (registry.py
    menolaknya lebih awal; ini lapisan kedua.)
  - Selectors.kt dengan baris pertama "// @auto-detect" ditulis ulang kalau fixture berubah (sidik jari
    di header), masih default, atau FORCE_DETECT=1. Hapus baris itu untuk mengunci dan mengedit manual.
  - Hasil dicek ulang terhadap fixture (kartu >= 3 dan bertautan, judul terisi, episode/pemutar benar-benar
    cocok). Daftar item tak terdeteksi / tak valid -> GAGAL (exit 1). Bagian lain yang kosong -> peringatan
    di detection_report.md; runtime memakai selector bawaan/heuristik untuk bagian itu.
  - Tidak ada tebakan: kalau HTML tidak memuat buktinya (mis. kotak pencarian tanpa <form>), nilainya dikosongkan.
Butuh: pip install beautifulsoup4
"""
import base64
import datetime
import hashlib
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_utils as fu  # noqa: E402
import registry  # noqa: E402
from fixture_utils import extract_html  # noqa: E402,F401  (dipakai tes)

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "detection_report.md"

HEADER_RE = re.compile(r"^// @auto-detect(?:\s*\|\s*detected:\s*(\S+))?(?:\s*\|\s*score:\s*(\d+))?(?:\s*\|\s*fixtures:\s*(\w+))?")
FIXTURES = ROOT / "tests" / "kotlin" / "fixtures"
FIXTURE_KINDS = ("list", "detail", "episode")
EP_RE = re.compile(r"(episode|\beps?\b[ ._-]?\d+|\bep[ ._-]?\d+|chapter|/eps?[-/])", re.I)
SKIP_PLAYER = re.compile(r"facebook\.com|disqus\.com|googletagmanager|recaptcha", re.I)
CAT_OK = re.compile(r"genre|categor|kategori|series|movie|film|anime|ongoing|complete|"
                    r"popul|terbaru|latest|tv|donghua|drama|new|top", re.I)
CAT_BAD = re.compile(r"login|register|daftar|dmca|contact|kontak|about|privacy|jadwal|"
                     r"schedule|request|wp-|feed|#|\.xml|disclaimer|faq|tos|terms", re.I)
CAT_INDEX = re.compile(r"^/(genre|genres|category|kategori|tag|country|az-list|a-z)/?$", re.I)  # indeks taksonomi, bukan daftar
NAV_SEL = "nav a, header a, .menu a, #menu a, ul.menu a, .navbar a"
SEARCH_NAMES = ("s", "q", "query", "keyword", "search", "k", "term")
PAGE_PARAMS = ("page", "paged", "p", "halaman")
NON_PLAYER_TAGS = ("img", "script", "link", "meta", "source", "video", "style", "iframe")
PLAYER_ATTRS = ["src", "data-src", "data-lazy-src", "data-litespeed-src", "value",
                "data-video", "data-embed", "data-iframe", "data-url", "data-em"]


# ------------------------------------------------------------ util selector
def stable_classes(el) -> list:
    out = []
    for c in el.get("class") or []:
        if not re.fullmatch(r"[A-Za-z_][\w-]*", c) or len(c) > 40 or re.search(r"\d{2,}", c):
            continue
        if c.startswith(("post-", "type-", "status-", "format-", "category-", "tag-", "has-")) or c == "hentry":
            continue
        out.append(c)
    return out


def sig(el, n: int = 3) -> str:
    return el.name + "".join("." + c for c in stable_classes(el)[:n])


def card_href(el):
    if el.name == "a" and el.get("href"):
        return el["href"]
    a = el.find("a", href=True)
    return a["href"] if a else None


def norm(base: str, href: str) -> str:
    return urljoin(base, href).split("#")[0].rstrip("/")


def meta(soup, prop: str) -> str:
    m = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return (m.get("content") or "").strip() if m else ""


# ------------------------------------------------------------------ deteksi
def find_items(soup):
    """Kartu = leluhur tertinggi yang hanya berisi satu <img>. Grup kartu terbanyak = daftar utama."""
    groups = defaultdict(list)
    for img in soup.find_all("img"):
        if any(p.name in ("header", "footer", "nav") for p in img.parents):
            continue
        card = None
        for anc in img.parents:
            if anc.name in ("body", "html", "[document]"):
                break
            if len(anc.find_all("img")) != 1:
                break
            card = anc
        if card is None or not card_href(card):
            continue
        groups[(card.name, tuple(sorted(stable_classes(card))))].append(card)
    if not groups:
        return None
    cards = max(groups.values(), key=len)
    n = len(cards)
    if n < 4:
        return None
    counts = Counter(c for el in cards for c in stable_classes(el))
    common = [c for c, k in counts.items() if k >= 0.9 * n]
    cands = []
    if common:
        # kelas tunggal dulu (selector paling umum yang masih tepat), baru gabungan
        cands += [f"{cards[0].name}.{c}" for c in common[:4]]
        cands += [cards[0].name + "".join("." + c for c in common[:3]),
                  cards[0].name + "".join("." + c for c in common)]
    else:
        p = cards[0].parent
        cands.append(f"{sig(p)} > {cards[0].name}")
        if p.parent is not None:
            cands.append(f"{sig(p.parent)} > {sig(p)} > {cards[0].name}")
    for sel in cands:
        try:
            found = soup.select(sel)
        except Exception:
            continue
        if n <= len(found) <= max(2 * n, n + 6):
            return sel, cards
    return None


def detect_title(cards) -> str:
    sample = cards[:12]
    for sel in ["h2", "h3", "h4", "h5", "h6", "[class*=title]", ".name", "[class*=name]"]:
        texts = []
        for c in sample:
            el = c.select_one(sel)
            t = el.get_text(" ", strip=True) if el else ""
            if 2 <= len(t) <= 150:
                texts.append(t)
        if len(texts) >= 0.8 * len(sample) and len(set(texts)) >= 0.8 * len(texts):
            return sel
    return ""


def hrefs_of(soup, sel, base) -> set:
    return {norm(base, card_href(c)) for c in soup.select(sel) if card_href(c)}


def detect_paging(home, base):
    """(gaya, parameter) dari tautan halaman berikutnya yang BENAR-BENAR ada di HTML; ("none", "page") bila tidak ada."""
    host = urlparse(base).netloc
    nxt = [a.get("href") for a in home.select("link[rel=next], a[rel=next], a.next, a.nextpostslink, "
                                              ".pagination a, .pager a, .hpage a, .page-numbers a, ul.pagination a")
           if a.get("href")]
    others = [a["href"] for a in home.find_all("a", href=True)]
    for href in nxt + others:                      # tautan khusus "next" didahulukan
        u = urlparse(urljoin(base + "/", href))
        if u.netloc and u.netloc != host:
            continue
        m = re.search(r"/page/(\d+)/?$", u.path)
        if m and int(m.group(1)) == 2:
            return "path", "page"
        q = parse_qs(u.query)
        for prm in PAGE_PARAMS:
            if q.get(prm) == ["2"]:
                return "query", prm
    return "none", "page"


def detect_search(home, base) -> str:
    """Pola pencarian dari <form method=GET> bernama s/q/keyword/...; "" bila tidak ada bukti di HTML.
    (Kotak pencarian tanpa <form>/action digerakkan JavaScript: URL-nya tidak bisa diketahui, jadi tidak ditebak.)"""
    host = urlparse(base).netloc
    for form in home.find_all("form"):
        if (form.get("method") or "get").lower() != "get":
            continue
        field = next((i.get("name") for i in form.find_all("input")
                      if i.get("name") in SEARCH_NAMES and (i.get("type") or "text") in ("text", "search")), None)
        if not field:
            continue
        action = urlparse(urljoin(base + "/", form.get("action") or "/"))
        if action.netloc != host:
            continue
        extra = "".join(f"&{i['name']}={i.get('value', '')}" for i in form.find_all("input", type="hidden")
                        if i.get("name") and i.get("value") and i.get("name") != field)
        return f"{action.path or '/'}?{field}={{q}}{extra}"
    return ""


def detect_categories(home, base, list_path="", limit=8):
    """Kategori dari menu situs sendiri (tanpa mengunjungi situs, jadi BELUM terbukti berisi daftar item).
    Dibuang: halaman daftar itu sendiri, indeks genre/kategori, halaman informasi (CAT_BAD)."""
    host = urlparse(base).netloc
    skip = (list_path or "").rstrip("/") + "/" if list_path else ""
    found = {}
    for a in home.select(NAV_SEL):
        href = a.get("href") or ""
        text = a.get_text(" ", strip=True)
        u = urlparse(urljoin(base + "/", href))
        if u.netloc != host or not (2 <= len(text) <= 25):
            continue
        path = u.path.rstrip("/") + "/" if u.path.strip("/") else ""
        if not path or path.count("/") > 3 or path == skip or CAT_INDEX.match(path):
            continue
        key = path + (f"?{u.query}" if u.query else "")
        if CAT_BAD.search(key) or CAT_BAD.search(text) or not (CAT_OK.search(key) or CAT_OK.search(text)):
            continue
        found.setdefault(key, text)
    return list(found.items())[:limit]


def first_ok(soup, cands, min_len=100):
    for sel in cands:
        try:
            el = soup.select_one(sel)
        except Exception:
            continue
        if el and len(el.get_text(" ", strip=True)) >= min_len:
            return sel
    return ""


def detect_genre(soup) -> str:
    for sel in ["a[rel=tag]", ".genre a", ".genres a", ".genxed a", "a[href*='/genre/']",
                "a[href*='/genres/']", "a[href*='/category/']", "a[href*='/kategori/']",
                "a[href*='/tag/']"]:
        try:
            found = [a for a in soup.select(sel) if a.get_text(strip=True)]
        except Exception:
            continue
        if 1 <= len(found) <= 12:
            return sel
    return ""


def detect_poster(soup) -> str:
    for sel in [".poster img", ".thumb img", ".cover img", "img.wp-post-image",
                "img[class*=poster]", "img[class*=cover]", "img[class*=thumb]"]:
        el = soup.select_one(sel)
        if el and any((el.get(a) or "").strip() and not (el.get(a) or "").startswith("data:")
                      for a in ("data-src", "data-lazy-src", "src")):
            return sel
    return ""


def detect_episodes(soup, page_url_, min_count: int = 3):
    """Return (selector, descending) atau ("", True). Dari fixture nyata cukup 1 tautan episode, asal berada
    di dalam daftar (<li>); dari sumber tak pasti dibutuhkan >= 3."""
    host = urlparse(page_url_).netloc

    def is_ep(a):
        return EP_RE.search(a.get_text(" ", strip=True) + " " + (a.get("href") or "")) is not None

    anchors = [a for a in soup.find_all("a", href=True)
               if urlparse(urljoin(page_url_, a["href"])).netloc == host and is_ep(a)]
    if min_count < 3:
        anchors = [a for a in anchors if any(p.name == "li" for p in a.parents)]
    if len(anchors) < min_count:
        return "", True
    cands = Counter()
    for a in anchors:
        mid = []
        for anc in list(a.parents)[:4]:
            if anc.name in ("body", "html"):
                break
            if not stable_classes(anc):
                mid.append(anc.name)
                continue
            if 0 < len(mid) <= 2:       # selector rapat: "ul.daftar li a" lebih konkret daripada "ul.daftar a"
                cands[f"{sig(anc)} {' '.join(reversed(mid))} a"] += 1
            cands[f"{sig(anc)} a"] += 1
            break
    for tok in ("episode", "/eps", "-ep-", "/ep-"):
        cands[f"a[href*='{tok}']"] += 0
    for sel in [s for s, _ in cands.most_common()]:
        try:
            found = soup.select(sel)
        except Exception:
            continue
        good = [a for a in found if is_ep(a)]
        if len(found) >= min_count and len(good) >= 0.7 * len(found) and len(found) <= len(anchors) * 1.5 + 3:
            nums = []
            for a in found:
                m = re.search(r"\d+", a.get_text(" ", strip=True))
                if m:
                    nums.append(int(m.group()))
            desc = not (len(nums) >= 2 and nums[0] < nums[-1])
            return sel, desc
    return "", True


def embed_like(value: str) -> bool:
    """Nilai atribut yang tampak seperti embed pemutar: URL, atau base64 dari <iframe ...>/URL."""
    v = (value or "").strip()
    if not v or SKIP_PLAYER.search(v):
        return False
    if v.startswith(("http://", "https://", "//")):
        return True
    if re.fullmatch(r"[A-Za-z0-9+/=\s]{16,}", v):
        try:
            dec = base64.b64decode(v + "=" * (-len(v) % 4)).decode("utf-8", "ignore").strip().lower()
        except Exception:
            return False
        return dec.startswith(("<iframe", "http://", "https://", "//")) and not SKIP_PLAYER.search(dec)
    return False


def detect_player(soup, base) -> str:
    """Selector pemutar yang terbukti ada di halaman episode nyata. Elemen beratribut embed
    (mis. `select.mirror option[data-em]`) didahulukan; "iframe" polos hanya bila tak ada yang lebih konkret.
    Catatan: Chrome menulis ulang src iframe MHTML menjadi cid:..., jadi iframe berstatus cid: tetap dihitung."""
    found = []
    for attr in PLAYER_ATTRS:
        if attr == "src":
            continue
        for el in soup.select(f"[{attr}]"):
            if el.name in NON_PLAYER_TAGS or (attr == "value" and el.name != "option"):
                continue
            if not embed_like(el.get(attr)):
                continue
            parent = next((p for p in list(el.parents)[:2] if stable_classes(p)), None)
            sel = (f"{sig(parent)} " if parent is not None else "") + f"{el.name}[{attr}]"
            if sel not in found:
                found.append(sel)
            break                                   # satu contoh per atribut cukup
    if found:
        return ",".join(found[:3])
    for el in soup.select("iframe"):
        src = (el.get("src") or el.get("data-src") or "").strip()
        if not src or src.startswith("cid:") or embed_like(src):
            if not SKIP_PLAYER.search(src):
                return "iframe"
    return ""


# --------------------------------------------------------------- fixture
def fixture_paths(name: str) -> dict:
    d = FIXTURES / name
    return {k: d / f"{k}.html" for k in FIXTURE_KINDS if (d / f"{k}.html").is_file()}


def fixture_hash(name: str) -> str:
    """Sidik jari isi fixture; kosong kalau list.html tidak ada."""
    paths = fixture_paths(name)
    if "list" not in paths:
        return ""
    h = hashlib.sha1()
    for k in FIXTURE_KINDS:
        if k in paths:
            h.update(k.encode())
            h.update(paths[k].read_bytes())
    return h.hexdigest()[:8]


def load_fixtures(name: str) -> dict:
    return {k: BeautifulSoup(extract_html(p.read_text(encoding="utf-8", errors="ignore")), "html.parser")
            for k, p in fixture_paths(name).items()}


def list_fixture_path(name: str) -> str:
    """Path URL halaman asal list.html (dari header MHTML), '' bila tidak diketahui."""
    p = fixture_paths(name).get("list")
    if not p:
        return ""
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        return urlparse(fu.source_url(f.read(5000))).path


def detect_from_fixtures(base: str, fx: dict, list_path: str = "") -> dict:
    """Seluruh deteksi dari HTML fixture. Tidak ada akses jaringan."""
    home = fx["list"]
    d = {"PAGE_PARAM": "page", "PAGE_STYLE": "none", "SEARCH": "", "TITLE": "", "POSTER": "",
         "DESC": "", "GENRE": "", "EPISODE": "", "EPISODES_DESC": True,
         "USE_OG_IMAGE": True, "USE_OG_DESC": True, "PLAYER": "iframe",
         "CATEGORIES": [], "_source": "fixture"}
    items = find_items(home)
    if not items:
        raise RuntimeError("daftar item tidak ditemukan di list.html (fixture bukan halaman daftar, "
                           "atau daftarnya dimuat JavaScript sehingga tidak ikut tersimpan)")
    item_sel, cards = items
    d["ITEM"] = item_sel
    d["TITLE"] = detect_title(cards)
    d["PAGE_STYLE"], d["PAGE_PARAM"] = detect_paging(home, base)
    d["SEARCH"] = detect_search(home, base)
    d["CATEGORIES"] = detect_categories(home, base, list_path)

    detail = fx.get("detail")
    if detail is not None:
        og_img, og_desc = meta(detail, "og:image"), meta(detail, "og:description")
        d["USE_OG_IMAGE"] = bool(og_img) and og_img != meta(home, "og:image")
        d["USE_OG_DESC"] = bool(og_desc) and og_desc != meta(home, "og:description")
        d["DESC"] = first_ok(detail, [".synopsis", ".sinopsis", "[itemprop=description]", ".description",
                                      ".desc", ".summary", ".entry-content p"])
        if not d["USE_OG_IMAGE"]:
            d["POSTER"] = detect_poster(detail)
        d["GENRE"] = detect_genre(detail)
        d["EPISODE"], d["EPISODES_DESC"] = detect_episodes(detail, base + "/", min_count=1)

    player_page = fx.get("episode") or (detail if not d["EPISODE"] else None)
    d_player = detect_player(player_page, base) if player_page is not None else ""
    if d_player:
        d["PLAYER"] = d_player
    d["_player_found"] = bool(d_player)
    return d


def validate_selectors(d: dict, fx: dict, base: str):
    """Uji balik selector hasil deteksi pada fixture. Return (fatal, peringatan)."""
    fatal, warn = [], []
    cards = fx["list"].select(d["ITEM"])
    with_link = [c for c in cards if card_href(c)]
    if len(cards) < 3:
        fatal.append(f"ITEM '{d['ITEM']}' hanya cocok dengan {len(cards)} kartu di list.html (minimal 3)")
    elif len(with_link) < 0.8 * len(cards):
        fatal.append(f"hanya {len(with_link)} dari {len(cards)} kartu ITEM punya tautan")
    if cards and d["TITLE"]:
        titled = sum(1 for c in cards if (c.select_one(d["TITLE"]) and c.select_one(d["TITLE"]).get_text(strip=True)))
        if titled < 0.8 * len(cards):
            warn.append(f"TITLE '{d['TITLE']}' kosong di {len(cards) - titled} dari {len(cards)} kartu")
    host = fu.norm_host(urlparse(base).netloc)
    absolute = [urlparse(card_href(c)) for c in with_link if (card_href(c) or "").startswith(("http://", "https://"))]
    if absolute and sum(1 for u in absolute if fu.norm_host(u.netloc) == host) < 0.5 * len(absolute):
        warn.append(f"kurang dari separuh tautan kartu mengarah ke {host}; pastikan fixture memang dari domain ini")
    detail, ep = fx.get("detail"), fx.get("episode")
    if detail is not None:
        if not d["EPISODE"]:
            warn.append("daftar episode tidak ditemukan di detail.html (wajar untuk situs film)")
        elif not [e for e in detail.select(d["EPISODE"]) if e.get("href") or e.select_one("a[href]")]:
            warn.append(f"EPISODE '{d['EPISODE']}' tidak cocok dengan tautan di detail.html")
    if ep is not None:
        if not d.get("_player_found"):
            warn.append("elemen pemutar tidak ditemukan di episode.html (mungkin dimuat JavaScript); runtime memakai bawaan")
        elif not ep.select(d["PLAYER"]):
            warn.append(f"PLAYER '{d['PLAYER']}' tidak cocok dengan elemen apa pun di episode.html")
    if not d["SEARCH"]:
        warn.append("pencarian tidak terdeteksi (tidak ada <form> GET pencarian di list.html); runtime mencoba pola bawaan")
    if d["PAGE_STYLE"] == "none":
        warn.append("tautan halaman berikutnya tidak ada di list.html; pagination dimatikan")
    return fatal, warn


def score(d: dict) -> int:
    s = 1  # ITEM
    s += bool(d["TITLE"]) + bool(d["SEARCH"]) + (d["PAGE_STYLE"] != "none")
    s += bool(d["DESC"] or d["USE_OG_DESC"]) + bool(d["GENRE"]) + bool(d["EPISODE"])
    s += bool(d.get("_player_found")) + (len(d["CATEGORIES"]) > 0)
    return s


# ---------------------------------------------------------------- output
def kstr(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def render(pkg: str, d: dict, date: str, fx_hash: str = "", name: str = "") -> str:
    cats = ",\n        ".join(f"{kstr(p)} to {kstr(n)}" for p, n in d["CATEGORIES"])
    cats_block = f"\n        {cats}\n    " if cats else ""
    attrs = ", ".join(kstr(a) for a in PLAYER_ATTRS)
    b = lambda v: "true" if v else "false"
    fx = f" | fixtures: {fx_hash}" if fx_hash else ""
    src = f"tests/kotlin/fixtures/{name}/" if name else "tests/kotlin/fixtures/<Plugin>/"
    return f"""// @auto-detect | detected: {date} | score: {score(d)}{fx}
// Dibuat otomatis oleh .github/scripts/detect_selectors.py dari HTML nyata di {src}
// Hapus baris "@auto-detect" di baris pertama untuk MENGUNCI dan mengedit manual.
package com.cloudstreamid.{pkg}

object Sel {{
    const val ITEM = {kstr(d["ITEM"])}
    const val TITLE = {kstr(d["TITLE"])}
    const val SEARCH = {kstr(d["SEARCH"])}
    const val PAGE_STYLE = {kstr(d["PAGE_STYLE"])}
    const val PAGE_PARAM = {kstr(d["PAGE_PARAM"])}
    const val POSTER = {kstr(d["POSTER"])}
    const val DESC = {kstr(d["DESC"])}
    const val GENRE = {kstr(d["GENRE"])}
    const val EPISODE = {kstr(d["EPISODE"])}
    const val EPISODES_DESC = {b(d["EPISODES_DESC"])}
    const val USE_OG_IMAGE = {b(d["USE_OG_IMAGE"])}
    const val USE_OG_DESC = {b(d["USE_OG_DESC"])}
    const val PLAYER = {kstr(d["PLAYER"])}
    val PLAYER_ATTRS = listOf({attrs})
    val CATEGORIES: List<Pair<String, String>> = listOf({cats_block})
}}
"""


def write_report(rows: list) -> None:
    lines = ["# Laporan deteksi selector", "",
             "Dibuat otomatis oleh `detect_selectors.py` dari fixture HTML nyata (tanpa akses situs). "
             "❌ = tidak ada buktinya di HTML; runtime memakai selector bawaan/heuristik. "
             "Kategori diambil dari menu situs dan belum diuji ke situs.", "",
             "| Plugin | Fixture | Item | Judul | Cari | Halaman | Kategori | Deskripsi | Genre | Episode | Pemutar |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    ok = lambda v: "✅" if v else "❌"
    other, warns = [], []
    for r in rows:
        d = r["d"]
        if d is None:
            other.append(f"- **{r['name']}**: {r['status']}")
            continue
        lines.append(f"| {r['name']} | {r.get('hash') or '-'} | ✅ | {ok(d['TITLE'])} | {ok(d['SEARCH'])} | "
                     f"{ok(d['PAGE_STYLE'] != 'none')} | {len(d['CATEGORIES'])} | {ok(d['DESC'] or d['USE_OG_DESC'])} | "
                     f"{ok(d['GENRE'])} | {ok(d['EPISODE'])} | {ok(d.get('_player_found'))} |")
        warns += [f"- **{r['name']}**: {w}" for w in r.get("warn", [])]
    if other:
        lines += ["", "Tidak diproses / gagal:", ""] + other
    if warns:
        lines += ["", "Peringatan:", ""] + warns
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    force = bool(os.environ.get("FORCE_DETECT"))
    today = datetime.datetime.now(datetime.timezone.utc).date()
    rep = registry.Report()
    registry.parse_domains((ROOT / "domains.yml").read_text(encoding="utf-8"), rep)
    rows, failed = [], False
    for e in (x for x in rep.entries if x.active):
        name, base = e.name, e.url.rstrip("/")
        folder = ROOT / name
        files = list(folder.rglob("Selectors.kt")) if folder.is_dir() else []
        if not files:
            continue
        probs = fu.problems(ROOT, name, base)
        if probs:
            failed = True
            print(f"[TOLAK] {name}: fixture HTML tidak memenuhi syarat: " + "; ".join(probs), file=sys.stderr)
            rows.append({"name": name, "status": "DITOLAK, fixture HTML tidak memenuhi syarat: " + "; ".join(probs), "d": None})
            continue
        sel_file = files[0]
        old = sel_file.read_text(encoding="utf-8")
        m = HEADER_RE.match(old)
        if not m:
            print(f"[KUNCI] {name}: Selectors.kt dikunci manual")
            rows.append({"name": name, "status": "dikunci manual", "d": None})
            continue
        stamp = m.group(1)
        fx_hash = fixture_hash(name)
        if not (force or fx_hash != m.group(3) or stamp in (None, "default")):
            print(f"[LEWAT] {name}: fixture tidak berubah sejak {stamp}")
            rows.append({"name": name, "status": f"fixture tidak berubah (terakhir {stamp})", "d": None})
            continue
        try:
            fx = load_fixtures(name)
            d = detect_from_fixtures(base, fx, list_fixture_path(name))
            fatal, warn = validate_selectors(d, fx, base)
            if fatal:
                raise RuntimeError("; ".join(fatal))
        except Exception as ex:
            failed = True
            print(f"[GAGAL] {name}: {ex}", file=sys.stderr)
            rows.append({"name": name, "status": f"gagal: {ex}", "d": None})
            continue
        new_text = render(sel_file.parent.name, d, str(today), fx_hash, name)
        changed = old.split("\n", 1)[1:] != new_text.split("\n", 1)[1:]
        sel_file.write_text(new_text, encoding="utf-8")
        print(f"[{'UBAH' if changed else 'SAMA'}] {name}: skor {score(d)}/9 (dari fixture {fx_hash})")
        for w in warn:
            print(f"  - {w}")
        # version dinaikkan oleh bump_versions.py (jalan sesudah skrip ini)
        rows.append({"name": name, "status": "ok", "d": d, "warn": warn, "hash": fx_hash})
    write_report(rows)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
