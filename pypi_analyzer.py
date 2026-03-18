"""
pypi_analyzer.py — explore the PURL-to-SWHID gap for PyPI packages.

Demonstrates:
  - pkg:pypi/torch@2.6.0  → 0 sdists, many wheels, wildly different sizes
  - pkg:pypi/six@1.17.0   → sdist SWHID found in Software Heritage archive
  - pkg:pypi/certifi@...  → sdist SWHID NOT found (generated files differ from git)

Usage:
    python pypi_analyzer.py pkg:pypi/torch@2.6.0
    python pypi_analyzer.py pkg:pypi/six@1.17.0
    python pypi_analyzer.py pkg:pypi/certifi@2024.12.14
"""

import io
import os
import sys
import shutil
import tarfile
import requests
from swhid_verifier import compute_swhid, verify_swhid

PYPI_API = "https://pypi.org/pypi"


def parse_purl(purl):
    if not purl.startswith("pkg:pypi/"):
        raise ValueError(f"Expected pkg:pypi/ PURL, got: {purl}")
    rest = purl[len("pkg:pypi/"):]
    if "@" not in rest:
        raise ValueError(f"PURL must include @version: {purl}")
    name, version = rest.split("@", 1)
    return name, version


def query_pypi(name, version):
    resp = requests.get(f"{PYPI_API}/{name}/{version}/json")
    resp.raise_for_status()
    data = resp.json()

    sdists, wheels = [], []
    for f in data["urls"]:
        entry = {
            "filename": f["filename"],
            "url":      f["url"],
            "size":     f["size"],
        }
        if f["packagetype"] == "sdist":
            sdists.append(entry)
        elif f["packagetype"] == "bdist_wheel":
            parts = f["filename"][:-4].split("-")
            entry["python"]   = parts[2] if len(parts) > 2 else "?"
            entry["abi"]      = parts[3] if len(parts) > 3 else "?"
            entry["platform"] = parts[4] if len(parts) > 4 else "?"
            wheels.append(entry)

    return sdists, wheels


def print_wheels_table(wheels, name, version):
    if not wheels:
        print(f"  (no wheels)")
        return
    sizes   = [f"{w['size'] // 1024 // 1024:.1f} MB" if w['size'] > 1_000_000
               else f"{w['size'] // 1024:,} KB" for w in wheels]
    col_f = max(len(w['filename']) for w in wheels)
    col_s = max(len(s) for s in sizes)
    col_p = max(len(w['python'])   for w in wheels)
    col_a = max(len(w['abi'])      for w in wheels)
    col_t = max(len(w['platform']) for w in wheels)

    print(f"  {'Filename':<{col_f}}  {'Size':>{col_s}}  {'Python':<{col_p}}  {'ABI':<{col_a}}  Platform")
    print(f"  {'-'*col_f}  {'-'*col_s}  {'-'*col_p}  {'-'*col_a}  {'-'*col_t}")
    for w, size_str in zip(wheels, sizes):
        print(f"  {w['filename']:<{col_f}}  {size_str:>{col_s}}  {w['python']:<{col_p}}  {w['abi']:<{col_a}}  {w['platform']}")


def download_and_extract_sdist(sdist):
    target = "tmp"
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target)

    print(f"  Downloading {sdist['filename']} ({sdist['size'] // 1024:,} KB)...")
    resp = requests.get(sdist["url"])
    resp.raise_for_status()

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        tar.extractall(path=target, filter="data")

    # unwrap single top-level directory
    items = os.listdir(target)
    if len(items) == 1:
        inner = os.path.join(target, items[0])
        if os.path.isdir(inner):
            return inner
    return target


def analyze(purl):
    name, version = parse_purl(purl)

    print(f"\n{'='*60}")
    print(f"Package: {purl}")
    print(f"{'='*60}")

    sdists, wheels = query_pypi(name, version)

    total_wheels_size = sum(w["size"] for w in wheels)
    total_sdist_size  = sum(s["size"] for s in sdists)

    print(f"\nArtifacts on PyPI:")
    print(f"  sdists : {len(sdists)}" +
          (f"  ({total_sdist_size // 1024:,} KB total)" if sdists else ""))
    print(f"  wheels : {len(wheels)}" +
          (f"  ({total_wheels_size // 1024 // 1024:.0f} MB total)" if wheels else ""))

    if wheels:
        min_w = min(wheels, key=lambda w: w["size"])
        max_w = max(wheels, key=lambda w: w["size"])
        print(f"  smallest wheel: {min_w['filename']}  ({min_w['size'] // 1024:,} KB)")
        print(f"  largest wheel:  {max_w['filename']}  ({max_w['size'] // 1024 // 1024:.1f} MB)")
        print(f"\nFull wheel list:")
        print_wheels_table(wheels, name, version)

    if not sdists:
        print(f"\nFinding: No sdist published for {name} {version}.")
        print(f"  A PURL cannot be resolved to a single source SWHID.")
        print(f"  One PURL → {len(wheels)} artifacts — the mapping is 1-to-many.")
        return

    # sdist exists — attempt SWHID computation
    print(f"\nsdist found — computing SWHID...")
    source_path = download_and_extract_sdist(sdists[0])
    swhid = compute_swhid(source_path)
    found = verify_swhid(swhid)

    print(f"\n  SWHID: {swhid}")
    print(f"  SWH:   {'FOUND' if found else 'not found'}")

    if found:
        print(f"\nFinding: {name} {version} — sdist SWHID matches Software Heritage archive.")
        print(f"  Pure-Python sdists with no generated files produce a stable, verifiable SWHID.")
    else:
        print(f"\nFinding: {name} {version} — SWHID computed but NOT found in Software Heritage.")
        print(f"  The sdist tree diverges from the archived git tree.")
        print(f"  Likely cause: generated files (.egg-info, CA bundles, etc.) present in sdist")
        print(f"  but not in the git repository. Normalization rules for PyPI sdists are")
        print(f"  not yet standardized — this is an open problem.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pypi_analyzer.py <purl>")
        print("  e.g. python pypi_analyzer.py pkg:pypi/torch@2.6.0")
        sys.exit(1)
    analyze(sys.argv[1])
