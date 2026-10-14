#!/usr/bin/env python3
"""
Utilitas fixture HTML yang dipakai bersama oleh registry.py, check_domains.py, sync_plugins.py
dan detect_selectors.py. Hanya memakai pustaka standar (tanpa beautifulsoup4) supaya registry.py
tetap bisa jalan paling awal di CI.

Aturan fixture (tahap "fixture dulu"):
  - Tiap plugin AKTIF di domains.yml wajib punya tiga berkas di
    tests/kotlin/fixtures/<NamaProvider>/ : list.html, detail.html, episode.html
  - Berkas harus HTML sungguhan (bukan kosong/placeholder).
  - Berkas harus berasal dari host yang SAMA dengan URL di domains.yml. Host asal dibaca dari
    header "Snapshot-Content-Location" (MHTML Chrome "Simpan halaman"), lalu <link rel=canonical>
    atau <meta property=og:url>. Kalau tidak ada petunjuk sama sekali, nama host harus muncul di
    isi HTML.
"""
import re
from pathlib import Path
from urllib.parse import urlparse

KINDS = ("list", "detail", "episode")
MIN_CHARS = 1000          # HTML asli selalu jauh lebih besar; ini hanya menolak berkas kosong/placeholder
SNAPSHOT_LOC_RE = re.compile(r"^Snapshot-Content-Location:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
HTML_SIGN_RE = re.compile(r"<(?:!doctype\s+html|html|head|body)\b", re.IGNORECASE)
_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)


def fixtures_dir(root: Path) -> Path:
    return Path(root) / "tests" / "kotlin" / "fixtures"


def rel_path(name: str, kind: str) -> str:
    return f"tests/kotlin/fixtures/{name}/{kind}.html"


def extract_html(raw: str) -> str:
    """Chrome 'Simpan halaman' berformat MHTML (Saved by Blink): ambil bagian text/html pertama."""
    if not raw.lstrip().startswith("From:") or "Saved by Blink" not in raw:
        return raw
    m = re.search(r'boundary="?([^"\r\n;]+)"?', raw)
    if not m:
        return raw
    for part in raw.split("--" + m.group(1))[1:]:
        sep = re.search(r"\r?\n\r?\n", part)
        if not sep:
            continue
        if re.search(r"(?i)content-type:\s*text/html", part[:sep.start()]):
            return part[sep.end():]
    return raw


def norm_host(host: str) -> str:
    host = (host or "").lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def host_of(url: str) -> str:
    return norm_host(urlparse(url).hostname or "")


def source_url(raw: str) -> str:
    """URL halaman asal fixture MHTML (header Snapshot-Content-Location), '' kalau bukan MHTML."""
    m = SNAPSHOT_LOC_RE.search(raw[:5000])
    return m.group(1) if m else ""


def _attr(tag: str, name: str) -> str:
    m = re.search(rf"""\b{name}\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", tag, re.IGNORECASE)
    return next((g for g in m.groups() if g is not None), "") if m else ""


def source_hosts(raw: str, html: str) -> list:
    """Host asal fixture. MHTML: header snapshot. HTML biasa: canonical / og:url."""
    snap = host_of(source_url(raw))
    if snap:
        return [snap]
    head = html[:400_000]
    hosts = []
    for tag in _LINK_TAG_RE.findall(head):
        if "canonical" in _attr(tag, "rel").lower():
            hosts.append(host_of(_attr(tag, "href")))
    for tag in _META_TAG_RE.findall(head):
        if _attr(tag, "property").lower() == "og:url":
            hosts.append(host_of(_attr(tag, "content")))
    return sorted({h for h in hosts if h})


def problems(root: Path, name: str, url: str, check_host: bool = True) -> list:
    """Daftar masalah fixture untuk satu plugin; kosong = fixture lengkap dan cocok dengan URL."""
    out = []
    want = host_of(url)
    d = fixtures_dir(root) / name
    for kind in KINDS:
        rel = rel_path(name, kind)
        p = d / f"{kind}.html"
        if not p.is_file():
            out.append(f"{rel} belum ada")
            continue
        raw = p.read_text(encoding="utf-8", errors="ignore")
        html = extract_html(raw)
        if len(html.strip()) < MIN_CHARS or not HTML_SIGN_RE.search(html[:400_000]):
            out.append(f"{rel} bukan HTML yang valid (kosong, terlalu kecil, atau placeholder)")
            continue
        if not check_host or not want:
            continue
        hosts = source_hosts(raw, html)
        if hosts:
            if want not in hosts:
                out.append(f"{rel} berasal dari {', '.join(hosts)}, bukan {want}")
        elif want not in html.lower():
            out.append(f"{rel} tidak punya petunjuk asal domain dan host {want} tidak muncul di isinya")
    return out
