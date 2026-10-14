#!/usr/bin/env python3
"""Ringkas laporan JUnit XML (Gradle) jadi Markdown pendek untuk $GITHUB_STEP_SUMMARY.
Dibuat supaya hasil tes terbaca di layar HP tanpa membuka log panjang.
Pemakaian: summarize_junit.py <folder-xml>  (cetak ke stdout)"""
import sys
import glob
import xml.etree.ElementTree as ET


def summarize(folder):
    total = failed = skipped = 0
    problems, skips = [], []
    for path in sorted(glob.glob(f"{folder}/**/TEST-*.xml", recursive=True)):
        for case in ET.parse(path).getroot().iter("testcase"):
            total += 1
            name = f"{case.get('classname', '').split('.')[-1]} > {case.get('name', '')}"
            bad = case.find("failure")
            if bad is None:
                bad = case.find("error")
            if bad is not None:
                failed += 1
                msg = (bad.get("message") or (bad.text or "")).strip().splitlines()
                problems.append((name, msg[0][:300] if msg else ""))
            elif case.find("skipped") is not None:
                skipped += 1
                skips.append(name)
    lines = ["## Hasil tes parser", "",
             f"Total {total} | lulus {total - failed - skipped} | gagal {failed} | dilewati {skipped}", ""]
    if problems:
        lines.append("### Gagal")
        lines += [f"- **{n}**: {m}" for n, m in problems]
        lines.append("")
    if skips:
        lines.append("### Dilewati (biasanya fixture belum ada)")
        lines += [f"- {n}" for n in skips]
    if total == 0:
        lines.append("Tidak ada laporan tes ditemukan (kemungkinan kompilasi gagal; lihat log langkah Gradle).")
    return "\n".join(lines) + "\n", failed


if __name__ == "__main__":
    text, _ = summarize(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(text)
