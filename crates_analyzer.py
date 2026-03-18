"""
crates_analyzer.py — demonstrate SWHID normalization for crates.io packages.

Demonstrates:
  - pkg:cargo/serde@1.0.203 → downloads .crate, shows 3 injected files,
    strips them, computes SWHID, compares against git tag SWHID in SWH archive.
  - Result: MATCH — proving normalization is deterministic.

Usage:
    python crates_analyzer.py pkg:cargo/serde@1.0.203
"""

import io
import json
import os
import sys
import shutil
import tarfile
import requests
from swhid_verifier import compute_swhid

SWH_API       = "https://archive.softwareheritage.org/api/1"
CRATES_HEADERS = {"User-Agent": "swhid-poc/0.1 (gsoc research)"}
INJECTED_FILES = [".cargo_vcs_info.json", "Cargo.toml", "Cargo.toml.orig"]


def parse_purl(purl):
    if not purl.startswith("pkg:cargo/"):
        raise ValueError(f"Expected pkg:cargo/ PURL, got: {purl}")
    rest = purl[len("pkg:cargo/"):]
    if "@" not in rest:
        raise ValueError(f"PURL must include @version: {purl}")
    name, version = rest.split("@", 1)
    return name, version


def fetch_crate_url(name, version):
    url = f"https://crates.io/api/v1/crates/{name}/{version}"
    resp = requests.get(url, headers=CRATES_HEADERS)
    resp.raise_for_status()
    data = resp.json()
    if data["version"]["yanked"]:
        raise ValueError(f"Crate {name} {version} is yanked")
    return f"https://static.crates.io/crates/{name}/{name}-{version}.crate"


def download_and_extract(crate_url, name, version):
    target = "tmp"
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target)

    print(f"  Downloading from {crate_url}...")
    resp = requests.get(crate_url)
    resp.raise_for_status()

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        tar.extractall(path=target, filter="data")

    # crates always extract to a single top-level dir: name-version/
    items = os.listdir(target)
    source_path = os.path.join(target, items[0]) if len(items) == 1 else target

    # read injected files before stripping
    injected = {}
    for filename in INJECTED_FILES:
        full = os.path.join(source_path, filename)
        if os.path.exists(full):
            with open(full, "r", encoding="utf-8") as f:
                injected[filename] = f.read()

    return source_path, injected


def strip_injected(source_path):
    removed = []
    for filename in INJECTED_FILES:
        full = os.path.join(source_path, filename)
        if os.path.exists(full):
            os.remove(full)
            removed.append(filename)
    return removed


def fetch_swh_dir_for_revision(sha1):
    resp = requests.get(f"{SWH_API}/revision/{sha1}/")
    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        raise RuntimeError("SWH API rate limit reached — try again later")
    resp.raise_for_status()
    return resp.json()["directory"]


def analyze(purl):
    name, version = parse_purl(purl)

    print(f"\n{'='*60}")
    print(f"Crate: {purl}")
    print(f"{'='*60}")

    crate_url = fetch_crate_url(name, version)
    print(f"\nStep 1 — Download and extract")
    source_path, injected = download_and_extract(crate_url, name, version)
    print(f"  Extracted to: {source_path}/")

    # --- show injected files ---
    print(f"\nStep 2 — Registry-injected files (present in .crate, absent from git)")
    if not injected:
        print("  (none found — older crate?)")
    for filename in INJECTED_FILES:
        if filename not in injected:
            continue
        lines = injected[filename].splitlines()
        preview = "\n    ".join(lines[:6])
        suffix  = f"\n    ... ({len(lines) - 6} more lines)" if len(lines) > 6 else ""
        print(f"\n  {filename}")
        print(f"  {'─'*len(filename)}")
        print(f"    {preview}{suffix}")

    # --- strip ---
    print(f"\nStep 3 — Strip injected files")
    removed = strip_injected(source_path)
    print(f"  Removed: {', '.join(removed)}")

    # --- compute SWHID ---
    print(f"\nStep 4 — Compute SWHID of stripped tree")
    swhid = compute_swhid(source_path)
    computed_hash = str(swhid).split(":")[-1]
    print(f"  SWHID: {swhid}")

    # --- git sha1 from vcs info ---
    if ".cargo_vcs_info.json" not in injected:
        print(f"\nNo .cargo_vcs_info.json — cannot retrieve git sha1 for comparison.")
        return

    vcs_info    = json.loads(injected[".cargo_vcs_info.json"])
    sha1        = vcs_info.get("git", {}).get("sha1")
    path_in_vcs = vcs_info.get("path_in_vcs", "")

    if not sha1:
        print(f"\nNo git sha1 in .cargo_vcs_info.json — cannot compare.")
        return

    if path_in_vcs:
        print(f"\nNote: path_in_vcs = '{path_in_vcs}'")
        print(f"  This crate is published from a monorepo subdirectory.")
        print(f"  The SWH revision points to the repo root, not the crate subdirectory.")
        print(f"  Skipping comparison — would require traversing SWH directory tree.")
        return

    # --- SWH lookup ---
    print(f"\nStep 5 — Look up git commit in Software Heritage archive")
    print(f"  git sha1: {sha1}")
    swh_dir_hash = fetch_swh_dir_for_revision(sha1)

    if swh_dir_hash is None:
        print(f"  Revision not yet archived by Software Heritage.")
        print(f"  Cannot verify normalization without archive entry.")
        return

    print(f"  SWH directory hash: {swh_dir_hash}")

    # --- compare ---
    print(f"\nStep 6 — Compare")
    print(f"  Computed (stripped .crate): {computed_hash}")
    print(f"  SWH (git tag):              {swh_dir_hash}")

    if computed_hash == swh_dir_hash:
        print(f"\nResult: MATCH")
        print(f"  Stripping the 3 registry-injected files recovers the exact git tree.")
        print(f"  One PURL → one stable SWHID. Normalization works for crates.io.")
    else:
        print(f"\nResult: MISMATCH")
        print(f"  Hashes differ. Possible causes: additional injected content,")
        print(f"  file permission differences, or a non-empty path_in_vcs.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python crates_analyzer.py <purl>")
        print("  e.g. python crates_analyzer.py pkg:cargo/serde@1.0.203")
        sys.exit(1)
    analyze(sys.argv[1])
