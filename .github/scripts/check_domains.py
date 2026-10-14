#!/usr/bin/env python3
"""
Deteksi domain baru otomatis dan perbarui domains.yml.

Untuk tiap baris di domains.yml: buka URL-nya, ikuti redirect, dan kalau situs asli
(halaman memuat nama situs) ternyata pindah ke domain lain, domains.yml diperbarui.
Kalau situs diblokir bot atau mati, baris dibiarkan (edit manual).
Setelah ini, apply_domains.py + build akan jalan di workflow.
"""
import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DOMAINS = ROOT / "domains.yml"

UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")


def read_flat(path: Path) -> dict:
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def probe(url: str):
    """Return (status, final_url, body) atau None kalau tidak terjangkau."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.geturl(), r.read(300_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        try:
            body = e.read(300_000).decode("utf-8", "ignore")
        except Exception:
            body = ""
        return e.code, e.geturl() or url, body
    except Exception:
        return None


def judge(result, keyword: str) -> str:
    """'ok' | 'unknown' (kemungkinan Cloudflare) | 'bad'"""
    if result is None:
        return "bad"
    status, _, body = result
    if status == 200:
        return "ok" if keyword.lower() in body.lower() else "bad"
    if status in (403, 429, 503):
        return "unknown"   # diblokir bot, tidak bisa dipastikan
    return "bad"


def set_domain(text: str, folder: str, url: str) -> str:
    return re.sub(rf"^({re.escape(folder)}\s*:\s*).*$", rf"\g<1>{url}",
                  text, count=1, flags=re.MULTILINE)


def main() -> None:
    current = read_flat(DOMAINS)
    text = DOMAINS.read_text(encoding="utf-8")

    for folder, cur in current.items():
        # kata kunci = nama plugin (mis. "Kuramanime"); harus ada di halaman supaya
        # domain parkir/iklan tidak ikut terpilih
        keyword = folder.replace("Provider", "")

        res = probe(cur)
        verdict = judge(res, keyword)

        if verdict == "ok":
            final = origin(res[1])
            if final != cur:
                print(f"[BARU] {folder}: redirect {cur} -> {final}")
                text = set_domain(text, folder, final)
            else:
                print(f"[OK]   {folder}: {cur}")
            continue

        if verdict == "unknown":
            print(f"[SKIP] {folder}: {cur} diblokir bot (Cloudflare?), tidak diubah")
            continue

        print(f"[MATI] {folder}: {cur} tidak valid, edit URL-nya di domains.yml")

    DOMAINS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
