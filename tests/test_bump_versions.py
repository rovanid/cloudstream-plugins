import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import bump_versions  # noqa: E402


def make_repo(domains="AProvider: https://a.com\nBProvider: https://b.com\n", names=("AProvider", "BProvider")) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "domains.yml").write_text(domains, encoding="utf-8")
    (root / "shared" / "kotlin").mkdir(parents=True)
    (root / "shared" / "kotlin" / "Engine.kt").write_text("// engine v1\n", encoding="utf-8")
    for n in names:
        d = root / n
        (d / "src" / "main").mkdir(parents=True)
        (d / "build.gradle.kts").write_text("// c\nversion = 5\n\ncloudstream { status = 1 }\n", encoding="utf-8")
        (d / "src" / "main" / f"{n}.kt").write_text('override var mainUrl = "https://x.com"\n', encoding="utf-8")
        (d / "src" / "main" / "Selectors.kt").write_text(
            "// @auto-detect | detected: 2026-10-01 | score: 5\nobject Sel { const val ITEM = \"a\" }\n", encoding="utf-8")
    return root


def version(root: Path, name: str) -> int:
    for line in (root / name / "build.gradle.kts").read_text().splitlines():
        if line.startswith("version"):
            return int(line.split("=")[1])
    raise AssertionError("no version")


def actions(results) -> dict:
    return {n: a for n, a, _, _ in results}


class BumpTest(unittest.TestCase):
    def test_first_run_is_baseline_without_bump(self):
        r = make_repo()
        self.assertEqual(set(actions(bump_versions.run(r)).values()), {"BASELINE"})
        self.assertEqual(version(r, "AProvider"), 5)
        self.assertTrue((r / "plugin_hashes.json").exists())

    def test_second_run_without_change_is_noop(self):
        r = make_repo()
        bump_versions.run(r)
        before = (r / "plugin_hashes.json").read_text()
        self.assertEqual(set(actions(bump_versions.run(r)).values()), {"SAMA"})
        self.assertEqual(version(r, "AProvider"), 5)
        self.assertEqual((r / "plugin_hashes.json").read_text(), before)

    def test_shared_change_bumps_all_active_plugins_once(self):
        r = make_repo()
        bump_versions.run(r)
        (r / "shared" / "kotlin" / "Engine.kt").write_text("// engine v2\n", encoding="utf-8")
        self.assertEqual(set(actions(bump_versions.run(r)).values()), {"NAIK"})
        self.assertEqual((version(r, "AProvider"), version(r, "BProvider")), (6, 6))
        # idempotent: bump sendiri tidak mengubah hash, jadi tidak naik dua kali
        self.assertEqual(set(actions(bump_versions.run(r)).values()), {"SAMA"})
        self.assertEqual(version(r, "AProvider"), 6)

    def test_plugin_change_bumps_only_that_plugin(self):
        r = make_repo()
        bump_versions.run(r)
        (r / "AProvider" / "src" / "main" / "AProvider.kt").write_text('override var mainUrl = "https://new.com"\n')
        a = actions(bump_versions.run(r))
        self.assertEqual((a["AProvider"], a["BProvider"]), ("NAIK", "SAMA"))
        self.assertEqual((version(r, "AProvider"), version(r, "BProvider")), (6, 5))

    def test_gradle_metadata_change_bumps_but_version_line_alone_does_not(self):
        r = make_repo()
        bump_versions.run(r)
        g = r / "AProvider" / "build.gradle.kts"
        g.write_text(g.read_text().replace("version = 5", "version = 9"))   # hanya baris version
        self.assertEqual(actions(bump_versions.run(r))["AProvider"], "SAMA")
        g.write_text(g.read_text().replace("status = 1", "status = 2"))     # metadata sungguhan
        self.assertEqual(actions(bump_versions.run(r))["AProvider"], "NAIK")
        self.assertEqual(version(r, "AProvider"), 10)

    def test_autodetect_date_only_change_does_not_bump(self):
        r = make_repo()
        bump_versions.run(r)
        s = r / "AProvider" / "src" / "main" / "Selectors.kt"
        s.write_text(s.read_text().replace("2026-10-01", "2026-10-14"))
        self.assertEqual(actions(bump_versions.run(r))["AProvider"], "SAMA")
        s.write_text(s.read_text().replace('"a"', '"b"'))                    # selector berubah
        self.assertEqual(actions(bump_versions.run(r))["AProvider"], "NAIK")

    def test_crlf_is_not_a_change(self):
        r = make_repo()
        bump_versions.run(r)
        e = r / "shared" / "kotlin" / "Engine.kt"
        e.write_bytes(e.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(set(actions(bump_versions.run(r)).values()), {"SAMA"})

    def test_build_dir_is_ignored(self):
        r = make_repo()
        bump_versions.run(r)
        (r / "AProvider" / "build").mkdir()
        (r / "AProvider" / "build" / "out.class").write_text("x")
        self.assertEqual(actions(bump_versions.run(r))["AProvider"], "SAMA")

    def test_disabled_plugin_is_skipped_and_bumps_when_reenabled(self):
        r = make_repo("AProvider: https://a.com\n#BProvider: https://b.com\n")
        bump_versions.run(r)
        self.assertNotIn("BProvider", json.loads((r / "plugin_hashes.json").read_text()))
        # aktifkan B -> baseline; nonaktifkan lagi, ubah shared, aktifkan -> naik
        (r / "domains.yml").write_text("AProvider: https://a.com\nBProvider: https://b.com\n")
        bump_versions.run(r)
        (r / "domains.yml").write_text("AProvider: https://a.com\n#BProvider: https://b.com\n")
        (r / "shared" / "kotlin" / "Engine.kt").write_text("// engine v3\n")
        a = actions(bump_versions.run(r))
        self.assertNotIn("BProvider", a)
        self.assertEqual(version(r, "BProvider"), 5)           # nonaktif: tidak disentuh
        (r / "domains.yml").write_text("AProvider: https://a.com\nBProvider: https://b.com\n")
        self.assertEqual(actions(bump_versions.run(r))["BProvider"], "NAIK")
        self.assertEqual(version(r, "BProvider"), 6)

    def test_dry_run_writes_nothing(self):
        r = make_repo()
        bump_versions.run(r)
        (r / "shared" / "kotlin" / "Engine.kt").write_text("// engine v2\n")
        before = (r / "plugin_hashes.json").read_text()
        self.assertEqual(set(actions(bump_versions.run(r, dry_run=True)).values()), {"NAIK"})
        self.assertEqual(version(r, "AProvider"), 5)
        self.assertEqual((r / "plugin_hashes.json").read_text(), before)

    def test_removed_folder_is_dropped_from_state(self):
        r = make_repo()
        bump_versions.run(r)
        import shutil
        shutil.rmtree(r / "BProvider")
        (r / "domains.yml").write_text("AProvider: https://a.com\n")
        bump_versions.run(r)
        self.assertEqual(list(json.loads((r / "plugin_hashes.json").read_text())), ["AProvider"])

    def test_corrupt_state_is_rebaselined(self):
        r = make_repo()
        (r / "plugin_hashes.json").write_text("{not json")
        self.assertEqual(set(actions(bump_versions.run(r)).values()), {"BASELINE"})
        self.assertEqual(version(r, "AProvider"), 5)


def add_standalone(root: Path, name: str = "MyHomepage") -> Path:
    d = root / name
    (d / "src" / "main").mkdir(parents=True)
    (d / "build.gradle.kts").write_text("version = 1\n\ncloudstream { status = 3 }\n", encoding="utf-8")
    (d / "src" / "main" / "Home.kt").write_text("class Home\n", encoding="utf-8")
    return d


class StandalonePluginTest(unittest.TestCase):
    """Plugin mandiri (mis. MyHomepage): bukan *Provider, tidak ada di domains.yml, tanpa shared/kotlin."""

    def test_standalone_is_baselined_then_stable(self):
        r = make_repo()
        add_standalone(r)
        self.assertEqual(actions(bump_versions.run(r))["MyHomepage"], "BASELINE")
        self.assertEqual(actions(bump_versions.run(r))["MyHomepage"], "SAMA")
        self.assertEqual(version(r, "MyHomepage"), 1)

    def test_standalone_bumps_when_own_code_changes(self):
        r = make_repo()
        d = add_standalone(r)
        bump_versions.run(r)
        (d / "src" / "main" / "Home.kt").write_text("class Home2\n", encoding="utf-8")
        a = actions(bump_versions.run(r))
        self.assertEqual(a["MyHomepage"], "NAIK")
        self.assertEqual(a["AProvider"], "SAMA")
        self.assertEqual(version(r, "MyHomepage"), 2)
        self.assertEqual(actions(bump_versions.run(r))["MyHomepage"], "SAMA")   # tidak naik dua kali

    def test_shared_change_does_not_bump_standalone(self):
        r = make_repo()
        add_standalone(r)
        bump_versions.run(r)
        (r / "shared" / "kotlin" / "Engine.kt").write_text("// engine v2\n", encoding="utf-8")
        a = actions(bump_versions.run(r))
        self.assertEqual(a["MyHomepage"], "SAMA")
        self.assertEqual(a["AProvider"], "NAIK")
        self.assertEqual(version(r, "MyHomepage"), 1)

    def test_read_standalone_ignores_non_plugin_dirs(self):
        r = make_repo()
        add_standalone(r)
        (r / "docs").mkdir()                                    # tanpa build.gradle.kts
        (r / "tests" / "kotlin").mkdir(parents=True)
        (r / "tests" / "kotlin" / "build.gradle.kts").write_text("x\n")   # bukan tingkat atas
        (r / ".github").mkdir()
        self.assertEqual(bump_versions.read_standalone(r), ["MyHomepage"])


if __name__ == "__main__":
    unittest.main()
