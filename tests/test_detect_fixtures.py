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

    def test_foreign_card_links_warn(self):
        h = "".join(f'<div class="ml-item"><a href="https://lain.example/{i}"><img src="a"></a><h2>t{i}</h2></div>' for i in range(8))
        fx = {"list": soup(page(h))}
        d = ds.detect_from_fixtures(BASE, fx)
        self.assertTrue(any("lain" in w or "separuh" in w for w in ds.validate_selectors(d, fx, BASE)[1]))


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
