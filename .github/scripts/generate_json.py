#!/usr/bin/env python3
"""
Pembuat JSON otomatis yang sesuai format CloudStream.

Dua subperintah:

  repo      Tulis repo.json (manifest repositori) di root repo, dengan nama repo GitHub
            yang benar (dari GITHUB_REPOSITORY atau --repo). Dijalankan SEBELUM build supaya
            ikut ter-commit ke branch utama.

  plugins   Tulis plugins.json final di folder builds. Sumber utama: build/plugins.json
            dari Gradle (makePluginsJson). Script ini melengkapi, memperbaiki, dan
            MEMVALIDASI tiap entri terhadap file .cs3 yang benar-benar ada. Kalau file JSON
            Gradle tidak ada, entri dibuat sendiri dari build.gradle.kts + domains.yml.
            Exit code 1 kalau ada entri yang tidak valid, supaya workflow gagal terang-terangan
            dan tidak mempublikasikan JSON rusak.

Format yang dipakai CloudStream
  repo.json     {name, description, manifestVersion: 1, pluginLists: [url plugins.json]}
  plugins.json  [{name, internalName, url, iconUrl, apiVersion, version, authors, description,
                  repositoryUrl, tvTypes, language, status, fileSize, isAdult?}]
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

# TvType yang dikenal CloudStream (nama enum persis)
VALID_TV_TYPES = {
    "Movie", "AnimeMovie", "TvSeries", "Cartoon", "Anime", "OVA", "Torrent", "Documentary",
    "AsianDrama", "Live", "NSFW", "Others", "Music", "AudioBook", "CustomMedia", "Audio", "Podcast",
}
DEFAULT_API_VERSION = 1
DEFAULT_REPO_NAME = "Plugin ID"
DEFAULT_REPO_DESC = "Repo plugin Cloudstream, dibuild otomatis lewat GitHub Actions"


# ----------------------------------------------------------------- util baca
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


def _kts_str(text: str, key: str):
    m = re.search(rf'^\s*{key}\s*=\s*"((?:[^"\\]|\\.)*)"', text, re.M)
    return m.group(1).replace('\\"', '"') if m else None


def _kts_int(text: str, key: str):
    m = re.search(rf"^\s*{key}\s*=\s*(\d+)", text, re.M)
    return int(m.group(1)) if m else None


def _kts_bool(text: str, key: str):
    m = re.search(rf"^\s*{key}\s*=\s*(true|false)", text, re.M)
    return (m.group(1) == "true") if m else None


def _kts_list(text: str, key: str):
    m = re.search(rf"^\s*{key}\s*=\s*listOf\(([^)]*)\)", text, re.M)
    if not m:
        return None
    return re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))


def parse_gradle(folder: Path) -> dict:
    g = folder / "build.gradle.kts"
    if not g.exists():
        return {}
    t = g.read_text(encoding="utf-8")
    return {
        "version": _kts_int(t, "version"),
        "description": _kts_str(t, "description"),
        "authors": _kts_list(t, "authors"),
        "status": _kts_int(t, "status"),
        "tvTypes": _kts_list(t, "tvTypes"),
        "language": _kts_str(t, "language"),
        "iconUrl": _kts_str(t, "iconUrl"),
        "isAdult": _kts_bool(t, "isAdult"),
    }


def display_name(folder_name: str) -> str:
    return folder_name[: -len("Provider")] if folder_name.endswith("Provider") and len(folder_name) > 8 else folder_name


def favicon(url: str) -> str:
    host = urlparse(url).netloc or url
    return f"https://www.google.com/s2/favicons?domain={host}&sz=128"


def repo_from_env(cli: str | None) -> str:
    repo = cli or os.environ.get("GITHUB_REPOSITORY") or ""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        sys.exit("GITHUB_REPOSITORY tidak valid atau kosong. Pakai --repo user/nama-repo")
    return repo


# ------------------------------------------------------------------- repo.json
def cmd_repo(args) -> int:
    repo = repo_from_env(args.repo)
    target = ROOT / "repo.json"
    name, desc = DEFAULT_REPO_NAME, DEFAULT_REPO_DESC
    if target.exists():
        try:
            old = json.loads(target.read_text(encoding="utf-8"))
            name = old.get("name") or name
            desc = old.get("description") or desc
        except json.JSONDecodeError:
            pass
    data = {
        "name": name,
        "description": desc,
        "manifestVersion": 1,
        "pluginLists": [f"https://raw.githubusercontent.com/{repo}/{args.branch}/plugins.json"],
    }
    new_text = json.dumps(data, indent=4, ensure_ascii=False) + "\n"
    if not target.exists() or target.read_text(encoding="utf-8") != new_text:
        target.write_text(new_text, encoding="utf-8")
        print(f"[UBAH] repo.json -> {data['pluginLists'][0]}")
    else:
        print("[SAMA] repo.json")
    return 0


# ---------------------------------------------------------------- plugins.json
def build_entry(folder_name: str, repo: str, branch: str, builds: Path, domains: dict, base: dict) -> dict:
    """Gabungkan: data Gradle (base) + build.gradle.kts + default. Nilai base menang untuk url/name."""
    g = parse_gradle(ROOT / folder_name)
    cs3 = builds / f"{folder_name}.cs3"
    e = dict(base)
    e["internalName"] = folder_name
    bn = base.get("name")
    e["name"] = bn if bn and bn != folder_name else display_name(folder_name)
    e["url"] = f"https://raw.githubusercontent.com/{repo}/{branch}/{folder_name}.cs3"
    e["repositoryUrl"] = f"https://github.com/{repo}"
    e["apiVersion"] = base.get("apiVersion", DEFAULT_API_VERSION)
    e["version"] = g.get("version") if g.get("version") is not None else base.get("version", 1)
    e["authors"] = g.get("authors") or base.get("authors") or [DEFAULT_REPO_NAME]
    e["description"] = g.get("description") or base.get("description") or ""
    e["language"] = g.get("language") or base.get("language") or "id"
    e["status"] = g.get("status") if g.get("status") is not None else base.get("status", 1)
    e["tvTypes"] = g.get("tvTypes") or base.get("tvTypes") or ["Others"]
    icon = g.get("iconUrl") or base.get("iconUrl")
    if not icon and folder_name in domains:
        icon = favicon(domains[folder_name])
    if icon:
        e["iconUrl"] = icon
    if g.get("isAdult") is not None:
        e["isAdult"] = g["isAdult"]
    if cs3.exists():
        e["fileSize"] = cs3.stat().st_size
    return e


def validate_entry(e: dict, builds: Path) -> list:
    errs = []
    req = {"name": str, "internalName": str, "url": str, "repositoryUrl": str,
           "version": int, "apiVersion": int, "status": int, "language": str,
           "authors": list, "tvTypes": list, "description": str}
    for k, typ in req.items():
        if k not in e:
            errs.append(f"field '{k}' hilang")
        elif not isinstance(e[k], typ) or isinstance(e[k], bool):
            errs.append(f"field '{k}' harus {typ.__name__}")
    if errs:
        return errs
    if e["status"] not in (0, 1, 2, 3):
        errs.append("status harus 0..3 (0 Down, 1 Ok, 2 Slow, 3 Beta-only)")
    if e["version"] < 0:
        errs.append("version negatif")
    bad = [t for t in e["tvTypes"] if t not in VALID_TV_TYPES]
    if bad:
        errs.append(f"tvTypes tidak dikenal CloudStream: {bad}")
    if not e["tvTypes"]:
        errs.append("tvTypes kosong")
    if not e["url"].endswith(".cs3") or not e["url"].startswith("https://"):
        errs.append("url harus https dan berakhiran .cs3")
    if not all(isinstance(a, str) and a for a in e["authors"]):
        errs.append("authors harus daftar string tidak kosong")
    cs3 = builds / f"{e['internalName']}.cs3"
    if not cs3.exists():
        errs.append(f"file {cs3.name} tidak ada di folder builds")
    elif cs3.stat().st_size < 1000:
        errs.append(f"file {cs3.name} terlalu kecil ({cs3.stat().st_size} byte), build mungkin rusak")
    return errs


def cmd_plugins(args) -> int:
    repo = repo_from_env(args.repo)
    builds = Path(args.builds_dir).resolve()
    domains = read_flat(ROOT / "domains.yml")

    base_by_name = {}
    gj = Path(args.gradle_json) if args.gradle_json else None
    if gj and gj.exists():
        try:
            for item in json.loads(gj.read_text(encoding="utf-8")):
                if isinstance(item, dict) and item.get("internalName"):
                    base_by_name[item["internalName"]] = item
            print(f"[INFO] {len(base_by_name)} entri dari {gj}")
        except json.JSONDecodeError as ex:
            print(f"[WARN] {gj} bukan JSON valid ({ex}), dibuat ulang dari build.gradle.kts")
    else:
        print("[INFO] plugins.json Gradle tidak ada, dibuat dari build.gradle.kts")

    # plugin = folder yang punya build.gradle.kts DAN file .cs3 hasil build
    folders = sorted(p.name for p in ROOT.iterdir() if p.is_dir() and (p / "build.gradle.kts").exists())
    entries, problems = [], 0
    for name in folders:
        cs3 = builds / f"{name}.cs3"
        if not cs3.exists():
            print(f"[LEWAT] {name}: tidak ada .cs3 (build gagal atau plugin dinonaktifkan)")
            continue
        e = build_entry(name, repo, args.branch, builds, domains, base_by_name.get(name, {}))
        errs = validate_entry(e, builds)
        if errs:
            problems += 1
            for m in errs:
                print(f"[ERROR] {name}: {m}")
            continue
        print(f"[OK]    {name}: v{e['version']} status={e['status']} {e['fileSize']} byte")
        entries.append(e)

    if not entries:
        print("[ERROR] tidak ada satu pun plugin valid, plugins.json tidak ditulis")
        return 1

    # urutan kunci mengikuti keluaran resmi supaya diff rapi
    order = ["iconUrl", "apiVersion", "repositoryUrl", "fileSize", "status", "language", "authors",
             "tvTypes", "version", "internalName", "description", "url", "name", "isAdult"]
    out = [{k: e[k] for k in order if k in e} for e in entries]
    (builds / "plugins.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[SELESAI] plugins.json: {len(out)} plugin, {problems} bermasalah")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="user/nama-repo (default: env GITHUB_REPOSITORY)")
    ap.add_argument("--branch", default="builds", help="branch tempat .cs3 & plugins.json dipublikasikan")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("repo")
    p = sub.add_parser("plugins")
    p.add_argument("--builds-dir", required=True)
    p.add_argument("--gradle-json", help="path build/plugins.json hasil Gradle")
    args = ap.parse_args()
    return cmd_repo(args) if args.cmd == "repo" else cmd_plugins(args)


if __name__ == "__main__":
    sys.exit(main())
