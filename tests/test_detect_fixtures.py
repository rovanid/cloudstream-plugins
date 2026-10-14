import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import detect_selectors as ds  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

CARDS = "".join(
    f'<div class="ml-item"><a href="/movie/film-{i}/" title="Film {i}"><img src="x{i}.jpg" alt="Film {i}"></a>'
    f'<h2>Film {i}</h2></div>' for i in range(8))
LIST_HTML = f"<html><body><div class='wrap'>{CARDS}</div></body></html>"
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

    def test_detect_from_fixtures_offline(self):
        soup = BeautifulSoup(ds.extract_html(MHTML), "html.parser")
        with mock.patch.object(ds, "fetch", return_value=None):
            d = ds.detect_from_fixtures("https://x.example", {"list": soup})
        self.assertEqual(d["ITEM"], "div.ml-item")
        self.assertEqual(d["TITLE"], "h2")
        self.assertEqual(d["PAGE_STYLE"], "none")
        self.assertEqual(d["_source"], "fixture")

    def test_not_a_list_page_raises(self):
        soup = BeautifulSoup("<html><body><p>kosong</p></body></html>", "html.parser")
        with self.assertRaises(RuntimeError):
            ds.detect_from_fixtures("https://x.example", {"list": soup})

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


if __name__ == "__main__":
    unittest.main()
