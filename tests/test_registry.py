import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import registry  # noqa: E402


def make(domains: str, types: str = "", folders=()) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "domains.yml").write_text(domains, encoding="utf-8")
    if types:
        (root / "plugin_types.yml").write_text(types, encoding="utf-8")
    for f in folders:
        (root / f / "src").mkdir(parents=True)
        (root / f / "build.gradle.kts").write_text("version = 1\n")
    return root


class RegistryTest(unittest.TestCase):
    def test_valid_with_spacing_and_comments(self):
        r = registry.validate(make("# c\nAProvider: https://a.com\nBProvider : https://b.com # x\n#CProvider: https://c.com\n"))
        self.assertTrue(r.ok, r.errors)
        self.assertEqual([e.name for e in r.entries if e.active], ["AProvider", "BProvider"])
        self.assertEqual([e.name for e in r.entries if not e.active], ["CProvider"])

    def test_duplicate_name(self):
        r = registry.validate(make("AProvider: https://a.com\nAProvider: https://b.com\n"))
        self.assertFalse(r.ok)
        self.assertTrue(any("ganda" in m for m in r.errors))

    def test_duplicate_host(self):
        r = registry.validate(make("AProvider: https://x.com\nBProvider: https://x.com/\n"))
        self.assertTrue(any("host x.com" in m for m in r.errors))

    def test_case_collision(self):
        r = registry.validate(make("FooProvider: https://a.com\nfooProvider: https://b.com\n"))
        self.assertTrue(any("bentrok" in m for m in r.errors))

    def test_invalid_url_and_name(self):
        r = registry.validate(make("Foo: https://a.com\nBarProvider: ftp://b.com\nBazProvider: https://c.com/path\nQuxProvider: https://q.com/\"x\n"))
        self.assertEqual(len(r.errors), 4)

    def test_line_without_any_colon(self):
        r = registry.validate(make("AProvider\nBProvider: https://b.com\n"))
        self.assertFalse(r.ok)
        self.assertTrue(any("tidak ada ':'" in m for m in r.errors))

    def test_missing_separator_before_url_is_blocked(self):
        # "https:" menyediakan ':' sehingga nama terbaca "AProvider https" -> harus tetap ditolak
        r = registry.validate(make("AProvider https://a.com\nBProvider: https://b.com\n"))
        self.assertFalse(r.ok)
        self.assertTrue(any("nama 'AProvider https'" in m for m in r.errors))

    def test_http_warns_not_errors(self):
        r = registry.validate(make("AProvider: http://a.com\n"))
        self.assertTrue(r.ok)
        self.assertTrue(any("http" in m for m in r.warnings))

    def test_empty_registry_is_error(self):
        self.assertFalse(registry.validate(make("# kosong\n")).ok)

    def test_bad_plugin_type(self):
        r = registry.validate(make("AProvider: https://a.com\n", types="AProvider: tv\n"))
        self.assertTrue(any("jenis" in m for m in r.errors))

    def test_warns_folder_that_sync_would_delete(self):
        # barisnya sudah tidak ada di domains.yml -> sync_plugins akan menghapus foldernya
        r = registry.validate(make("AProvider: https://a.com\n", folders=["AProvider", "BProvider"]))
        self.assertTrue(r.ok)
        self.assertTrue(any("BProvider" in m and "MENGHAPUS" in m for m in r.warnings))

    def test_disabled_folder_is_not_warned(self):
        # di-# = DISABLED: folder dipertahankan, jadi tidak ada peringatan penghapusan
        r = registry.validate(make("AProvider: https://a.com\n#BProvider: https://b.com\n", folders=["AProvider", "BProvider"]))
        self.assertTrue(r.ok)
        self.assertFalse(any("BProvider" in m and "MENGHAPUS" in m for m in r.warnings))

    def test_missing_file(self):
        self.assertFalse(registry.validate(Path(tempfile.mkdtemp())).ok)


if __name__ == "__main__":
    unittest.main()
