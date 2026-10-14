#!/usr/bin/env python3
"""
Sinkronkan folder plugin dengan domains.yml (dijalankan SEBELUM apply_domains.py):

  - baris baru di domains.yml  -> folder plugin dibuat dari .github/templates/
                                  (jenis dari plugin_types.yml: anime | movie)
  - baris dihapus / di-#       -> folder plugin dihapus

settings.gradle.kts otomatis memasukkan tiap folder yang punya build.gradle.kts,
jadi menghapus folder = plugin hilang dari build dan plugins.json.
Pengaman: tidak menghapus apa pun kalau domains.yml kosong/rusak, dan hanya menyentuh
folder bernama *Provider yang memang berbentuk plugin (build.gradle.kts + src/).
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


def is_plugin_folder(d: Path) -> bool:
    return (d.is_dir() and NAME_RE.fullmatch(d.name) is not None
            and (d / "build.gradle.kts").exists() and (d / "src").is_dir())


def prune(domains: dict) -> None:
    valid = {n for n, u in domains.items()
             if NAME_RE.fullmatch(n) and URL_RE.fullmatch(u.rstrip("/"))}
    if not valid:
        print("[AMAN] domains.yml tidak punya entri valid, tidak ada plugin yang dihapus")
        return
    for d in sorted(ROOT.iterdir()):
        if is_plugin_folder(d) and d.name not in domains:
            shutil.rmtree(d)
            print(f"[HAPUS] {d.name}: tidak ada lagi di domains.yml, folder dihapus")


def main() -> int:
    domains = read_flat(ROOT / "domains.yml")
    types = read_flat(ROOT / "plugin_types.yml")
    prune(domains)
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
