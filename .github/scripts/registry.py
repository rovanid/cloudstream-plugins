#!/usr/bin/env python3
"""
Validator registry domains.yml (+ plugin_types.yml).

Format TIDAK berubah (kompatibel dengan skrip lama):   NamaFolderProvider: https://domain
Yang baru: semua kesalahan yang sebelumnya DIABAIKAN diam-diam kini dilaporkan, dan build
berhenti (exit 1) kalau ada ERROR, sebelum check_domains / sync_plugins / apply_domains jalan.

ERROR  -> build diblokir:   nama/URL tidak valid, nama ganda, host ganda, baris tanpa ':',
                            jenis plugin tidak dikenal.
WARN   -> dilaporkan saja:  http (bukan https), folder plugin akan DIHAPUS sync_plugins
                            (ada di disk tetapi barisnya sudah tidak ada di domains.yml), plugin_types
                            menunjuk nama yang tidak ada.
Status:  `Nama: https://host` = aktif; `#Nama: https://host` = DISABLED (folder dipertahankan, tidak
         dibuild); baris dihapus = folder dihapus.
Jalankan lokal:  python3 .github/scripts/registry.py [--root .] [--json]
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*Provider")
URL_RE = re.compile(r"https?://[A-Za-z0-9.-]+(:\d+)?")   # sama dengan sync/apply_domains
KINDS = ("anime", "movie")
COMMENTED_ENTRY = re.compile(r"^#\s*([A-Za-z][A-Za-z0-9]*Provider)\s*:\s*(https?://\S+)")


@dataclass
class Entry:
    name: str
    url: str
    line: int
    active: bool = True


@dataclass
class Report:
    entries: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def parse_domains(text: str, rep: Report) -> None:
    for no, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            m = COMMENTED_ENTRY.match(stripped)
            if m:
                rep.entries.append(Entry(m.group(1), m.group(2).rstrip("/"), no, active=False))
            continue
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            rep.errors.append(f"baris {no}: tidak ada ':' ({line!r}); skrip lama akan mengabaikannya diam-diam")
            continue
        name, url = (p.strip() for p in line.split(":", 1))
        url = url.rstrip("/")
        if not NAME_RE.fullmatch(name):
            rep.errors.append(f"baris {no}: nama {name!r} harus huruf/angka dan berakhiran 'Provider'")
        if not URL_RE.fullmatch(url):
            rep.errors.append(f"baris {no}: URL {url!r} tidak valid untuk {name} "
                              "(harus http(s)://host tanpa path/query)")
        elif url.startswith("http://"):
            rep.warnings.append(f"baris {no}: {name} memakai http, bukan https")
        rep.entries.append(Entry(name, url, no))


def check_duplicates(rep: Report) -> None:
    by_name, by_lower, by_host = {}, {}, {}
    for e in (x for x in rep.entries if x.active):
        if e.name in by_name:
            rep.errors.append(f"baris {e.line}: nama {e.name} ganda (sudah di baris {by_name[e.name]}); "
                              "yang terakhir diam-diam menimpa yang pertama")
        by_name.setdefault(e.name, e.line)
        low = e.name.lower()
        if low in by_lower and by_lower[low] != e.name:
            rep.errors.append(f"baris {e.line}: {e.name} bentrok dengan {by_lower[low]} "
                              "(package Android memakai huruf kecil)")
        by_lower.setdefault(low, e.name)
        h = _host(e.url)
        if h and h in by_host and by_host[h] != e.name:
            rep.errors.append(f"baris {e.line}: host {h} dipakai ganda oleh {by_host[h]} dan {e.name}")
        if h:
            by_host.setdefault(h, e.name)


def read_types(path: Path, rep: Report) -> dict:
    types = {}
    if not path.exists():
        return types
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            rep.errors.append(f"plugin_types.yml baris {no}: tidak ada ':'")
            continue
        k, v = (p.strip() for p in line.split(":", 1))
        if v.lower() not in KINDS:
            rep.errors.append(f"plugin_types.yml baris {no}: jenis {v!r} tidak dikenal ({'|'.join(KINDS)})")
        types[k] = v.lower()
    return types


def check_disk(root: Path, rep: Report, types: dict) -> None:
    active = {e.name for e in rep.entries if e.active}
    disabled = {e.name for e in rep.entries if not e.active} - active
    for k in types:
        if k not in active:
            rep.warnings.append(f"plugin_types.yml: {k} tidak ada di domains.yml aktif")
    if not active:
        return
    for d in sorted(root.iterdir()):
        if (d.is_dir() and NAME_RE.fullmatch(d.name) and (d / "build.gradle.kts").exists()
                and (d / "src").is_dir() and d.name not in active
                and d.name not in disabled):
            rep.warnings.append(f"folder {d.name} ada di disk tetapi barisnya tidak ada di domains.yml: "
                                "sync_plugins.py AKAN MENGHAPUSNYA (termasuk tuning SiteConfig manual)")


def validate(root: Path) -> Report:
    rep = Report()
    dom = root / "domains.yml"
    if not dom.exists():
        rep.errors.append("domains.yml tidak ditemukan")
        return rep
    parse_domains(dom.read_text(encoding="utf-8"), rep)
    if not any(e.active for e in rep.entries):
        rep.errors.append("domains.yml tidak punya entri aktif")
    check_duplicates(rep)
    types = read_types(root / "plugin_types.yml", rep)
    check_disk(root, rep, types)
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rep = validate(Path(a.root))
    if a.json:
        print(json.dumps({"ok": rep.ok, "errors": rep.errors, "warnings": rep.warnings,
                          "entries": [e.__dict__ for e in rep.entries]}, indent=2, ensure_ascii=False))
    else:
        act = [e for e in rep.entries if e.active]
        print(f"{len(act)} entri aktif, {len(rep.entries) - len(act)} dinonaktifkan (di-#)")
        for m in rep.errors:
            print(f"::error::{m}")
        for m in rep.warnings:
            print(f"::warning::{m}")
        print("REGISTRY OK" if rep.ok else "REGISTRY GAGAL")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
