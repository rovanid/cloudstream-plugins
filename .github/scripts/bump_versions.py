#!/usr/bin/env python3
"""
Naikkan `version` di build.gradle.kts tiap plugin AKTIF kalau isinya berubah sejak build terakhir.

Dua macam plugin:
  - plugin scraper `*Provider`: aktif kalau barisnya ada (tanpa #) di domains.yml; sidik jarinya
    mencakup shared/kotlin karena kode itu ikut dikompilasi ke setiap plugin scraper.
  - plugin MANDIRI (mis. MyHomepage): folder tingkat atas ber-build.gradle.kts + src/ yang namanya bukan
    *Provider. Tidak ada di domains.yml (tidak punya situs), selalu aktif, dan sidik jarinya hanya isi
    foldernya sendiri (build.gradle.kts root tidak memasukkan shared/kotlin ke plugin ini).

Cloudstream hanya memperbarui plugin di perangkat pengguna kalau `version` naik. Sebelumnya versi
hanya naik saat mainUrl berubah, sehingga perbaikan di shared/kotlin (AdaptiveProvider.kt) atau
tuning manual Selectors.kt/SiteConfig tidak sampai ke pengguna.

Cara kerja: untuk tiap plugin dihitung sidik jari (SHA-256) dari
  - semua file di shared/kotlin
  - semua file di folder plugin (kecuali build/, .gradle/, __pycache__)
dengan dua normalisasi supaya tidak ada kenaikan palsu:
  - baris `version = N` di build.gradle.kts dibuang (kalau tidak, menaikkan versi mengubah hash)
  - baris pertama Selectors.kt yang berbentuk `// @auto-detect | detected: <tanggal> ...` dibuang
    (tanggalnya berubah tiap deteksi ulang walau selector sama)
  - CRLF dianggap sama dengan LF
Hash disimpan di plugin_hashes.json. Sidik jari berbeda -> versi plugin itu naik 1, hash disimpan.

  - Plugin yang belum ada di plugin_hashes.json hanya dicatat (baseline), versinya tidak naik.
  - Plugin nonaktif (`#Nama: url` di domains.yml) dilewati dan hash lamanya dipertahankan,
    jadi kalau diaktifkan lagi setelah kodenya berubah, versinya naik.
  - Aman dijalankan berulang: tanpa perubahan isi, tidak ada yang ditulis.

Jalankan SETELAH apply_domains.py dan detect_selectors.py (keduanya tidak lagi menaikkan versi sendiri).
Pakai:  python3 .github/scripts/bump_versions.py [--root .] [--dry-run]
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
STATE_NAME = "plugin_hashes.json"
SKIP_DIRS = {"build", ".gradle", "__pycache__"}
VERSION_LINE_RE = re.compile(rb"^[ \t]*version[ \t]*=[ \t]*\d+[ \t]*\r?\n?", re.MULTILINE)
VERSION_RE = re.compile(r"^(\s*version\s*=\s*)(\d+)", re.MULTILINE)
AUTO_HEADER_RE = re.compile(rb"^// @auto-detect \|[^\n]*\n?")
NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*Provider")


def read_active(path: Path) -> list:
    """Nama plugin aktif (baris tanpa #) dari domains.yml, urutan sesuai file."""
    names = []
    if not path.exists():
        return names
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            k = line.split(":", 1)[0].strip()
            if NAME_RE.fullmatch(k) and k not in names:
                names.append(k)
    return names


def read_standalone(root: Path) -> list:
    """Plugin mandiri: folder tingkat atas ber-build.gradle.kts + src/ yang namanya bukan *Provider."""
    names = []
    for d in sorted(root.iterdir(), key=lambda p: p.name):
        if (d.is_dir() and not d.name.startswith(".") and not NAME_RE.fullmatch(d.name)
                and (d / "build.gradle.kts").exists() and (d / "src").is_dir()):
            names.append(d.name)
    return names


def _normalized(path: Path) -> bytes:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    if path.name == "build.gradle.kts":
        data = VERSION_LINE_RE.sub(b"", data)
    elif path.name == "Selectors.kt":
        data = AUTO_HEADER_RE.sub(b"", data, count=1)
    return data


def _files(base: Path):
    if not base.is_dir():
        return
    for f in sorted(base.rglob("*"), key=lambda p: p.as_posix()):
        if not f.is_file():
            continue
        if any(part in SKIP_DIRS for part in f.relative_to(base).parts):
            continue
        yield f


def fingerprint(root: Path, folder: Path, use_shared: bool = True) -> str:
    h = hashlib.sha256()
    bases = [("plugin", folder)]
    if use_shared:
        bases.insert(0, ("shared", root / "shared" / "kotlin"))
    for label, base in bases:
        for f in _files(base):
            h.update(f"{label}/{f.relative_to(base).as_posix()}".encode("utf-8"))
            h.update(b"\0")
            h.update(_normalized(f))
            h.update(b"\0")
    return h.hexdigest()


def bump(gradle: Path):
    """Naikkan version di build.gradle.kts. Kembalikan (lama, baru) atau None."""
    text = gradle.read_text(encoding="utf-8")
    m = VERSION_RE.search(text)
    if not m:
        return None
    old = int(m.group(2))
    gradle.write_text(text[:m.start(2)] + str(old + 1) + text[m.end(2):], encoding="utf-8")
    return old, old + 1


def run(root: Path, dry_run: bool = False) -> list:
    """Hasil: daftar (nama, aksi, versi_lama, versi_baru). aksi: BASELINE | NAIK | SAMA | LEWAT | WARN."""
    state_path = root / STATE_NAME
    state = {}
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = {k: v for k, v in loaded.items() if isinstance(v, str)}
        except json.JSONDecodeError:
            print(f"[WARN] {STATE_NAME} rusak, semua plugin dicatat ulang sebagai baseline")

    results, new_state = [], dict(state)
    names = read_active(root / "domains.yml")
    names += [n for n in read_standalone(root) if n not in names]
    for name in names:
        folder = root / name
        gradle = folder / "build.gradle.kts"
        if not gradle.exists():
            results.append((name, "LEWAT", None, None))
            continue
        fp = fingerprint(root, folder, use_shared=bool(NAME_RE.fullmatch(name)))
        if name not in state:
            results.append((name, "BASELINE", None, None))
        elif state[name] != fp:
            if dry_run:
                results.append((name, "NAIK", None, None))
            else:
                v = bump(gradle)
                if v is None:
                    results.append((name, "WARN", None, None))
                else:
                    results.append((name, "NAIK", v[0], v[1]))
        else:
            results.append((name, "SAMA", None, None))
            continue
        new_state[name] = fp

    # buang catatan plugin yang foldernya sudah tidak ada; plugin nonaktif (folder ada) dipertahankan
    for name in list(new_state):
        if not (root / name / "build.gradle.kts").exists():
            del new_state[name]

    if not dry_run and new_state != state:
        state_path.write_text(json.dumps(new_state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--dry-run", action="store_true", help="hanya laporkan, tidak menulis apa pun")
    a = ap.parse_args()
    root = Path(a.root)
    if not (root / "domains.yml").exists():
        print("domains.yml tidak ditemukan", file=sys.stderr)
        return 1
    for name, action, old, new in run(root, a.dry_run):
        if action == "NAIK" and old is not None:
            print(f"[NAIK]     {name}: version {old} -> {new} (isi berubah)")
        elif action == "NAIK":
            print(f"[NAIK]     {name}: isi berubah (dry-run, versi tidak diubah)")
        elif action == "BASELINE":
            print(f"[BASELINE] {name}: pertama kali dicatat, versi tidak naik")
        elif action == "WARN":
            print(f"[WARN]     {name}: isi berubah tetapi baris version tidak ditemukan di build.gradle.kts")
        elif action == "LEWAT":
            print(f"[LEWAT]    {name}: folder/build.gradle.kts tidak ada")
        else:
            print(f"[SAMA]     {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
