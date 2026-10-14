import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".github", "scripts"))
import summarize_junit as sj  # noqa: E402

XML = """<testsuite><testcase classname="a.B" name="ok"/>
<testcase classname="a.B" name="bad"><failure message="ITEM kosong
baris2">x</failure></testcase>
<testcase classname="a.B" name="skip"><skipped/></testcase></testsuite>"""


class T(unittest.TestCase):
    def test_summary(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "TEST-a.B.xml"), "w").write(XML)
            text, failed = sj.summarize(d)
        self.assertEqual(failed, 1)
        self.assertIn("Total 3 | lulus 1 | gagal 1 | dilewati 1", text)
        self.assertIn("B > bad", text)
        self.assertIn("ITEM kosong", text)

    def test_empty(self):
        with tempfile.TemporaryDirectory() as d:
            text, failed = sj.summarize(d)
        self.assertEqual(failed, 0)
        self.assertIn("kompilasi gagal", text)


if __name__ == "__main__":
    unittest.main()
