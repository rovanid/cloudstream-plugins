import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github" / "scripts"))
import check_domains as cd  # noqa: E402
import registry  # noqa: E402


def E(name, url):
    return registry.Entry(name, url, 1)


def fake(table):
    """table: url -> (status, final_url, body) | None"""
    def f(url):
        return table.get(url)
    return f


class KeywordTest(unittest.TestCase):
    def test_default_uses_name_and_host_label(self):
        self.assertEqual(cd.keywords_for("FooProvider", "https://tv1.bar-x.cc", {}), ["bar-x"])

    def test_table_overrides(self):
        self.assertEqual(cd.keywords_for("FooProvider", "https://a.com", {"FooProvider": ["zzzz"]}), ["zzzz"])

    def test_repo_keywords_file_covers_real_sources(self):
        t = cd.read_keywords()
        self.assertIn("anisail", t["AnimeSailProvider"])
        self.assertIn("lk21", t["LayarKaca21Provider"])


    def test_short_keywords_dropped_and_unverified(self):
        self.assertEqual(cd.keywords_for("AProvider", "https://a.com", {}), [])
        r = cd.evaluate([E("AProvider", "https://a.com")], {}, fetch=fake({}))[0]
        self.assertEqual(r["verdict"], "UNVERIFIED")
        self.assertIsNone(r["proposed"])


class JudgeTest(unittest.TestCase):
    def test_verdicts(self):
        self.assertEqual(cd.judge((200, "u", "Selamat datang di AniSail"), ["anisail"]), "OK")
        self.assertEqual(cd.judge((200, "u", "domain dijual"), ["anisail"]), "PARKED")
        self.assertEqual(cd.judge((403, "u", ""), ["x"]), "BLOCKED")
        self.assertEqual(cd.judge((404, "u", ""), ["x"]), "DEAD")
        self.assertEqual(cd.judge(None, ["x"]), "DEAD")


class RetryTest(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls = []

        def f(url):
            calls.append(1)
            return None if len(calls) < 3 else (200, url, "ok")
        res = cd.probe_retry("https://a.com", fetch=f, sleep=lambda s: None)
        self.assertEqual(res[0], 200)
        self.assertEqual(len(calls), 3)

    def test_block_not_retried(self):
        calls = []

        def f(url):
            calls.append(1)
            return (403, url, "")
        cd.probe_retry("https://a.com", fetch=f, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)


class EvaluateTest(unittest.TestCase):
    def test_same_domain_is_not_a_proposal(self):
        r = cd.evaluate([E("AlphaSiteProvider", "https://a.com")], {},
                        fetch=fake({"https://a.com": (200, "https://a.com/", "Welcome to AlphaSite")}))[0]
        self.assertEqual(r["verdict"], "OK")
        self.assertIsNone(r["proposed"])

    def test_verified_redirect_is_proposed(self):
        t = {"https://a.com": (200, "https://new.a.io/home", "Welcome to AlphaSite"),
             "https://new.a.io": (200, "https://new.a.io/", "Welcome to AlphaSite")}
        r = cd.evaluate([E("AlphaSiteProvider", "https://a.com")], {}, fetch=fake(t))[0]
        self.assertEqual(r["verdict"], "MOVED")
        self.assertEqual(r["proposed"], "https://new.a.io")

    def test_redirect_to_parked_host_rejected(self):
        t = {"https://a.com": (200, "https://evil.xyz/a", "Welcome to AlphaSite"),
             "https://evil.xyz": (200, "https://evil.xyz/", "buy this domain")}
        r = cd.evaluate([E("AlphaSiteProvider", "https://a.com")], {}, fetch=fake(t))[0]
        self.assertIsNone(r["proposed"])
        self.assertIn("kata kunci", r["reason"])

    def test_redirect_to_unreachable_origin_rejected(self):
        t = {"https://a.com": (200, "https://new.a.io/", "Welcome to AlphaSite")}
        r = cd.evaluate([E("AlphaSiteProvider", "https://a.com")], {}, fetch=fake(t))[0]
        self.assertIsNone(r["proposed"])

    def test_redirect_to_http_or_taken_host_rejected(self):
        t = {"https://a.com": (200, "http://new.a.io/", "Welcome to AlphaSite")}
        self.assertIsNone(cd.evaluate([E("AlphaSiteProvider", "https://a.com")], {}, fetch=fake(t))[0]["proposed"])
        t = {"https://a.com": (200, "https://b.com/", "Welcome to AlphaSite"), "https://b.com": (200, "https://b.com/", "Welcome to AlphaSite")}
        r = cd.evaluate([E("AlphaSiteProvider", "https://a.com"), E("BetaSiteProvider", "https://b.com")],
                        {"BetaSiteProvider": ["bonly"]}, fetch=fake({**t, "https://b.com": (200, "https://b.com/", "bonly")}))
        self.assertIsNone(r[0]["proposed"])
        self.assertIn("dipakai plugin lain", r[0]["reason"])

    def test_blocked_dead_parked_never_change(self):
        t = {"https://a.com": (403, "https://a.com", ""), "https://c.com": None,
             "https://p.com": (200, "https://p.com", "for sale")}
        rs = cd.evaluate([E("AlphaSiteProvider", "https://a.com"), E("GammaSiteProvider", "https://c.com"),
                          E("ParkSiteProvider", "https://p.com")], {}, fetch=fake(t))
        self.assertEqual([r["verdict"] for r in rs], ["BLOCKED", "DEAD", "PARKED"])
        self.assertTrue(all(r["proposed"] is None for r in rs))


class ApplyTest(unittest.TestCase):
    def test_only_url_replaced_comments_and_spacing_kept(self):
        text = "# c\nAlphaSiteProvider : https://a.com # catatan\nBetaSiteProvider: https://b.com\n"
        out = cd.apply_proposals(text, [{"name": "AlphaSiteProvider", "current": "https://a.com", "proposed": "https://n.io"}])
        self.assertEqual(out, "# c\nAlphaSiteProvider : https://n.io # catatan\nBetaSiteProvider: https://b.com\n")

    def test_result_passes_registry_validation(self):
        import tempfile
        root = Path(tempfile.mkdtemp())
        (root / "domains.yml").write_text(cd.apply_proposals(
            "AlphaSiteProvider: https://a.com\n", [{"name": "AlphaSiteProvider", "current": "https://a.com", "proposed": "https://n.io"}]))
        self.assertTrue(registry.validate(root).ok)


if __name__ == "__main__":
    unittest.main()
