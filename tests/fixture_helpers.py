"""Pembantu tes: membuat fixture HTML palsu (bukan tes; tidak ikut ditemukan unittest)."""
from pathlib import Path

PAD = "<!-- " + "x" * 1200 + " -->"


def html(host: str, body: str = "") -> str:
    return (f'<!DOCTYPE html><html><head><link rel="canonical" href="https://{host}/x/">'
            f"<title>t</title></head><body>{body}{PAD}</body></html>")


def mhtml(host: str, body: str = "") -> str:
    return ('From: <Saved by Blink>\r\n'
            f"Snapshot-Content-Location: https://{host}/halaman/\r\n"
            'Content-Type: multipart/related;\r\n\tboundary="----B----"\r\n\r\n'
            "------B----\r\nContent-Type: text/html\r\n\r\n"
            f"{html(host, body)}\r\n------B------\r\n")


def write_fixtures(root: Path, name: str, host: str, mhtml_format: bool = False, kinds=("list", "detail", "episode")):
    d = Path(root) / "tests" / "kotlin" / "fixtures" / name
    d.mkdir(parents=True, exist_ok=True)
    for k in kinds:
        (d / f"{k}.html").write_text((mhtml if mhtml_format else html)(host), encoding="utf-8")
