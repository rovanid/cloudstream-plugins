#!/usr/bin/env python3
"""
Deteksi selector otomatis untuk tiap plugin, lalu tulis Selectors.kt.

Yang dideteksi dari HTML situs asli:
  daftar item, judul, pagination, pencarian, kategori beranda,
  deskripsi, genre, daftar episode (+ urutannya), poster, dan pemutar (iframe/mirror).

Aturan:
  - File Selectors.kt dengan baris pertama "// @auto-detect" diperbarui otomatis.
    Hapus baris itu untuk mengunci dan mengedit manual (script akan melewatinya).
  - Dideteksi ulang kalau masih default, lebih dari REFRESH_DAYS hari, atau FORCE_DETECT=1.
  - Hasil baru yang skornya lebih rendah dari hasil lama tidak menimpa (anti-downgrade).
  - Situs yang memblokir bot (Cloudflare) atau memuat daftar lewat JavaScript tidak bisa
    dideteksi; hasilnya dicatat di detection_report.md dan file lama dibiarkan.
  - MODE FIXTURE: kalau tests/kotlin/fixtures/<Plugin>/list.html ada, selector dideteksi dari
    file HTML itu (list.html, detail.html, episode.html; format MHTML dari Chrome "Simpan halaman"
    juga dibaca), BUKAN dari situs langsung. Jadi situs yang memblokir bot atau memuat daftar lewat
    JavaScript tetap bisa dideteksi. Pagination/pencarian/kategori tetap dicoba lewat jaringan
    (kalau gagal, dikosongkan). Fixture baru/berubah (sidik jari di header) memicu deteksi ulang
    dan boleh menimpa hasil lama walau skornya lebih rendah.
Butuh: pip install beautifulsoup4
"""
import datetime
import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "detection_report.md"
REFRESH_DAYS = 7
DELAY = float(os.environ.get("DETECT_DELAY", "0.5"))
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")

HEADER_RE = re.compile(r"^// @auto-detect(?:\s*\|\s*detected:\s*(\S+))?(?:\s*\|\s*score:\s*(\d+))?(?:\s*\|\s*fixtures:\s*(\w+))?")
FIXTURES = ROOT / "tests" / "kotlin" / "fixtures"
FIXTURE_KINDS = ("list", "detail", "episode")
EP_RE = re.compile(r"(episode|\beps?\b[ ._-]?\d+|\bep[ ._-]?\d+|chapter|/eps?[-/])", re.I)
SKIP_PLAYER = re.compile(r"facebook\.com|disqus\.com|googletagmanager|recaptcha", re.I)
CAT_OK = re.compile(r"genre|categor|kategori|series|movie|film|anime|ongoing|complete|"
                    r"popul|terbaru|latest|tv|donghua|drama|new|top", re.I)
CAT_BAD = re.compile(r"login|register|daftar|dmca|contact|kontak|about|privacy|jadwal|"
                     r"schedule|request|wp-|feed|#|\.xml|disclaimer|faq|tos|terms", re.I)
PLAYER_CANDS = ["iframe", "option[value]", "[data-video]", "[data-embed]", "[data-iframe]", "[data-url]"]
PLAYER_ATTRS = ["src", "data-src", "data-lazy-src", "data-litespeed-src", "value",
                "data-video", "data-embed", "data-iframe", "data-url", "data-em"]


class Blocked(Exception):
    pass


# ---------------------------------------------------------------- jaringan
def fetch(url: str, strict: bool = False):
    """Return (final_url, soup) atau None. strict=True: lempar Blocked kalau diblokir bot."""
    time.sleep(DELAY)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "id,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, final = r.status, r.geturl()
            body = r.read(1_500_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        status, final = e.code, url
        try:
            body = e.read(200_000).decode("utf-8", "ignore")
        except Exception:
            body = ""
    except Exception:
        return None
    head = body[:20000].lower()
    if status in (403, 429, 503) or "just a moment" in head or "cf-chl" in head:
        if strict:
            raise Blocked
        return None
    if status != 200:
        return None
    return final, BeautifulSoup(body, "html.parser")


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


def page_url(base: str, page: int, style: str, param: str) -> str:
    if style == "path":
        return base.rstrip("/") + f"/page/{page}/"
    return base + ("&" if "?" in base else "?") + f"{param}={page}"


def hrefs_of(soup, sel, base) -> set:
    return {norm(base, card_href(c)) for c in soup.select(sel) if card_href(c)}


def detect_paging(home_url, item_sel, first_hrefs):
    for style, param in [("path", ""), ("query", "page"), ("query", "paged")]:
        res = fetch(page_url(home_url, 2, style, param))
        if not res:
            continue
        final, soup = res
        hrefs = hrefs_of(soup, item_sel, final)
        if len(hrefs) >= 3 and len(hrefs - first_hrefs) >= 2:
            return style, (param or "page")
    return "none", "page"


def detect_search(base, home_soup, item_sel, known_title, known_href, home_hrefs):
    words = re.sub(r"[^\w ]", " ", known_title).split()
    word = " ".join(words[:2]) if words else known_title
    cands = []
    for form in home_soup.find_all("form"):
        for inp in form.find_all("input"):
            if inp.get("name") in ("s", "q", "query", "keyword", "search", "k", "term"):
                path = urlparse(urljoin(base + "/", form.get("action") or "/")).path or "/"
                cands.append(f"{path}?{inp['name']}={{q}}")
    cands += ["/?s={q}", "/search?keyword={q}", "/search?q={q}", "/search/{q}",
              "/?search={q}", "/search?query={q}", "/search.php?q={q}"]
    seen = set()
    for t in cands:
        if t in seen:
            continue
        seen.add(t)
        res = fetch(base + t.replace("{q}", quote(word)))
        if not res:
            continue
        final, soup = res
        links = {norm(final, a["href"]) for a in soup.find_all("a", href=True)}
        # harus memuat item yang dicari DAN bukan sekadar beranda (situs sering
        # mengembalikan beranda untuk parameter yang tidak dikenal)
        if known_href in links and hrefs_of(soup, item_sel, final) != home_hrefs:
            return t
    return ""


def detect_categories(base, home_soup, item_sel, home_hrefs, limit=8):
    host = urlparse(base).netloc
    found = {}
    for a in home_soup.select("nav a, header a, .menu a, #menu a, ul.menu a, .navbar a"):
        href = a.get("href") or ""
        text = a.get_text(" ", strip=True)
        full = urljoin(base + "/", href)
        u = urlparse(full)
        if u.netloc != host or not (2 <= len(text) <= 25):
            continue
        path = u.path.rstrip("/") + "/" if u.path.strip("/") else ""
        if not path or path.count("/") > 3:
            continue
        key = path + (f"?{u.query}" if u.query else "")
        if CAT_BAD.search(key) or CAT_BAD.search(text) or not (CAT_OK.search(key) or CAT_OK.search(text)):
            continue
        found.setdefault(key, text)
    # Hanya kategori dari menu situs sendiri yang TERVERIFIKASI berisi daftar item.
    # Tidak ada entri "Terbaru" otomatis.
    cats = []
    for key, text in list(found.items())[:limit * 2]:
        if len(cats) >= limit:
            break
        res = fetch(base + key)
        if not res:
            continue
        final, soup = res
        hrefs = hrefs_of(soup, item_sel, final)
        if len(hrefs) >= 6 and len(hrefs - home_hrefs) >= len(hrefs) * 0.5:
            cats.append((key, text))
    return cats


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


def detect_episodes(soup, page_url_):
    """Return (selector, descending) atau ("", True)."""
    host = urlparse(page_url_).netloc

    def is_ep(a):
        return EP_RE.search(a.get_text(" ", strip=True) + " " + (a.get("href") or "")) is not None

    anchors = [a for a in soup.find_all("a", href=True)
               if urlparse(urljoin(page_url_, a["href"])).netloc == host and is_ep(a)]
    if len(anchors) < 3:
        return "", True
    cands = Counter()
    for a in anchors:
        for anc in list(a.parents)[:4]:
            if anc.name in ("body", "html") or not stable_classes(anc):
                continue
            cands[f"{sig(anc)} a"] += 1
            break
    for tok in ("episode", "/eps", "-ep-", "/ep-"):
        cands[f"a[href*='{tok}']"] += 0
    ordered = [s for s, _ in cands.most_common()]
    for sel in ordered:
        try:
            found = soup.select(sel)
        except Exception:
            continue
        good = [a for a in found if is_ep(a)]
        if len(found) >= 3 and len(good) >= 0.7 * len(found) and len(found) <= len(anchors) * 1.5 + 3:
            nums = []
            for a in found:
                m = re.search(r"\d+", a.get_text(" ", strip=True))
                if m:
                    nums.append(int(m.group()))
            desc = not (len(nums) >= 2 and nums[0] < nums[-1])
            return sel, desc
    return "", True


def detect_player(soup, base) -> str:
    good = []
    for sel in PLAYER_CANDS:
        for el in soup.select(sel):
            url = next(((el.get(a) or "").strip() for a in PLAYER_ATTRS if (el.get(a) or "").strip()), "")
            if url.startswith(("http", "//")) and not SKIP_PLAYER.search(url):
                good.append(sel)
                break
    return ",".join(good)


# --------------------------------------------------------------- fixture
def extract_html(raw: str) -> str:
    """Chrome 'Simpan halaman' berformat MHTML (Saved by Blink): ambil bagian text/html pertama."""
    if not raw.lstrip().startswith("From:") or "Saved by Blink" not in raw:
        return raw
    m = re.search(r'boundary="?([^"\r\n;]+)"?', raw)
    if not m:
        return raw
    for part in raw.split("--" + m.group(1))[1:]:
        sep = re.search(r"\r?\n\r?\n", part)
        if not sep:
            continue
        if re.search(r"(?i)content-type:\s*text/html", part[:sep.start()]):
            return part[sep.end():]
    return raw


def fixture_paths(name: str) -> dict:
    d = FIXTURES / name
    return {k: d / f"{k}.html" for k in FIXTURE_KINDS if (d / f"{k}.html").is_file()}


def fixture_hash(name: str) -> str:
    """Sidik jari isi fixture; kosong kalau list.html tidak ada (mode fixture tidak aktif)."""
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


def detect_from_fixtures(base: str, fx: dict) -> dict:
    """Seperti detect_site, tetapi struktur HTML dibaca dari fixture, bukan dari situs."""
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
    first_hrefs = hrefs_of(home, item_sel, base)

    # Pagination, pencarian, kategori perlu diuji ke situs; kalau diblokir/gagal tetap kosong.
    first = cards[0]
    known_href = norm(base, card_href(first))
    known_title = (first.select_one(d["TITLE"]).get_text(" ", strip=True) if d["TITLE"] and first.select_one(d["TITLE"])
                   else (first.find("a", title=True) or {}).get("title", "") or
                   (first.find("img", alt=True) or {}).get("alt", "") or "a")
    try:
        d["PAGE_STYLE"], d["PAGE_PARAM"] = detect_paging(base, item_sel, first_hrefs)
        d["SEARCH"] = detect_search(base, home, item_sel, known_title, known_href, first_hrefs)
        d["CATEGORIES"] = detect_categories(base, home, item_sel, first_hrefs)
    except Exception as e:  # jaringan bermasalah tidak boleh menggagalkan hasil fixture
        print(f"  (jaringan dilewati: {e})")

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
        d["EPISODE"], d["EPISODES_DESC"] = detect_episodes(detail, base + "/")

    player_page = fx.get("episode") or (detail if not d["EPISODE"] else None)
    d_player = detect_player(player_page, base) if player_page is not None else ""
    if d_player:
        d["PLAYER"] = d_player
    d["_player_found"] = bool(d_player)
    return d


# ---------------------------------------------------------- satu plugin
def detect_site(base: str) -> dict:
    res = fetch(base, strict=True)
    if not res:
        raise RuntimeError("halaman utama tidak bisa dibuka")
    final, home = res
    d = {"PAGE_PARAM": "page", "PAGE_STYLE": "none", "SEARCH": "", "TITLE": "", "POSTER": "",
         "DESC": "", "GENRE": "", "EPISODE": "", "EPISODES_DESC": True,
         "USE_OG_IMAGE": True, "USE_OG_DESC": True, "PLAYER": "iframe",
         "CATEGORIES": []}
    items = find_items(home)
    if not items:
        raise RuntimeError("daftar item tidak ditemukan (kemungkinan dimuat lewat JavaScript)")
    item_sel, cards = items
    d["ITEM"] = item_sel
    d["TITLE"] = detect_title(cards)
    first_hrefs = hrefs_of(home, item_sel, final)

    first = cards[0]
    known_href = norm(final, card_href(first))
    known_title = (first.select_one(d["TITLE"]).get_text(" ", strip=True) if d["TITLE"] and first.select_one(d["TITLE"])
                   else (first.find("a", title=True) or {}).get("title", "") or
                   (first.find("img", alt=True) or {}).get("alt", "") or "a")

    d["PAGE_STYLE"], d["PAGE_PARAM"] = detect_paging(base, item_sel, first_hrefs)
    d["SEARCH"] = detect_search(base, home, item_sel, known_title, known_href, first_hrefs)
    d["CATEGORIES"] = detect_categories(base, home, item_sel, first_hrefs)

    detail = fetch(known_href)
    if detail:
        dfinal, dsoup = detail
        og_img, og_desc = meta(dsoup, "og:image"), meta(dsoup, "og:description")
        d["USE_OG_IMAGE"] = bool(og_img) and og_img != meta(home, "og:image")
        d["USE_OG_DESC"] = bool(og_desc) and og_desc != meta(home, "og:description")
        d["DESC"] = first_ok(dsoup, [".synopsis", ".sinopsis", "[itemprop=description]", ".description",
                                     ".desc", ".summary", ".entry-content p"])
        if not d["USE_OG_IMAGE"]:
            d["POSTER"] = detect_poster(dsoup)
        d["GENRE"] = detect_genre(dsoup)
        d["EPISODE"], d["EPISODES_DESC"] = detect_episodes(dsoup, dfinal)

        player_page = dsoup
        if d["EPISODE"]:
            eps = dsoup.select(d["EPISODE"])
            href = eps[0].get("href") if eps else None
            res2 = fetch(urljoin(dfinal, href)) if href else None
            player_page = res2[1] if res2 else None
        d_player = detect_player(player_page, base) if player_page else ""
        if not d_player and not d["EPISODE"]:
            for a in dsoup.find_all("a", href=True):
                if re.search(r"nonton|watch|play|tonton", a.get_text(" ", strip=True), re.I):
                    res3 = fetch(urljoin(dfinal, a["href"]))
                    if res3:
                        d_player = detect_player(res3[1], base)
                        break
        if d_player:
            d["PLAYER"] = d_player
        d["_player_found"] = bool(d_player)
    return d


def score(d: dict) -> int:
    s = 1  # ITEM
    s += bool(d["TITLE"]) + bool(d["SEARCH"]) + (d["PAGE_STYLE"] != "none")
    s += bool(d["DESC"] or d["USE_OG_DESC"]) + bool(d["GENRE"]) + bool(d["EPISODE"])
    s += bool(d.get("_player_found")) + (len(d["CATEGORIES"]) > 0)
    return s


# ---------------------------------------------------------------- output
def kstr(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def render(pkg: str, d: dict, date: str, fx_hash: str = "") -> str:
    cats = ",\n        ".join(f"{kstr(p)} to {kstr(n)}" for p, n in d["CATEGORIES"])
    cats_block = f"\n        {cats}\n    " if cats else ""
    attrs = ", ".join(kstr(a) for a in PLAYER_ATTRS)
    b = lambda v: "true" if v else "false"
    fx = f" | fixtures: {fx_hash}" if fx_hash else ""
    return f"""// @auto-detect | detected: {date} | score: {score(d)}{fx}
// File ini dibuat/diperbarui otomatis oleh .github/scripts/detect_selectors.py.
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


def read_flat(path: Path) -> dict:
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    force = bool(os.environ.get("FORCE_DETECT"))
    today = datetime.datetime.now(datetime.timezone.utc).date()
    rows = []
    for name, url in read_flat(ROOT / "domains.yml").items():
        folder = ROOT / name
        files = list(folder.rglob("Selectors.kt")) if folder.is_dir() else []
        if not files:
            continue
        sel_file = files[0]
        old = sel_file.read_text(encoding="utf-8")
        m = HEADER_RE.match(old)
        if not m:
            print(f"[KUNCI] {name}: Selectors.kt dikunci manual")
            rows.append((name, "dikunci manual", None))
            continue
        stamp, old_score = m.group(1), int(m.group(2) or 0)
        fx_hash = fixture_hash(name)
        fx_changed = bool(fx_hash) and fx_hash != m.group(3)
        due = force or fx_changed or stamp in (None, "default")
        if not due:
            try:
                due = (today - datetime.date.fromisoformat(stamp)).days >= REFRESH_DAYS
            except ValueError:
                due = True
        if not due:
            print(f"[LEWAT] {name}: terakhir dideteksi {stamp}")
            rows.append((name, f"belum waktunya (terakhir {stamp})", None))
            continue

        base = url.rstrip("/")
        try:
            d = detect_from_fixtures(base, load_fixtures(name)) if fx_hash else detect_site(base)
        except Blocked:
            print(f"[BLOKIR] {name}: situs memblokir bot, selector tidak diubah")
            rows.append((name, "diblokir bot (Cloudflare?), tidak bisa dideteksi otomatis", None))
            continue
        except Exception as e:
            print(f"[GAGAL] {name}: {e}")
            rows.append((name, f"gagal: {e}", None))
            continue

        new_score = score(d)
        if not fx_changed and stamp not in (None, "default") and new_score < old_score:
            print(f"[TURUN] {name}: skor {new_score} < {old_score}, hasil lama dipertahankan")
            rows.append((name, f"skor turun ({new_score} < {old_score}), hasil lama dipertahankan", None))
            continue

        pkg = sel_file.parent.name
        new_text = render(pkg, d, str(today), fx_hash)
        changed = old.split("\n", 1)[1:] != new_text.split("\n", 1)[1:]
        sel_file.write_text(new_text, encoding="utf-8")
        print(f"[{'UBAH' if changed else 'SAMA'}] {name}: skor {new_score}/9"
              + (f" (dari fixture {fx_hash})" if fx_hash else ""))
        # version dinaikkan oleh bump_versions.py (jalan sesudah skrip ini)
        rows.append((name, "ok", d))

    lines = ["# Laporan deteksi selector", "",
             "Dibuat otomatis oleh `detect_selectors.py`. Tanda ❌ berarti perlu disetel manual "
             "(hapus baris `@auto-detect` di `Selectors.kt` lalu edit).", "",
             "| Plugin | Sumber | Item | Judul | Cari | Halaman | Kategori | Deskripsi | Genre | Episode | Pemutar |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    ok = lambda v: "✅" if v else "❌"
    other = []
    for name, status, d in rows:
        if d is None:
            other.append(f"- **{name}**: {status}")
            continue
        lines.append(f"| {name} | {d.get('_source', 'situs')} | ✅ | {ok(d['TITLE'])} | {ok(d['SEARCH'])} | {ok(d['PAGE_STYLE'] != 'none')} | "
                     f"{len(d['CATEGORIES'])} | {ok(d['DESC'] or d['USE_OG_DESC'])} | {ok(d['GENRE'])} | "
                     f"{ok(d['EPISODE'])} | {ok(d.get('_player_found'))} |")
    if other:
        lines += ["", "Tidak diproses / gagal:", ""] + other
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
