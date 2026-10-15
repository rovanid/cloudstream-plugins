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
NAV_SEL = ("nav a, header a, .menu a, #menu a, ul.menu a, .navbar a, [role=navigation] a, "
           '[class*="menu"] a, [class*="nav-"] a, ul.nav a, [id*="menu"] a')
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


def real_href(a) -> bool:
    h = (a.get("href") or "").strip()
    return bool(h) and not h.startswith(("#", "javascript:", "mailto:", "tel:"))


def card_link(el):
    """<a> detail kartu: <a> itu sendiri, atau <a> yang membungkus poster, atau <a> nyata pertama."""
    if el.name == "a" and real_href(el):
        return el
    links = [a for a in el.find_all("a", href=True) if real_href(a)]
    for a in links:
        if a.find("img"):
            return a
    return links[0] if links else None


def card_href(el):
    a = card_link(el)
    return a["href"] if a else None


def norm(base: str, href: str) -> str:
    return urljoin(base, href).split("#")[0].rstrip("/")


def meta(soup, prop: str) -> str:
    m = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return (m.get("content") or "").strip() if m else ""


# ------------------------------------------------------------------ deteksi
SIDE_RE = re.compile(r"(?:^|[\s_-])(?:sidebar|side|widget|widgets|aside|popular|trending|related|recommend\w*|"
                     r"rekomendasi|terpopuler|footer|slider|carousel|comments?|disqus)(?:$|[\s_-])", re.I)


def _side_context(el) -> bool:
    """Elemen berada di sidebar/widget/rekomendasi/footer/komentar (bukan konten utama)."""
    for p in el.parents:
        if p.name in ("aside", "footer"):
            return True
        if SIDE_RE.search(" ".join(p.get("class") or []) + " " + (p.get("id") or "")):
            return True
    return False


def _in_main(el) -> bool:
    return any(p.name == "main" or p.get("role") == "main" for p in el.parents)


def selector_for(el, soup, max_up: int = 3) -> str:
    """Selector terpendek yang match PERTAMA-nya tepat elemen ini (id, kelas sendiri, leluhur berkelas, tag)."""
    own = sig(el)
    cands = []
    if re.fullmatch(r"[A-Za-z][\w-]{1,30}", el.get("id") or "") and not re.search(r"\d{2,}", el.get("id")):
        cands.append("#" + el["id"])
    if stable_classes(el):
        cands.append(own)
    anc, steps = el.parent, 0
    while anc is not None and anc.name not in ("[document]", "html", "body") and steps < max_up:
        if stable_classes(anc):
            cands += [f"{sig(anc)} {own}", f"{sig(anc)} > {own}"]
        anc, steps = anc.parent, steps + 1
    cands.append(own)
    for c in cands:
        try:
            if soup.select_one(c) is el:
                return c
        except Exception:
            continue
    return ""


def _alike(a, b) -> bool:
    """Saudara sejenis: tag sama dan (berbagi kelas stabil, atau keduanya tanpa kelas)."""
    if a.name != b.name:
        return False
    ca, cb = set(stable_classes(a)), set(stable_classes(b))
    return bool(ca & cb) or (not ca and not cb)


def _split_by_classes(cards) -> list:
    """Kelompokkan kartu yang berbagi kelas (hot/new tetap satu jenis; bs vs bsz terpisah)."""
    subs = []                                        # [kelas_gabungan, kartu]
    for c in cards:
        cs = set(stable_classes(c))
        for sub in subs:
            if (cs & sub[0]) or (not cs and not sub[0]):
                sub[0] |= cs
                sub[1].append(c)
                break
        else:
            subs.append([cs, [c]])
    return [sub[1] for sub in subs]


def linkless_cards(soup):
    """(selector, jumlah) unit poster berulang (>= 4) yang TIDAK punya tautan detail sama sekali; None bila tak ada.
    Hanya untuk diagnosis: tautan dibuat JavaScript saat klik, sehingga tidak ada bukti URL di HTML tersimpan."""
    seen, counts = set(), Counter()
    for img in soup.find_all("img"):
        if any(p.name in ("header", "footer", "nav") for p in img.parents):
            continue
        for anc in img.parents:
            par = anc.parent
            if anc.name in ("body", "html", "[document]") or par is None:
                break
            if sum(1 for sib in par.find_all(anc.name, recursive=False) if _alike(anc, sib)) >= 4:
                if id(anc) not in seen and not card_href(anc):
                    seen.add(id(anc))
                    counts[sig(anc)] += 1
                break
    return counts.most_common(1)[0] if counts and counts.most_common(1)[0][1] >= 4 else None


def _internal_href(href: str, base: str) -> bool:
    """Tautan relatif atau satu host dengan situs (bukan iklan/pemendek URL ke luar)."""
    if not href.startswith(("http://", "https://", "//")):
        return True
    return fu.norm_host(urlparse(urljoin(base + "/", href)).netloc) == fu.norm_host(urlparse(base).netloc)


def find_items(soup, base: str = ""):
    """Kartu = unit terendah di atas <img> yang berulang (>= 4 saudara sejenis di induk yang sama) dan punya
    tautan detail. Tidak bergantung pada nama kelas atau jumlah <img> per kartu (badge/ikon/noscript boleh
    ada). Grup dengan tautan berbeda terbanyak = daftar utama; selector dipilih yang cocok dengan SEMUA kartu."""
    seen, groups = set(), defaultdict(list)
    for img in soup.find_all("img"):
        if any(p.name in ("header", "footer", "nav") for p in img.parents):
            continue
        for anc in img.parents:
            par = anc.parent
            if anc.name in ("body", "html", "[document]") or par is None or par.name in ("[document]", "html"):
                break
            if not card_href(anc):
                continue
            if sum(1 for sib in par.find_all(anc.name, recursive=False) if _alike(anc, sib)) < 4:
                continue
            if id(anc) not in seen:
                seen.add(id(anc))
                groups[(anc.name, tuple(sig(x) for x in [par, *list(par.parents)[:2]] if x.name != "[document]"),
                    _side_context(anc))].append(anc)      # induk + 2 leluhur: section utama vs tab trending terpisah
            break
    best, best_n, best_score = None, 0, 0.0
    fb, fb_n, fb_score = None, 0, 0.0                 # cadangan: grup terbaik tanpa memandang tautan keluar
    for cards in groups.values():
        for sub in _split_by_classes(cards):          # jenis kartu berbeda di induk yang sama dipisah
            hrefs = {card_href(c) for c in sub}
            n = len(hrefs)
            # daftar utama menang atas widget sidebar yang lebih panjang: konteks sidebar/rekomendasi dikurangi
            ctx = (0.35 if _side_context(sub[0]) else 1.0) * (1.5 if _in_main(sub[0]) else 1.0)
            if n * ctx > fb_score:
                fb, fb_n, fb_score = sub, n, n * ctx
            n_int = sum(1 for h in hrefs if _internal_href(h, base)) if base else n   # banner iklan tak dihitung
            if n_int * ctx > best_score:
                best, best_n, best_score = sub, n, n_int * ctx
    if best is None:
        best, best_n = fb, fb_n                       # validator yang menolaknya dengan alasan jelas
    if best is None or best_n < 4:
        return None
    cards, n = best, len(best)
    counts = Counter(c for el in cards for c in stable_classes(el))
    common = [c for c, k in counts.most_common() if k >= 0.9 * n]
    name, p = cards[0].name, cards[0].parent
    cands = []
    if common:
        cands += [f"{name}.{c}" for c in common[:4]]
        cands += [name + "".join("." + c for c in common[:3]), name + "".join("." + c for c in common)]
        cands += [f"{sig(p)} > {name}.{c}" for c in common[:2]]
    cands.append(f"{sig(p)} > {name}")
    if p.parent is not None and p.parent.name not in ("[document]", "html"):
        cands.append(f"{sig(p.parent)} > {sig(p)} > {name}")
    deep = []                                            # selector dalam/rapuh: hanya bila tak ada yang pendek
    chain, node = [name + (f".{common[0]}" if common else "")], p                              # rantai anak-langsung 2..4 tingkat: "a > b > c > kartu"
    for _ in range(4):
        if node is None or node.name in ("[document]", "html", "body"):
            break
        chain.insert(0, sig(node))
        if len(chain) >= 4:
            deep.append(" > ".join(chain))
        node = node.parent
    # leluhur pembeda (mis. section utama vs tab trending) bila selector di atas ikut menyeret kartu lain
    for anc in list(p.parents)[:6]:
        if anc.name in ("[document]", "html", "body") or not stable_classes(anc):
            continue
        deep.append(f"{sig(anc)} {name}" + (f".{common[0]}" if common else ""))
    ids = {id(c) for c in cards}
    loose = None
    for sel in cands:
        try:
            found = soup.select(sel)
        except Exception:
            continue
        fid = {id(f) for f in found}
        if not ids <= fid:
            continue
        if fid == ids:                                  # selector eksak (tak menyeret kartu sidebar) menang
            return sel, cards
        if loose is None and len(found) <= max(2 * n, n + 6):
            loose = sel
    if loose:       # selector pendek tahan lintas halaman (beranda vs /movies/); kelebihan kartu dilaporkan validator
        return loose, cards
    for sel in deep:
        try:
            found = soup.select(sel)
        except Exception:
            continue
        if {id(f) for f in found} == ids:
            return sel, cards
    return None


def _detect_title_fixed(cards) -> str:
    sample = cards[:12]
    for sel in ["h2", "h3", "h4", "h5", "h6", "[class*=title]", ".name", "[class*=name]", "strong"]:
        texts = []
        for c in sample:
            el = c.select_one(sel)
            t = el.get_text(" ", strip=True) if el else ""
            if 2 <= len(t) <= 150:
                texts.append(t)
        if len(texts) >= 0.8 * len(sample) and len(set(texts)) >= 0.8 * len(texts):
            return sel
    return ""


def _txt(t) -> str:
    return re.sub(r"\s+", " ", t or "").strip().lower()


def _title_refs(card) -> set:
    a, img = card_link(card), card.find("img")
    refs = {_txt(a.get("title")) if a else "", _txt(img.get("alt")) if img else "",
            _txt(a.get_text(" ")) if a else ""}
    return {r for r in refs if len(r) >= 3}


def detect_title(cards) -> str:
    """Judul = elemen di dalam kartu yang TEKSNYA sama dengan title/alt/teks tautan detail kartu itu
    (bukan nama kelas). Kandidat diambil dari elemen berteks pada kartu contoh; daftar tetap hanya cadangan."""
    sample = cards[:12]
    refs = [_title_refs(c) for c in sample]
    cands = {}
    for c in sample[:3]:
        for el in c.find_all(True):
            if el.name in ("img", "script", "style", "svg", "i", "br", "source", "noscript"):
                continue
            if 2 <= len(el.get_text(" ", strip=True)) <= 150:
                cands.setdefault(sig(el, 2), el)
    best, best_score = "", 0.0
    for sel in cands:
        try:
            texts = [((c.select_one(sel).get_text(" ", strip=True)) if c.select_one(sel) else "") for c in sample]
        except Exception:
            continue
        ok = [t for t in texts if 2 <= len(t) <= 150 and not re.fullmatch(r"[\d\s.,:/%-]+", t)]
        if len(ok) < 0.8 * len(sample) or len(set(ok)) < 0.8 * len(ok):
            continue
        match = sum(1 for t, r in zip(texts, refs)
                    if len(_txt(t)) >= 3 and any(_txt(t) in x or x in _txt(t) for x in r)) / len(sample)
        if match < 0.6:
            continue
        tag = sel.split(".")[0]
        score = (match * 3 + (1 if re.fullmatch(r"h[1-6]", tag) else 0) + (0.5 if re.search(r"title|name|judul", sel, re.I) else 0)
                 - 0.001 * len(sel) - 0.01 * sum(len(t) for t in ok) / len(ok))
        if score > best_score:
            best, best_score = sel, score
    return best or _detect_title_fixed(cards)


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
    return sorted(found.items(), key=lambda kv: kv[0].strip("/").count("/"))[:limit]   # tingkat atas dulu (stabil)


DESC_HINT = re.compile(r"syn|desc|summary|plot|story|overview|sinopsis|content", re.I)


def detect_desc(detail, og_desc: str = "", min_len: int = 100) -> str:
    """Blok teks terpanjang yang rendah tautan di luar sidebar/footer/komentar; blok yang memuat awal
    meta description didahulukan. Kembali \"\" bila tak ada."""
    ref = _txt(og_desc or meta(detail, "description") or meta(detail, "og:description"))[:40]
    best, best_score = None, 0
    for el in detail.find_all(["p", "div", "span", "section", "article"]):
        if any(p.name in ("header", "nav", "script", "style", "form") for p in el.parents) or _side_context(el):
            continue
        if el.name != "p" and el.find(["p", "div", "section", "article", "ul", "ol", "table"]):
            continue
        text = el.get_text(" ", strip=True)
        if len(text) < min_len or sum(len(a.get_text(" ", strip=True)) for a in el.find_all("a")) > 0.3 * len(text):
            continue
        sc = min(len(text), 2000) + (5000 if ref and ref in _txt(text) else 0) \
            + (300 if any(DESC_HINT.search(c) for c in el.get("class") or []) else 0)
        if sc > best_score:
            best, best_score = el, sc
    if best is None:
        return ""
    par = best.parent
    if best.name == "p" and par is not None and stable_classes(par) and not _side_context(par):
        own, whole = len(best.get_text(" ", strip=True)), len(par.get_text(" ", strip=True))
        if whole <= 3 * own + 50:                      # seluruh paragraf sinopsis, bukan hanya satu <p>
            best = par
    return selector_for(best, detail)


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


PAGINATION_HREF = re.compile(r"/page/\d+|[?&](?:page|paged|p|halaman)=\d+", re.I)


def numbered_link_group(soup, base_url, min_count: int = 3) -> list:
    """Cadangan bila teks/URL tak memuat kata 'episode': tautan satu host yang bernomor, berulang sebagai
    unit sejenis (li/div/a) dalam satu induk, dengan bentuk URL sama (angka diganti #). Pagination, tahun,
    dan area sidebar/rekomendasi/menu dibuang."""
    host = urlparse(base_url).netloc
    groups = defaultdict(list)
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if not real_href(a) or not re.search(r"\d", text) or re.fullmatch(r"(?:19|20)\d\d", text):
            continue
        if urlparse(urljoin(base_url, a["href"])).netloc != host or PAGINATION_HREF.search(a["href"]):
            continue
        if _side_context(a) or any(p.name in ("header", "footer", "nav") for p in a.parents):
            continue
        for anc in [a, *a.parents]:
            par = anc.parent
            if par is None or anc.name in ("body", "html", "[document]"):
                break
            if sum(1 for sib in par.find_all(anc.name, recursive=False) if _alike(anc, sib)) >= min_count:
                groups[id(par)].append(a)
                break
    best = []
    for g in groups.values():
        top = Counter(re.sub(r"\d+", "#", urlparse(a["href"]).path) for a in g).most_common(1)[0][1]
        if len(g) >= min_count and top >= 0.8 * len(g) and len({a["href"] for a in g}) >= min_count and len(g) > len(best):
            best = g
    return best


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
        anchors = numbered_link_group(soup, page_url_)
    if len(anchors) < min_count:
        return "", True
    ep_ids = {id(a) for a in anchors}
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
        good = [a for a in found if id(a) in ep_ids or is_ep(a)]
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


PLAYER_CTX = re.compile(r"play|video|embed|stream|movie-?box|watch", re.I)
DATA_BAD = re.compile(r"share|href|image|img|poster|thumb|bg|background|ajax|nonce|cover|srcset|tooltip|title", re.I)


def _dyn_embed(value: str, base: str) -> bool:
    """Atribut data-* di luar daftar bawaan butuh bukti lebih: base64 embed, URL host lain, atau URL bernuansa pemutar
    (bukan sekadar tautan halaman situs sendiri seperti data-article-url)."""
    v = (value or "").strip()
    if not v.startswith(("http://", "https://", "//")):
        return True                                  # base64 yang sudah lolos embed_like
    u = urlparse(urljoin(base + "/", v))
    return u.netloc != urlparse(base).netloc or bool(re.search(r"embed|player|stream|video|iframe|/[ev]/", u.path, re.I))


def player_attrs(soup) -> list:
    """Atribut bawaan + atribut data-* lain di dokumen (bukan share/gambar); nilainya tetap harus tampak embed."""
    attrs = [a for a in PLAYER_ATTRS if a != "src"]
    for el in soup.find_all(True):
        if el.name in NON_PLAYER_TAGS:
            continue
        for k in el.attrs:
            if k.startswith("data-") and k not in attrs and not DATA_BAD.search(k):
                attrs.append(k)
    return attrs


def detect_player(soup, base) -> str:
    """Selector pemutar yang terbukti ada di halaman episode nyata. Elemen beratribut embed
    (mis. `select.mirror option[data-em]`) didahulukan; "iframe" polos hanya bila tak ada yang lebih konkret.
    Catatan: Chrome menulis ulang src iframe MHTML menjadi cid:..., jadi iframe berstatus cid: tetap dihitung."""
    found = []
    for attr in player_attrs(soup):
        if found and attr not in PLAYER_ATTRS:       # atribut data-* lain hanya cadangan bila yang bawaan nihil
            break
        for el in soup.select(f"[{attr}]"):
            if el.name in NON_PLAYER_TAGS or (attr == "value" and el.name != "option"):
                continue
            if not embed_like(el.get(attr)) or (attr not in PLAYER_ATTRS and not _dyn_embed(el.get(attr), base)):
                continue
            parent = next((p for p in list(el.parents)[:2] if stable_classes(p)), None)
            sel = (f"{sig(parent)} " if parent is not None else "") + f"{el.name}[{attr}]"
            if sel not in found:
                found.append(sel)
            break                                   # satu contoh per atribut cukup
    if found:
        return ",".join(found[:3])
    frames = soup.select("iframe")
    # iframe di dalam wadah bernuansa pemutar (player/video/embed/stream) didahulukan atas iframe lain (iklan, dll.)
    frames.sort(key=lambda f: 0 if any(PLAYER_CTX.search(" ".join(p.get("class") or []) + " " + (p.get("id") or ""))
                                       for p in f.parents) else 1)
    for el in frames:
        src = (el.get("src") or el.get("data-src") or "").strip()
        if not src or src.startswith("cid:") or embed_like(src):
            if not SKIP_PLAYER.search(src):
                return selector_for(el, soup) or "iframe"
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
    items = find_items(home, base)
    if not items:
        nolink = linkless_cards(home)
        if nolink:
            raise RuntimeError(f"ditemukan {nolink[1]} kartu berulang ('{nolink[0]}') tetapi TANPA tautan detail: URL film "
                               "dibuat JavaScript saat diklik dan tidak ada di HTML tersimpan. Tidak ditebak; unggah halaman "
                               "daftar yang memuat <a href> ke halaman detail (mis. hasil pencarian, /genre/..., atau halaman 2)")
        raise RuntimeError("daftar item tidak ditemukan di list.html (fixture bukan halaman daftar, "
                           "atau daftarnya dimuat JavaScript sehingga tidak ikut tersimpan)")
    item_sel, cards = items
    d["ITEM"] = item_sel
    d["_item_extra"] = len(home.select(item_sel)) - len(cards)   # kartu di luar daftar utama yang ikut cocok
    d["TITLE"] = detect_title(cards)
    d["PAGE_STYLE"], d["PAGE_PARAM"] = detect_paging(home, base)
    d["SEARCH"] = detect_search(home, base)
    d["CATEGORIES"] = detect_categories(home, base, list_path)

    detail = fx.get("detail")
    if detail is not None:
        og_img, og_desc = meta(detail, "og:image"), meta(detail, "og:description")
        d["USE_OG_IMAGE"] = bool(og_img) and og_img != meta(home, "og:image")
        d["USE_OG_DESC"] = bool(og_desc) and og_desc != meta(home, "og:description")
        d["DESC"] = detect_desc(detail, og_desc) or first_ok(detail, [".synopsis", ".sinopsis", "[itemprop=description]", ".description",
                                      ".desc", ".summary", ".entry-content p"])
        if not d["USE_OG_IMAGE"]:
            d["POSTER"] = detect_poster(detail)
        d["GENRE"] = detect_genre(detail)
        d["EPISODE"], d["EPISODES_DESC"] = detect_episodes(detail, base + "/", min_count=1)

    player_page = fx.get("episode") or (detail if not d["EPISODE"] else None)
    d_player = detect_player(player_page, base) if player_page is not None else ""
    if d_player:
        d["PLAYER"] = d_player
        d["_extra_attrs"] = [a for a in re.findall(r"\[([\w-]+)\]", d_player) if a not in PLAYER_ATTRS]
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
    else:
        if len({norm(base, card_href(c)) for c in with_link}) < 3:
            fatal.append("tautan detail kartu ITEM kurang dari 3 yang berbeda (bukan daftar judul)")
        if sum(1 for c in cards if c.find("img")) < 0.8 * len(cards):
            fatal.append(f"ITEM '{d['ITEM']}' bukan kartu berposter: kurang dari 80% punya <img>")
    if d.get("_item_extra", 0) > 0:
        warn.append(f"ITEM '{d['ITEM']}' juga cocok dengan {d['_item_extra']} kartu di luar daftar utama "
                    "(mis. tab trending/sidebar); dipertahankan karena selector lebih spesifik rapuh antar halaman")
    if cards and d["TITLE"]:
        titled = sum(1 for c in cards if (c.select_one(d["TITLE"]) and c.select_one(d["TITLE"]).get_text(strip=True)))
        if titled < 0.8 * len(cards):
            warn.append(f"TITLE '{d['TITLE']}' kosong di {len(cards) - titled} dari {len(cards)} kartu")
    host = fu.norm_host(urlparse(base).netloc)
    absolute = [urlparse(card_href(c)) for c in with_link if (card_href(c) or "").startswith(("http://", "https://"))]
    if absolute and sum(1 for u in absolute if fu.norm_host(u.netloc) == host) < 0.5 * len(absolute):
        fatal.append(f"ITEM '{d['ITEM']}' bukan daftar situs: kurang dari separuh tautan kartu mengarah ke {host} "
                     "(kemungkinan banner iklan/tautan keluar); tidak ada kartu berposter dengan tautan detail internal")
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
    attrs = ", ".join(kstr(a) for a in PLAYER_ATTRS + d.get("_extra_attrs", []))
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
        tmp = sel_file.with_name(sel_file.name + ".tmp")      # tulis atomik: gagal di tengah tidak merusak berkas lama
        tmp.write_text(new_text, encoding="utf-8")
        os.replace(tmp, sel_file)
        print(f"[{'UBAH' if changed else 'SAMA'}] {name}: skor {score(d)}/9 (dari fixture {fx_hash})")
        for w in warn:
            print(f"  - {w}")
        # version dinaikkan oleh bump_versions.py (jalan sesudah skrip ini)
        rows.append({"name": name, "status": "ok", "d": d, "warn": warn, "hash": fx_hash})
    write_report(rows)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
