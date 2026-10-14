#!/usr/bin/env python3
"""
Pemeriksa domain (tahap 2): MENGUSULKAN perubahan, tidak pernah langsung mengadopsi.

Untuk tiap entri aktif di domains.yml:
  1. probe (dengan retry) -> vonis: OK | BLOCKED | PARKED | DEAD
  2. kalau OK tetapi situs mengalihkan ke origin lain, origin baru DIVERIFIKASI SENDIRI
     (probe langsung ke origin baru, https, status 200, kata kunci ada, host belum dipakai plugin lain)
  3. hasilnya ditulis ke laporan JSON (--report) dan ringkasan Markdown (--summary)

Secara default skrip ini HANYA MELAPORKAN (domains.yml tidak diubah). Dengan --apply,
usulan yang lolos verifikasi ditulis ke domains.yml di working tree; workflow domain-watch.yml
lalu membuka Pull Request supaya manusia + tes yang memutuskan. build.yml tidak lagi memanggil skrip ini.

Kata kunci: domain_keywords.yml (opsional), default = nama folder tanpa "Provider" + label host saat ini.
Jalankan lokal:  python3 .github/scripts/check_domains.py [--apply] [--report out.json] [--summary out.md]
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOMAINS = ROOT / "domains.yml"
KEYWORDS = ROOT / "domain_keywords.yml"

UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")
RETRIES = 3
MIN_KEYWORD_LEN = 4   # keyword pendek ("a", "tv") cocok ke hampir semua halaman
BLOCK_CODES = (403, 429, 503)


# ---------------------------------------------------------------- jaringan
def probe(url: str, timeout: int = 20):
    """(status, final_url, body) atau None bila tidak terjangkau."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.geturl(), r.read(300_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        try:
            body = e.read(300_000).decode("utf-8", "ignore")
        except Exception:
            body = ""
        return e.code, e.geturl() or url, body
    except Exception:
        return None


def probe_retry(url: str, fetch=probe, retries: int = RETRIES, sleep=time.sleep):
    """Ulangi untuk kegagalan sementara (tidak terjangkau / 5xx selain 503-blokir)."""
    res = None
    for i in range(retries):
        res = fetch(url)
        if res is not None and res[0] < 500:
            return res
        if res is not None and res[0] in BLOCK_CODES:
            return res
        if i < retries - 1:
            sleep(2 * (i + 1))
    return res


# ---------------------------------------------------------------- logika murni (diuji)
def origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def host_label(url: str) -> str:
    """Label sebelum TLD: https://tv12.lk21official.cc -> lk21official."""
    parts = (urlparse(url).hostname or "").lower().split(".")
    return parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")


def read_keywords(path: Path = KEYWORDS) -> dict:
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (p.strip() for p in line.split(":", 1))
        words = [w.strip().lower() for w in v.split(",") if w.strip()]
        if words:
            out[k] = words
    return out


def keywords_for(name: str, current_url: str, table: dict) -> list:
    if name in table:
        return [k for k in table[name] if len(k) >= MIN_KEYWORD_LEN]
    kws = [name[: -len("Provider")].lower() if name.endswith("Provider") else name.lower()]
    lab = host_label(current_url)
    if lab and lab not in kws:
        kws.append(lab)
    return [k for k in kws if len(k) >= MIN_KEYWORD_LEN]


def has_keyword(body: str, kws: list) -> bool:
    low = body.lower()
    return any(k in low for k in kws)


def judge(result, kws: list) -> str:
    """OK | BLOCKED (bot, tidak bisa dipastikan) | PARKED (hidup tapi bukan situs ini) | DEAD."""
    if result is None:
        return "DEAD"
    status, _, body = result
    if status == 200:
        return "OK" if has_keyword(body, kws) else "PARKED"
    if status in BLOCK_CODES:
        return "BLOCKED"
    return "DEAD"


def verify_new_origin(new_origin: str, kws: list, taken_hosts: set, fetch=probe_retry):
    """Cek origin usulan SECARA LANGSUNG. Return (lolos, alasan)."""
    p = urlparse(new_origin)
    if p.scheme != "https":
        return False, "origin baru bukan https"
    if (p.hostname or "").lower() in taken_hosts:
        return False, "host baru sudah dipakai plugin lain"
    if not registry.URL_RE.fullmatch(new_origin):
        return False, "origin baru tidak lolos format registry"
    res = fetch(new_origin)
    if res is None:
        return False, "origin baru tidak terjangkau saat diverifikasi langsung"
    if res[0] != 200:
        return False, f"origin baru membalas HTTP {res[0]} saat diverifikasi langsung"
    if not has_keyword(res[2], kws):
        return False, "kata kunci tidak ditemukan di origin baru"
    return True, "terverifikasi langsung"


def evaluate(entries, kw_table, fetch=probe_retry) -> list:
    """entries: list registry.Entry aktif. Return list dict hasil per plugin."""
    results = []
    hosts = {e.name: (urlparse(e.url).hostname or "").lower() for e in entries}
    for e in entries:
        kws = keywords_for(e.name, e.url, kw_table)
        if not kws:
            results.append({"name": e.name, "current": e.url, "keywords": [], "verdict": "UNVERIFIED",
                            "status": None, "proposed": None,
                            "reason": "tidak ada kata kunci >= %d huruf; isi domain_keywords.yml" % MIN_KEYWORD_LEN})
            continue
        res = fetch(e.url)
        verdict = judge(res, kws)
        row = {"name": e.name, "current": e.url, "keywords": kws, "verdict": verdict,
               "status": res[0] if res else None, "proposed": None, "reason": ""}
        if verdict == "OK":
            final = origin(res[1])
            if final.rstrip("/") == e.url.rstrip("/"):
                row["reason"] = "domain aktif, tidak berubah"
            else:
                taken = {h for n, h in hosts.items() if n != e.name}
                ok, why = verify_new_origin(final, kws, taken, fetch)
                row["reason"] = f"redirect ke {final}: {why}"
                if ok:
                    row["proposed"] = final
                    row["verdict"] = "MOVED"
        elif verdict == "BLOCKED":
            row["reason"] = "diblokir bot (HTTP %s); tidak bisa dipastikan dari CI, domains.yml tidak diubah" % row["status"]
        elif verdict == "PARKED":
            row["reason"] = "situs membalas 200 tetapi kata kunci tidak ada (domain parkir/diganti?); tidak diubah"
        else:
            row["reason"] = "tidak terjangkau / error setelah %d percobaan; perlu domain baru dari manusia" % RETRIES
        results.append(row)
    return results


def set_domain(text: str, name: str, old: str, new: str) -> str:
    """Ganti HANYA URL di baris entri (komentar & spasi di baris itu tetap)."""
    pat = re.compile(rf"^(\s*{re.escape(name)}\s*:\s*){re.escape(old)}/?(?=\s|#|$)", re.MULTILINE)
    return pat.sub(lambda m: m.group(1) + new, text, count=1)


def apply_proposals(text: str, results: list) -> str:
    for r in results:
        if r["proposed"]:
            text = set_domain(text, r["name"], r["current"], r["proposed"])
    return text


def summary_md(results: list) -> str:
    icon = {"OK": "✅", "MOVED": "🔁", "BLOCKED": "⏸️", "PARKED": "🅿️", "DEAD": "❌", "UNVERIFIED": "❔"}
    lines = ["| Plugin | Vonis | Domain | Usulan | Keterangan |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['name']} | {icon.get(r['verdict'], '?')} {r['verdict']} | {r['current']} | "
                     f"{r['proposed'] or '-'} | {r['reason']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="tulis usulan yang lolos ke domains.yml (working tree)")
    ap.add_argument("--report", help="tulis hasil JSON ke berkas ini")
    ap.add_argument("--summary", help="tulis ringkasan Markdown ke berkas ini")
    a = ap.parse_args()

    rep = registry.Report()
    registry.parse_domains(DOMAINS.read_text(encoding="utf-8"), rep)
    entries = [e for e in rep.entries if e.active]
    results = evaluate(entries, read_keywords())

    for r in results:
        print(f"[{r['verdict']}] {r['name']}: {r['current']} - {r['reason']}")
    if a.report:
        Path(a.report).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    if a.summary:
        Path(a.summary).write_text(summary_md(results), encoding="utf-8")
    if a.apply:
        text = DOMAINS.read_text(encoding="utf-8")
        new = apply_proposals(text, results)
        if new != text:
            DOMAINS.write_text(new, encoding="utf-8")
            print("domains.yml diubah di working tree (belum di-commit; workflow membuat PR)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
