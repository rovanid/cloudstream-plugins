#!/usr/bin/env python3
"""
Buat folder plugin baru otomatis untuk setiap entri di domains.yml yang
foldernya belum ada. Jenis template dari plugin_types.yml (anime | movie).
Dijalankan SEBELUM apply_domains.py.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / ".github" / "templates"
NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*Provider")
URL_RE = re.compile(r"https?://[A-Za-z0-9.-]+(:\d+)?")


def read_flat(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def scaffold(folder_name: str, url: str, kind: str) -> None:
    base = folder_name[: -len("Provider")]      # "FooBarProvider" -> "FooBar"
    pkg = folder_name.lower()
    repl = {"__NAME__": base, "__PKG__": pkg, "__URL__": url}
    src = TEMPLATES / kind
    dst = ROOT / folder_name
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        parts = []
        for p in rel.parts:
            for k, v in repl.items():
                p = p.replace(k, v)
            parts.append(p)
        target = dst.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = f.read_text(encoding="utf-8")
        for k, v in repl.items():
            text = text.replace(k, v)
        target.write_text(text, encoding="utf-8")


def main() -> int:
    domains = read_flat(ROOT / "domains.yml")
    types = read_flat(ROOT / "plugin_types.yml")
    for name, url in domains.items():
        if (ROOT / name).exists():
            continue
        url = url.rstrip("/")
        kind = types.get(name, "anime").lower()
        if not NAME_RE.fullmatch(name):
            print(f"[SKIP] {name}: nama harus huruf/angka dan berakhiran 'Provider'")
            continue
        if not URL_RE.fullmatch(url):
            print(f"[SKIP] {name}: URL tidak valid ({url!r})")
            continue
        if not (TEMPLATES / kind).is_dir():
            print(f"[SKIP] {name}: jenis '{kind}' tidak dikenal (anime | movie)")
            continue
        scaffold(name, url, kind)
        print(f"[BARU] {name}: plugin dibuat dari template '{kind}' ({url})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
