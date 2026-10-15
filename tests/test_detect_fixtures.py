import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect_selectors as ds  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402
from fixture_helpers import PAD  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
BASE = "https://x.example"


def soup(h: str):
    return BeautifulSoup(h, "html.parser")


def cards(n=8, cls="ml-item"):
    return "".join(f'<div class="{cls}"><a href="/movie/film-{i}/" title="Film {i}"><img src="x{i}.jpg" alt="Film {i}"></a>'
                   f"<h2>Film {i}</h2></div>" for i in range(n))


def page(body: str, head: str = "") -> str:
    return f"<!DOCTYPE html><html><head>{head}</head><body>{body}{PAD}</body></html>"


LIST_HTML = f"<html><body><div class='wrap'>{cards()}</div></body></html>"
MHTML = ('From: <Saved by Blink>\r\nContent-Type: multipart/related;\r\n\tboundary="----B----"\r\n\r\n'
         '------B----\r\nContent-Type: text/html\r\nContent-Location: https://x/\r\n\r\n'
         f'{LIST_HTML}\r\n------B----\r\nContent-Type: image/png\r\n\r\nBINARY\r\n------B------\r\n')


class FixtureDetectTest(unittest.TestCase):
    def test_extract_html_mhtml(self):
        out = ds.extract_html(MHTML)
        self.assertIn("ml-item", out)
        self.assertNotIn("BINARY", out)

    def test_extract_html_plain_unchanged(self):
        self.assertEqual(ds.extract_html(LIST_HTML), LIST_HTML)

    def test_detect_from_fixtures_is_offline(self):
        d = ds.detect_from_fixtures(BASE, {"list": soup(ds.extract_html(MHTML))})
        self.assertEqual(d["ITEM"], "div.ml-item")
        self.assertEqual(d["TITLE"], "h2")
        self.assertEqual(d["PAGE_STYLE"], "none")
        self.assertEqual(d["_source"], "fixture")
        self.assertFalse(hasattr(ds, "fetch"), "tidak boleh ada akses jaringan lagi")

    def test_not_a_list_page_raises(self):
        with self.assertRaises(RuntimeError):
            ds.detect_from_fixtures(BASE, {"list": soup("<html><body><p>kosong</p></body></html>")})

    def test_fixture_hash_changes_with_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = ds.FIXTURES
            ds.FIXTURES = Path(tmp)
            try:
                self.assertEqual(ds.fixture_hash("AProvider"), "")
                f = Path(tmp) / "AProvider"
                f.mkdir()
                (f / "list.html").write_text("a", encoding="utf-8")
                h1 = ds.fixture_hash("AProvider")
                (f / "list.html").write_text("b", encoding="utf-8")
                self.assertTrue(h1)
                self.assertNotEqual(h1, ds.fixture_hash("AProvider"))
            finally:
                ds.FIXTURES = old

    def test_header_regex_reads_fixture_hash(self):
        m = ds.HEADER_RE.match("// @auto-detect | detected: 2026-10-14 | score: 3 | fixtures: 49318b44\n")
        self.assertEqual((m.group(1), m.group(2), m.group(3)), ("2026-10-14", "3", "49318b44"))
        m2 = ds.HEADER_RE.match("// @auto-detect | detected: default | score: 0\n")
        self.assertIsNone(m2.group(3))


class ItemTest(unittest.TestCase):
    def test_prefers_single_common_class(self):
        h = soup("<div>" + "".join(f'<article class="bs is-anime"><a href="/a{i}"><img src="i"></a></article>' for i in range(8)) + "</div>")
        self.assertEqual(ds.find_items(h)[0], "article.bs")


class PagingTest(unittest.TestCase):
    def test_path_style_from_rel_next(self):
        h = soup('<head><link rel="next" href="https://x.example/page/2/"></head><body></body>')
        self.assertEqual(ds.detect_paging(h, BASE), ("path", "page"))

    def test_query_style(self):
        h = soup('<body><div class="pagination"><a href="/list?paged=2">2</a></div></body>')
        self.assertEqual(ds.detect_paging(h, BASE), ("query", "paged"))

    def test_none_when_no_evidence(self):
        h = soup('<body><a href="/genre/action/28/">Action</a><a href="https://other.example/page/2/">x</a></body>')
        self.assertEqual(ds.detect_paging(h, BASE), ("none", "page"))


class SearchTest(unittest.TestCase):
    def test_get_form(self):
        h = soup('<form action="/" method="get"><input type="text" name="s"></form>')
        self.assertEqual(ds.detect_search(h, BASE), "/?s={q}")

    def test_hidden_params_kept(self):
        h = soup('<form action="/cari"><input name="q"><input type="hidden" name="post_type" value="anime"></form>')
        self.assertEqual(ds.detect_search(h, BASE), "/cari?q={q}&post_type=anime")

    def test_post_form_and_form_less_input_not_guessed(self):
        self.assertEqual(ds.detect_search(soup('<form method="post"><input name="s"></form>'), BASE), "")
        self.assertEqual(ds.detect_search(soup('<div id="search"><input name="keyword"></div>'), BASE), "")

    def test_foreign_host_form_ignored(self):
        self.assertEqual(ds.detect_search(soup('<form action="https://google.com/search"><input name="q"></form>'), BASE), "")


class CategoryTest(unittest.TestCase):
    NAV = ('<nav><a href="/">Home</a><a href="/movies/">Movies</a><a href="/genre/">Genre</a>'
           '<a href="/latest-movie/">Latest Movie</a><a href="/privacy-policy/">Privacy Movie</a>'
           '<a href="/daftar-anime/">Daftar Anime</a><a href="https://other.example/film/">Film Luar</a></nav>')

    def test_filters_index_self_info_and_foreign(self):
        cats = ds.detect_categories(soup(self.NAV), BASE, list_path="/movies/")
        self.assertEqual(cats, [("/latest-movie/", "Latest Movie")])

    def test_limit(self):
        nav = "<nav>" + "".join(f'<a href="/film-{i}/">Film {i}</a>' for i in range(20)) + "</nav>"
        self.assertEqual(len(ds.detect_categories(soup(nav), BASE)), 8)


class EpisodeTest(unittest.TestCase):
    EP = '<div class="entry-content"><ul class="daftar"><li><a href="/judul-episode-1/">Judul Episode 1</a></li></ul></div>'

    def test_single_episode_in_list_gets_tight_selector(self):
        sel, desc = ds.detect_episodes(soup(self.EP), BASE + "/", min_count=1)
        self.assertEqual(sel, "ul.daftar li a")
        self.assertTrue(desc)

    def test_single_link_outside_list_is_not_an_episode_list(self):
        h = soup('<div class="box"><a href="/judul-episode-1/">Episode 1</a></div>')
        self.assertEqual(ds.detect_episodes(h, BASE + "/", min_count=1), ("", True))

    def test_default_still_needs_three(self):
        self.assertEqual(ds.detect_episodes(soup(self.EP), BASE + "/"), ("", True))

    def test_ascending_order_detected(self):
        lis = "".join(f'<li><a href="/e-episode-{i}/">Episode {i}</a></li>' for i in (1, 2, 3, 4))
        sel, desc = ds.detect_episodes(soup(f'<ul class="eps">{lis}</ul>'), BASE + "/")
        self.assertEqual((sel, desc), ("ul.eps li a", False))


class PlayerTest(unittest.TestCase):
    def test_base64_mirror_options(self):
        b64 = base64.b64encode(b'<iframe src="https://v.example/embed/1"></iframe>').decode()
        h = soup(f'<select class="mirror"><option value="">Pilih</option><option data-em="{b64}">S1</option></select>'
                 '<iframe src="cid:frame-1"></iframe>')
        self.assertEqual(ds.detect_player(h, BASE), "select.mirror option[data-em]")

    def test_option_value_urls(self):
        h = soup('<select class="srv"><option value="https://v.example/a">A</option></select>')
        self.assertEqual(ds.detect_player(h, BASE), "select.srv option[value]")

    def test_image_data_src_and_share_inputs_are_not_players(self):
        h = soup('<img data-src="https://cdn.example/p.jpg"><input value="https://x.example/share">')
        self.assertEqual(ds.detect_player(h, BASE), "")

    def test_plain_iframe_and_social_iframe(self):
        self.assertEqual(ds.detect_player(soup('<iframe src="https://v.example/e"></iframe>'), BASE), "iframe")
        self.assertEqual(ds.detect_player(soup('<iframe src="cid:frame-9"></iframe>'), BASE), "iframe")
        self.assertEqual(ds.detect_player(soup('<iframe src="https://www.facebook.com/plugins/x"></iframe>'), BASE), "")


class ValidateTest(unittest.TestCase):
    def test_valid(self):
        fx = {"list": soup(page(cards()))}
        d = ds.detect_from_fixtures(BASE, fx)
        fatal, warn = ds.validate_selectors(d, fx, BASE)
        self.assertEqual(fatal, [])
        self.assertTrue(any("pencarian" in w for w in warn))

    def test_too_few_cards_is_fatal(self):
        fx = {"list": soup(page(cards(2)))}
        fatal, _ = ds.validate_selectors({"ITEM": "div.ml-item", "TITLE": "", "EPISODE": "", "SEARCH": "",
                                          "PAGE_STYLE": "none", "PLAYER": "iframe"}, fx, BASE)
        self.assertTrue(any("minimal 3" in m for m in fatal))

    def test_foreign_card_links_are_fatal(self):
        h = "".join(f'<div class="ml-item"><a href="https://lain.example/{i}"><img src="a"></a><h2>t{i}</h2></div>' for i in range(8))
        fx = {"list": soup(page(h))}
        d = ds.detect_from_fixtures(BASE, fx)
        self.assertTrue(any("separuh" in m for m in ds.validate_selectors(d, fx, BASE)[0]))


class MainFlowTest(unittest.TestCase):
    """main() pada repo tiruan: fixture dulu, lalu hasil Selectors.kt."""

    def setUp(self):
        self.saved = (ds.ROOT, ds.FIXTURES, ds.REPORT)
        self.root = Path(tempfile.mkdtemp())
        ds.ROOT, ds.FIXTURES, ds.REPORT = self.root, self.root / "tests/kotlin/fixtures", self.root / "report.md"

    def tearDown(self):
        ds.ROOT, ds.FIXTURES, ds.REPORT = self.saved

    def plugin(self, domains="AProvider: https://x.example\n", header="// @auto-detect | detected: default | score: 0"):
        (self.root / "domains.yml").write_text(domains, encoding="utf-8")
        d = self.root / "AProvider/src/main/kotlin/com/cloudstreamid/aprovider"
        d.mkdir(parents=True)
        (d / "Selectors.kt").write_text(f"{header}\npackage com.cloudstreamid.aprovider\nobject Sel {{ const val ITEM = \"\" }}\n")
        return d / "Selectors.kt"

    def fixtures(self, host="x.example", list_body=None):
        from fixture_helpers import write_fixtures
        write_fixtures(self.root, "AProvider", host)
        fx = self.root / "tests/kotlin/fixtures/AProvider"
        (fx / "list.html").write_text(page(list_body or cards(), f'<link rel="canonical" href="https://{host}/">'), encoding="utf-8")

    def test_missing_fixtures_fail_and_do_not_write(self):
        f = self.plugin()
        before = f.read_text()
        self.assertEqual(ds.main(), 1)
        self.assertEqual(f.read_text(), before)
        self.assertIn("DITOLAK", ds.REPORT.read_text())

    def test_fixtures_from_other_domain_fail(self):
        f = self.plugin()
        self.fixtures(host="lain.example")
        self.assertEqual(ds.main(), 1)
        self.assertIn("default", f.read_text().splitlines()[0])

    def test_generates_selectors_from_fixtures_and_is_idempotent(self):
        f = self.plugin()
        self.fixtures()
        self.assertEqual(ds.main(), 0)
        txt = f.read_text()
        self.assertIn('const val ITEM = "div.ml-item"', txt)
        self.assertIn("fixtures: ", txt.splitlines()[0])
        self.assertEqual(ds.main(), 0)                       # fixture sama -> dilewati
        self.assertEqual(f.read_text(), txt)

    def test_changed_fixture_regenerates(self):
        f = self.plugin()
        self.fixtures()
        ds.main()
        self.fixtures(list_body=cards(8, cls="kartu"))
        ds.main()
        self.assertIn('const val ITEM = "div.kartu"', f.read_text())

    def test_unusable_list_page_fails(self):
        f = self.plugin()
        self.fixtures(list_body="<p>tidak ada daftar</p>")
        self.assertEqual(ds.main(), 1)
        self.assertIn("default", f.read_text().splitlines()[0])

    def test_manual_lock_respected(self):
        f = self.plugin(header="// DIKUNCI MANUAL")
        self.fixtures()
        self.assertEqual(ds.main(), 0)
        self.assertTrue(f.read_text().startswith("// DIKUNCI MANUAL"))

    def test_disabled_entry_ignored(self):
        self.plugin(domains="#AProvider: https://x.example\nBProvider: https://b.example\n")
        self.assertEqual(ds.main(), 0)


class CardStructureRegressionTest(unittest.TestCase):
    """Struktur kartu berbeda-beda: deteksi mengandalkan DOM, bukan nama kelas tertentu."""

    def sel(self, html):
        r = ds.find_items(soup(html))
        self.assertIsNotNone(r)
        found = soup(html).select(r[0])
        self.assertEqual(len(found), len(r[1]))           # selector benar-benar cocok dengan kartu yang terdeteksi
        return r[0]

    def test_card_with_badge_images_and_varying_classes(self):
        h = "<div class='grid'>" + "".join(
            f"<div class='item {'hot' if i % 2 else 'new'}'><a href='/watch/f-{i}'><img src='p{i}.jpg'>"
            f"<img class='q' src='hd.png'></a><span>Film {i}</span></div>" for i in range(8)) + "</div>"
        self.assertEqual(self.sel(h), "div.item")

    def test_classless_list_items(self):
        h = "<ul>" + "".join(f"<li><a href='/t/s-{i}'><img src='p{i}.jpg'><h3>Seri {i}</h3></a></li>" for i in range(6)) + "</ul>"
        self.assertEqual(self.sel(h), "ul > li")

    def test_other_class_name_not_hardcoded(self):
        h = "".join(f"<section class='kotak'><a href='/f/{i}'><img src='a{i}'></a><h4>J{i}</h4></section>" for i in range(5))
        self.assertEqual(self.sel(f"<main>{h}</main>"), "section.kotak")

    def test_two_card_types_in_same_parent_picks_largest_and_matches_all(self):
        a = "".join(f"<article class='bs'><a href='/a/{i}'><img src='x'></a></article>" for i in range(6))
        b = "".join(f"<article class='bsz'><a href='/b/{i}'><img src='x'></a></article>" for i in range(4))
        self.assertEqual(self.sel(f"<div class='l'>{a}</div><div class='l'>{b}</div>"), "article.bs")

    def test_icon_lists_without_links_ignored(self):
        stars = "<ul>" + "<li><img src='star.png'></li>" * 6 + "</ul>"
        self.assertIsNone(ds.find_items(soup(stars)))

    def test_mhtml_quoted_printable_is_decoded(self):
        import quopri
        body = LIST_HTML.replace("Film", "Film é")
        qp = quopri.encodestring(body.encode("utf-8")).decode("ascii")
        raw = ('From: <Saved by Blink>\r\nSnapshot-Content-Location: https://x.example/\r\n'
               'Content-Type: multipart/related;\r\n\tboundary="----B----"\r\n\r\n'
               '------B----\r\nContent-Type: text/html\r\nContent-Transfer-Encoding: quoted-printable\r\n'
               f'Content-Location: https://x.example/\r\n\r\n{qp}\r\n------B------\r\n')
        out = ds.extract_html(raw)
        self.assertNotIn("=3D", out)
        self.assertEqual(ds.find_items(soup(out))[0], "div.ml-item")


def _mh(html, cte="", charset="utf-8", extra_parts="", nl="\r\n", bom=""):
    """MHTML tiruan: halaman utama + (opsional) bagian text/html lain lebih dulu."""
    enc = f"Content-Transfer-Encoding: {cte}{nl}" if cte else ""
    return (f'{bom}From: <Saved by Blink>{nl}Snapshot-Content-Location: https://x.example/{nl}'
            f'Content-Type: multipart/related;{nl}\tboundary="----B----"{nl}{nl}{extra_parts}'
            f'------B----{nl}Content-Type: text/html; charset={charset}{nl}{enc}Content-Location: https://x.example/{nl}{nl}'
            f'{html}{nl}------B------{nl}')


class StructureDetectionTest(unittest.TestCase):
    """Judul/deskripsi/episode/pemutar/daftar utama dikenali dari struktur, bukan daftar kelas tetap."""

    def test_main_list_beats_larger_sidebar_widget(self):
        main = "".join(f"<div class='kartu'><a href='/m/{i}'><img src='a'></a></div>" for i in range(6))
        side = "".join(f"<div class='kartu'><a href='/s/{i}'><img src='a'></a></div>" for i in range(12))
        for wrap in ("<aside>{}</aside>", "<div class='widget-box'>{}</div>", "<div id='sidebar'>{}</div>"):
            h = f"<div class='isi'>{main}</div>" + wrap.format(side)
            sel, cards = ds.find_items(soup(h))
            self.assertEqual({card_href for card_href in (ds.card_href(c) for c in cards)},
                             {f"/m/{i}" for i in range(6)})
            self.assertEqual(len(soup(h).select(sel)), 6, sel)      # selector tidak menyeret kartu sidebar

    def test_main_and_sidebar_under_same_parent_class_are_separated(self):
        a = "".join(f"<article class='k'><a href='/m/{i}'><img src='a'></a></article>" for i in range(5))
        b = "".join(f"<article class='k'><a href='/s/{i}'><img src='a'></a></article>" for i in range(9))
        sel, cards = ds.find_items(soup(f"<main><div class='l'>{a}</div></main><aside><div class='l'>{b}</div></aside>"))
        self.assertTrue(all(ds.card_href(c).startswith("/m/") for c in cards))

    def test_title_found_by_text_match_not_class_name(self):
        h = "<div class='g'>" + "".join(
            f"<div class='c'><a href='/f/{i}' title='Judul {i}'><img src='p' alt='Judul {i}'></a>"
            f"<div class='zq'>Judul {i}</div><div class='lbl'>HD</div></div>" for i in range(6)) + "</div>"
        sel, cards = ds.find_items(soup(h))
        self.assertEqual(ds.detect_title(cards), "div.zq")

    def test_title_inside_link_with_generic_tag(self):
        h = "<ul>" + "".join(f"<li><a href='/f/{i}'><img src='p'><span>Serial Hebat {i}</span><b>HD</b></a></li>"
                              for i in range(6)) + "</ul>"
        sel, cards = ds.find_items(soup(h))
        self.assertEqual(ds.detect_title(cards), "span")

    def test_description_by_meta_match_with_custom_class(self):
        para = "Sinopsis panjang tentang petualangan seorang pemuda yang mencari arti hidup di dunia asing. " * 2
        h = (f"<head><meta name='description' content='{para[:80]}'></head><body><div class='pj'><p>{para}</p></div>"
             f"<aside class='sidebar'><p>{'Teks sidebar yang sangat panjang sekali ' * 6}</p></aside></body>")
        d = soup(h)
        self.assertEqual(ds.detect_desc(d), "div.pj")
        self.assertEqual(d.select_one(ds.detect_desc(d)).name, "div")

    def test_description_ignores_short_text(self):
        self.assertEqual(ds.detect_desc(soup("<div class='x'>pendek</div>")), "")

    def test_episodes_without_episode_keyword(self):
        lis = "".join(f"<li><a href='/nonton/judul-{i}/'>{i}</a></li>" for i in (3, 2, 1, 4))
        pag = "<div class='pagination'><a href='/page/2/'>2</a><a href='/page/3/'>3</a></div>"
        sel, desc = ds.detect_episodes(soup(f"<ul class='chapter'>{lis}</ul>{pag}"), BASE + "/", min_count=1)
        self.assertEqual(sel, "ul.chapter li a")

    def test_numbered_links_in_sidebar_or_years_are_not_episodes(self):
        side = "<aside><ul>" + "".join(f"<li><a href='/x/s-{i}/'>Hot {i}</a></li>" for i in range(5)) + "</ul></aside>"
        years = "<ul class='thn'>" + "".join(f"<li><a href='/tahun/{y}/'>{y}</a></li>" for y in (2021, 2022, 2023)) + "</ul>"
        self.assertEqual(ds.detect_episodes(soup(side + years), BASE + "/", min_count=1), ("", True))

    def test_player_custom_data_attribute_when_no_known_one(self):
        h = ("<div class='vplay'>" + "".join(f"<button data-stream='https://v.example/embed/{i}'>S{i}</button>"
                                              for i in range(3)) + "</div><div data-article-url='https://x.example/a/'></div>")
        sel = ds.detect_player(soup(h), BASE)
        self.assertEqual(sel, "div.vplay button[data-stream]")

    def test_player_iframe_gets_container_context(self):
        h = "<iframe src='https://ads.example/x'></iframe><div class='player'><iframe src='https://v.example/e'></iframe></div>"
        self.assertEqual(ds.detect_player(soup(h), BASE), "div.player iframe")

    def test_extra_player_attr_is_rendered_into_kotlin(self):
        d = {"ITEM": "div.a", "TITLE": "", "SEARCH": "", "PAGE_STYLE": "none", "PAGE_PARAM": "page", "POSTER": "",
             "DESC": "", "GENRE": "", "EPISODE": "", "EPISODES_DESC": True, "USE_OG_IMAGE": True, "USE_OG_DESC": True,
             "PLAYER": "div.v button[data-stream]", "CATEGORIES": [], "_extra_attrs": ["data-stream"]}
        self.assertIn('"data-stream"', ds.render("aprovider", d, "2026-10-15"))


class MhtmlEncodingTest(unittest.TestCase):
    BODY = LIST_HTML.replace("Film", "Fílm é ü")

    def check(self, raw):
        out = ds.extract_html(raw)
        self.assertIn("Fílm é ü", out)
        self.assertEqual(ds.find_items(soup(out))[0], "div.ml-item")

    def test_quoted_printable_latin1(self):
        import quopri
        self.check(_mh(quopri.encodestring(self.BODY.encode("iso-8859-1")).decode("ascii"), "quoted-printable", "iso-8859-1"))

    def test_base64_utf8(self):
        enc = base64.encodebytes(self.BODY.encode("utf-8")).decode("ascii")
        self.check(_mh(enc, "base64"))

    def test_8bit_and_binary_untouched(self):
        for cte in ("8bit", "binary", ""):
            self.check(_mh(self.BODY, cte))

    def test_lf_only_line_endings_and_bom(self):
        import quopri
        qp = quopri.encodestring(self.BODY.encode("utf-8")).decode("ascii")
        self.check(_mh(qp, "quoted-printable", nl="\n", bom="\ufeff"))

    def test_uppercase_headers_unknown_charset_falls_back_to_utf8(self):
        import quopri
        qp = quopri.encodestring(self.BODY.encode("utf-8")).decode("ascii")
        raw = _mh(qp, "quoted-printable", "x-tidak-ada").replace("Content-Transfer-Encoding", "CONTENT-TRANSFER-ENCODING")
        self.check(raw)

    def test_main_frame_chosen_over_earlier_subframe(self):
        sub = ('------B----\r\nContent-Type: text/html\r\nContent-Location: https://ads.example/f\r\n\r\n'
               "<html><body><p>iklan</p></body></html>\r\n")
        out = ds.extract_html(_mh(self.BODY, extra_parts=sub))
        self.assertIn("ml-item", out)
        self.assertNotIn("iklan", out)


class HomepageWithTrendingTabsTest(unittest.TestCase):
    """Pola situs nyata (myflixer): daftar utama + tab trending berkelas kartu sama; menu bernama ul.nav."""

    def test_short_selector_kept_and_extra_cards_warned(self):
        def wrap(cls, pre, n):
            return f"<{pre} class='{cls}'><div class='block_area-content'><div class='film_list-wrap'>" + "".join(
                f"<div class='flw-item'><a href='/movie/{cls}-{i}/'><img src='a'></a><h3 class='film-name'>F{i}</h3></div>"
                for i in range(n)) + f"</div></div></{pre}>"
        menu = "<ul class='nav header_menu-list'><li class='nav-item'><a href='/movies/'>Movies</a></li></ul>"
        h = page(menu + wrap("block_area home", "section", 8) + wrap("tab-pane", "div", 5))
        fx = {"list": soup(h)}
        d = ds.detect_from_fixtures(BASE, fx)
        self.assertEqual(d["ITEM"], "div.flw-item")
        self.assertEqual(d["_item_extra"], 5)
        self.assertEqual(d["CATEGORIES"], [("/movies/", "Movies")])
        fatal, warn = ds.validate_selectors(d, fx, BASE)
        self.assertEqual(fatal, [])
        self.assertTrue(any("di luar daftar utama" in w for w in warn))


class LinklessCardsTest(unittest.TestCase):
    def test_cards_without_links_fail_with_clear_reason_not_guessed(self):
        h = "<div class='movies-grid'>" + "".join(
            f"<div class='movie-card'><img src='p{i}.jpg'><h3 class='movie-title'>Film {i}</h3></div>" for i in range(8)) + "</div>"
        self.assertIsNone(ds.find_items(soup(h)))
        with self.assertRaises(RuntimeError) as cm:
            ds.detect_from_fixtures(BASE, {"list": soup(page(h))})
        self.assertIn("TANPA tautan detail", str(cm.exception))
        self.assertIn("div.movie-card", str(cm.exception))


class AdBannerVsRealListTest(unittest.TestCase):
    def test_internal_list_beats_larger_external_ad_group(self):
        ads = "".join(f"<div class='mx-auto'><a href='https://dub.sh/x{i}'><img src='ad{i}.png'></a></div>" for i in range(12))
        real = "".join(f"<div class='kt'><a href='/anime/{i}/x'><img src='p{i}.jpg'></a><h3>Judul {i}</h3></div>" for i in range(6))
        h = soup(page(f"<div class='iklan'>{ads}</div><div class='daftar'>{real}</div>"))
        sel, cards = ds.find_items(h, BASE)
        self.assertEqual(sel, "div.kt")

    def test_only_ads_with_posters_is_rejected_by_validation(self):
        ads = "".join(f"<div class='mx-auto'><a href='https://dub.sh/x{i}'><img src='ad{i}.png'></a></div>" for i in range(12))
        text_list = "".join(f"<div class='col'><a href='/anime/{i}/x'>Judul {i}</a></div>" for i in range(20))
        fx = {"list": soup(page(ads + text_list))}
        d = ds.detect_from_fixtures(BASE, fx)
        self.assertTrue(any("separuh" in m for m in ds.validate_selectors(d, fx, BASE)[0]))


class FailureKeepsOldFileTest(MainFlowTest):
    def test_failed_validation_keeps_previous_selectors(self):
        f = self.plugin(header="// @auto-detect | detected: 2026-01-01 | score: 5 | fixtures: oldhash")
        before = f.read_text()
        self.fixtures(list_body="<p>tidak ada daftar</p>")
        self.assertEqual(ds.main(), 1)
        self.assertEqual(f.read_text(), before)
        self.assertFalse(list(f.parent.glob("*.tmp")))

    def test_mhtml_list_fixture_generates_matching_selector(self):
        from fixture_helpers import mhtml
        f = self.plugin()
        self.fixtures()
        fxp = self.root / "tests/kotlin/fixtures/AProvider/list.html"
        fxp.write_text(mhtml("x.example", cards(8, cls="kartu-x")), encoding="utf-8")
        self.assertEqual(ds.main(), 0)
        self.assertIn('const val ITEM = "div.kartu-x"', f.read_text())


class RealFixtureRegressionTest(unittest.TestCase):
    """Fixture asli di repo ini: hasil otomatis harus sama dengan selector yang dulu disetel manual."""

    def real(self, name, base):
        if not (REPO / "tests/kotlin/fixtures" / name / "list.html").exists():
            self.skipTest(f"fixture {name} tidak ada")
        fx = ds.load_fixtures(name)
        d = ds.detect_from_fixtures(base, fx, ds.list_fixture_path(name))
        return d, fx

    def test_animesail(self):
        d, fx = self.real("AnimeSailProvider", "https://anisail.com")
        self.assertEqual(d["ITEM"], "article.bs")
        self.assertEqual(d["EPISODE"], "ul.daftar li a")
        self.assertEqual(d["PLAYER"], "select.mirror option[data-em]")
        self.assertEqual(d["PAGE_STYLE"], "path")
        self.assertEqual(d["SEARCH"], "/?s={q}")
        self.assertEqual(ds.validate_selectors(d, fx, "https://anisail.com")[0], [])

    def test_sflix(self):
        d, fx = self.real("SflixProvider", "https://sflix.blue")
        self.assertEqual(d["ITEM"], "div.ml-item")
        self.assertEqual(d["SEARCH"], "")              # kotak pencarian tanpa <form>: tidak ditebak
        self.assertEqual(d["EPISODE"], "")             # situs film
        self.assertNotIn("/movies/", [p for p, _ in d["CATEGORIES"]])   # halaman daftar itu sendiri
        self.assertEqual(ds.validate_selectors(d, fx, "https://sflix.blue")[0], [])


if __name__ == "__main__":
    unittest.main()
