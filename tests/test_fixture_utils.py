import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_utils as fu  # noqa: E402
from fixture_helpers import html, mhtml, write_fixtures  # noqa: E402


def root_with(name="AProvider", host="a.com", **kw) -> Path:
    r = Path(tempfile.mkdtemp())
    write_fixtures(r, name, host, **kw)
    return r


class ProblemsTest(unittest.TestCase):
    def test_complete_matching_fixtures_pass(self):
        self.assertEqual(fu.problems(root_with(), "AProvider", "https://a.com"), [])

    def test_mhtml_fixtures_pass(self):
        self.assertEqual(fu.problems(root_with(mhtml_format=True), "AProvider", "https://a.com"), [])

    def test_missing_folder_reports_all_three(self):
        p = fu.problems(Path(tempfile.mkdtemp()), "AProvider", "https://a.com")
        self.assertEqual(len(p), 3)
        self.assertTrue(all("belum ada" in m for m in p))

    def test_missing_single_file(self):
        r = root_with(kinds=("list", "detail"))
        p = fu.problems(r, "AProvider", "https://a.com")
        self.assertEqual(len(p), 1)
        self.assertIn("episode.html belum ada", p[0])

    def test_placeholder_rejected(self):
        r = root_with()
        (r / "tests/kotlin/fixtures/AProvider/list.html").write_text("<html></html>")
        (r / "tests/kotlin/fixtures/AProvider/detail.html").write_text("")
        (r / "tests/kotlin/fixtures/AProvider/episode.html").write_text("x" * 5000)   # besar tapi bukan HTML
        p = fu.problems(r, "AProvider", "https://a.com")
        self.assertEqual(len(p), 3)
        self.assertTrue(all("bukan HTML" in m for m in p))

    def test_other_host_rejected_html_and_mhtml(self):
        for fmt in (False, True):
            p = fu.problems(root_with(host="other.com", mhtml_format=fmt), "AProvider", "https://a.com")
            self.assertEqual(len(p), 3, p)
            self.assertIn("other.com, bukan a.com", p[0])

    def test_www_prefix_ignored(self):
        self.assertEqual(fu.problems(root_with(host="www.a.com"), "AProvider", "https://a.com"), [])
        self.assertEqual(fu.problems(root_with(host="a.com"), "AProvider", "https://www.a.com"), [])

    def test_subdomain_is_a_different_domain(self):
        self.assertTrue(fu.problems(root_with(host="tv12.a.com"), "AProvider", "https://tv13.a.com"))

    def test_without_evidence_host_must_appear_in_body(self):
        r = root_with()
        body = "<!DOCTYPE html><html><body>" + "x" * 1500
        for k in fu.KINDS:
            (r / f"tests/kotlin/fixtures/AProvider/{k}.html").write_text(body + "</body></html>")
        self.assertEqual(len(fu.problems(r, "AProvider", "https://a.com")), 3)
        for k in fu.KINDS:
            (r / f"tests/kotlin/fixtures/AProvider/{k}.html").write_text(body + ' <a href="https://a.com/z">z</a></body></html>')
        self.assertEqual(fu.problems(r, "AProvider", "https://a.com"), [])

    def test_check_host_can_be_disabled(self):
        self.assertEqual(fu.problems(root_with(host="other.com"), "AProvider", "https://a.com", check_host=False), [])

    def test_extract_html_and_source_url(self):
        raw = mhtml("a.com", "<p id=z>")
        self.assertIn('id=z', fu.extract_html(raw))
        self.assertEqual(fu.source_url(raw), "https://a.com/halaman/")
        self.assertEqual(fu.source_url(html("a.com")), "")


if __name__ == "__main__":
    unittest.main()
