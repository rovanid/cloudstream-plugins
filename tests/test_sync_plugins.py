import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_plugins  # noqa: E402
import registry  # noqa: E402
from fixture_helpers import write_fixtures  # noqa: E402


def make(domains: str, folders) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "domains.yml").write_text(domains, encoding="utf-8")
    for f in folders:
        (root / f / "src").mkdir(parents=True)
        (root / f / "build.gradle.kts").write_text("version = 1\n")
        (root / f / "src" / "Keep.kt").write_text("tuning manual\n")
    return root


class DisabledTest(unittest.TestCase):
    def setUp(self):
        self._old = sync_plugins.ROOT

    def tearDown(self):
        sync_plugins.ROOT = self._old

    def test_commented_entry_keeps_folder(self):
        r = make("AProvider: https://a.com\n#BProvider: https://b.com\n", ["AProvider", "BProvider"])
        sync_plugins.ROOT = r
        sync_plugins.prune(sync_plugins.read_flat(r / "domains.yml"), frozenset(sync_plugins.read_disabled(r / "domains.yml")))
        self.assertTrue((r / "BProvider" / "src" / "Keep.kt").exists())

    def test_deleted_line_removes_folder(self):
        r = make("AProvider: https://a.com\n", ["AProvider", "BProvider"])
        sync_plugins.ROOT = r
        sync_plugins.prune(sync_plugins.read_flat(r / "domains.yml"), frozenset(sync_plugins.read_disabled(r / "domains.yml")))
        self.assertFalse((r / "BProvider").exists())
        self.assertTrue((r / "AProvider").exists())

    def test_read_disabled_ignores_prose_comments(self):
        r = make("# Format:  NamaFolder: https://domain\n#TAMBAH : tulis baris\n#XProvider: https://x.com\nAProvider: https://a.com\n", [])
        self.assertEqual(sync_plugins.read_disabled(r / "domains.yml"), {"XProvider"})

    def test_main_does_not_scaffold_disabled(self):
        r = make("AProvider: https://a.com\n#BProvider: https://b.com\n", ["AProvider"])
        sync_plugins.ROOT = r
        sync_plugins.main()
        self.assertFalse((r / "BProvider").exists())

    def test_registry_does_not_warn_deletion_for_disabled_folder(self):
        r = make("AProvider: https://a.com\n#BProvider: https://b.com\n", ["AProvider", "BProvider"])
        rep = registry.validate(r, require_fixtures=False)
        self.assertTrue(rep.ok, rep.errors)
        self.assertFalse(any("BProvider" in w and "MENGHAPUS" in w for w in rep.warnings), rep.warnings)

    def test_registry_still_warns_for_orphan_folder(self):
        r = make("AProvider: https://a.com\n", ["AProvider", "ZProvider"])
        rep = registry.validate(r, require_fixtures=False)
        self.assertTrue(any("ZProvider" in w and "MENGHAPUS" in w for w in rep.warnings), rep.warnings)


class FixtureGateTest(unittest.TestCase):
    def setUp(self):
        self._old = sync_plugins.ROOT
        self._tpl = sync_plugins.TEMPLATES

    def tearDown(self):
        sync_plugins.ROOT = self._old
        sync_plugins.TEMPLATES = self._tpl

    def _root(self, with_fixtures: bool) -> Path:
        r = make("NewProvider: https://new.example\n", [])
        tpl = r / ".github" / "templates" / "anime"
        (tpl / "src").mkdir(parents=True)
        (tpl / "build.gradle.kts").write_text("version = 1\n")
        (tpl / "src" / "__NAME__.kt").write_text("x\n")
        if with_fixtures:
            write_fixtures(r, "NewProvider", "new.example")
        sync_plugins.ROOT = r
        sync_plugins.TEMPLATES = r / ".github" / "templates"
        return r

    def test_new_plugin_without_fixtures_is_not_created(self):
        r = self._root(False)
        self.assertEqual(sync_plugins.main(), 1)
        self.assertFalse((r / "NewProvider").exists())

    def test_new_plugin_with_fixtures_is_created(self):
        r = self._root(True)
        self.assertEqual(sync_plugins.main(), 0)
        self.assertTrue((r / "NewProvider" / "build.gradle.kts").exists())


if __name__ == "__main__":
    unittest.main()
