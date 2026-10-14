#!/usr/bin/env python3
"""
Terapkan domains.yml ke source Kotlin tiap provider (mainUrl).
`version` TIDAK dinaikkan di sini: itu tugas bump_versions.py (dijalankan sesudahnya), yang
mendeteksi perubahan mainUrl sekaligus perubahan kode lain dan menaikkan versi tepat sekali.

Format domains.yml:
    NamaFolder: https://domain-baru.tld

Aman dijalankan berulang (idempotent): kalau mainUrl sudah sama, tidak ada file yang diubah.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAINS = ROOT / "domains.yml"

# override var mainUrl = "https://..."  /  override var mainUrl: String = "..."
MAINURL_RE = re.compile(r'(\bmainUrl\s*(?::\s*String\s*)?=\s*")([^"]+)(")')


def read_flat(path: Path) -> dict:
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def valid_url(url: str) -> bool:
    return bool(re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d+)?", url))


def apply_to_folder(folder: Path, url: str) -> bool:
    """Ubah mainUrl di file Kotlin yang berisi MainAPI. True kalau ada perubahan."""
    changed = False
    for kt in folder.rglob("*.kt"):
        src = kt.read_text(encoding="utf-8")
        if "override var mainUrl" not in src:      # lewati extractor/helper/Selectors
            continue
        m = MAINURL_RE.search(src)
        if not m or m.group(2).rstrip("/") == url:
            continue
        new = src[:m.start(2)] + url + src[m.end(2):]
        kt.write_text(new, encoding="utf-8")
        print(f"  {kt.relative_to(ROOT)}: {m.group(2)} -> {url}")
        changed = True
    return changed


def main() -> int:
    if not DOMAINS.exists():
        print("domains.yml tidak ditemukan", file=sys.stderr)
        return 1

    for name, url in read_flat(DOMAINS).items():
        url = url.rstrip("/")
        folder = ROOT / name
        if not folder.is_dir():
            print(f"[SKIP] {name}: folder tidak ada")
            continue
        if not valid_url(url):
            print(f"[SKIP] {name}: URL tidak valid ({url!r})")
            continue
        if apply_to_folder(folder, url):
            print(f"[UBAH] {name}")
        else:
            print(f"[SAMA] {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
