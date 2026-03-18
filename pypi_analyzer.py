"""
pypi_analyzer.py - Deep PURL-to-SWHID analysis for PyPI packages.

Computes SWHIDs for sdists, verifies against the SWH archive, and returns a
structured findings dict that the unified analyze.py CLI renders with rich.

Key cases demonstrated:
  pkg:pypi/torch@2.6.0        -> 0 sdists, many wheels -> 1 PURL : N artifacts
  pkg:pypi/six@1.17.0         -> sdist SWHID FOUND in SWH archive
  pkg:pypi/certifi@2024.12.14 -> sdist SWHID NOT FOUND (generated CA bundle)

Usage (standalone):
    python pypi_analyzer.py pkg:pypi/six@1.17.0
Or via unified analyzer:
    python analyze.py pkg:pypi/six@1.17.0
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


def _query_pypi(name, version):
    resp = requests.get(f"{PYPI_API}/{name}/{version}/json")
    resp.raise_for_status()
    return resp.json()


def _download_and_extract_sdist(sdist):
    target = "tmp"
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target)

    resp = requests.get(sdist["url"])
    resp.raise_for_status()

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        tar.extractall(path=target, filter="data")

    items = os.listdir(target)
    if len(items) == 1:
        inner = os.path.join(target, items[0])
        if os.path.isdir(inner):
            return inner
    return target


def _extract_vcs_url(project_urls, home_page):
    """Return the best VCS URL from PyPI project_urls metadata."""
    if project_urls:
        for key in ("Source", "Source Code", "Repository", "Code", "GitHub"):
            for k, v in project_urls.items():
                if key.lower() in k.lower():
                    return v
    return home_page or ""


def _compute_scores(has_sdist, found_in_swh):
    if not has_sdist:
        return {"reproducibility": 0, "provenance": 0, "normalization": 0, "overall": 0}
    if found_in_swh:
        # Works for pure-Python packages; normalization is not formalized yet
        return {"reproducibility": 8, "provenance": 10, "normalization": 6, "overall": 8}
    # sdist exists but tree diverges from git
    return {"reproducibility": 3, "provenance": 2, "normalization": 2, "overall": 2}


def analyze(name, version, purl=None):
    """
    Download and analyze a PyPI package. Returns a structured findings dict.
    Does not print anything - the caller is responsible for display.
    """
    purl = purl or f"pkg:pypi/{name}@{version}"
    data = _query_pypi(name, version)
    info = data["info"]

    # --- metadata ---
    project_urls = info.get("project_urls") or {}
    vcs_url = _extract_vcs_url(project_urls, info.get("home_page", ""))
    deps = info.get("requires_dist") or []

    metadata = {
        "summary":          info.get("summary", ""),
        "license":          info.get("license", ""),
        "author":           info.get("author", ""),
        "requires_python":  info.get("requires_python", ""),
        "home_page":        info.get("home_page", ""),
        "project_urls":     project_urls,
        "classifiers":      info.get("classifiers", []),
        "dependencies":     deps,
        "dependency_count": len(deps),
        "vcs_url":          vcs_url,
    }

    # --- artifact inventory ---
    sdists, wheels = [], []
    for f in data["urls"]:
        entry = {
            "filename": f["filename"],
            "url":      f["url"],
            "size":     f["size"],
            "sha256":   f.get("digests", {}).get("sha256", ""),
        }
        if f["packagetype"] == "sdist":
            sdists.append(entry)
        elif f["packagetype"] == "bdist_wheel":
            parts = f["filename"][:-4].split("-")
            entry["python"]   = parts[2] if len(parts) > 2 else "?"
            entry["abi"]      = parts[3] if len(parts) > 3 else "?"
            entry["platform"] = parts[4] if len(parts) > 4 else "?"
            wheels.append(entry)

    artifacts = {
        "sdist_count": len(sdists),
        "wheel_count": len(wheels),
        "sdists":      sdists,
        "wheels":      wheels,
    }

    # --- SWHID computation ---
    swhid_data = {}
    found_in_swh = None

    if sdists:
        source_path = _download_and_extract_sdist(sdists[0])
        computed = compute_swhid(source_path)
        found_in_swh = verify_swhid(computed)
        swhid_data = {
            "value":        str(computed),
            "source":       "sdist",
            "found_in_swh": found_in_swh,
            "vcs_url":      vcs_url,
        }

    # --- verdict ---
    has_sdist = len(sdists) > 0

    if not has_sdist:
        verdict = f"No sdist published - 1 PURL maps to {len(wheels)} wheel artifact(s)"
        explanation = (
            "PyPI distributes this package as wheels only. There is no canonical source "
            "distribution, so a single PURL cannot be resolved to one stable SWHID. "
            "The 1-to-many artifact mapping makes deterministic provenance impossible."
        )
        reproducible = False
    elif found_in_swh:
        verdict = "SWHID found in Software Heritage archive"
        explanation = (
            "The sdist tree matches the git tree archived by Software Heritage. "
            "This typically applies to pure-Python packages with no generated files. "
            "One PURL -> one stable SWHID. Provenance is fully verifiable."
        )
        reproducible = True
    else:
        verdict = "SWHID computed but NOT found in SWH archive"
        explanation = (
            "The sdist tree diverges from the archived git tree. Likely cause: generated "
            "files (.egg-info, CA bundles, compiled extensions, SOURCES.txt entries) are "
            "present in the sdist but absent from the git repository. PyPI normalization "
            "rules are not yet standardized - this is an open research problem."
        )
        reproducible = False

    analysis = {
        "reproducible": reproducible,
        "has_sdist":    has_sdist,
        "has_wheels":   len(wheels) > 0,
        "verdict":      verdict,
        "explanation":  explanation,
    }

    scores = _compute_scores(has_sdist, found_in_swh)

    return {
        "purl":      purl,
        "ecosystem": "pypi",
        "name":      name,
        "version":   version,
        "metadata":  metadata,
        "artifacts": artifacts,
        "swhid":     swhid_data,
        "analysis":  analysis,
        "scores":    scores,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pypi_analyzer.py <purl>")
        print("  e.g. python pypi_analyzer.py pkg:pypi/six@1.17.0")
        sys.exit(1)

    purl_arg = sys.argv[1]
    name, version = parse_purl(purl_arg)
    findings = analyze(name, version, purl_arg)

    a  = findings["artifacts"]
    s  = findings["swhid"]
    an = findings["analysis"]
    sc = findings["scores"]
    m  = findings["metadata"]

    print(f"\n{'='*60}")
    print(f"Package: {purl_arg}")
    print(f"{'='*60}")
    if m.get("summary"):
        print(f"\n  {m['summary']}")
    if m.get("license"):
        print(f"  License: {m['license']}")
    if m.get("vcs_url"):
        print(f"  Source:  {m['vcs_url']}")
    print(f"\nArtifacts:  sdists={a['sdist_count']}  wheels={a['wheel_count']}")
    if s:
        print(f"\nSWHID: {s['value']}")
        print(f"SWH:   {'FOUND' if s['found_in_swh'] else 'NOT FOUND'}")
    print(f"\nVerdict: {an['verdict']}")
    print(f"  {an['explanation']}")
    print(f"\nScores:")
    for k in ("reproducibility", "provenance", "normalization", "overall"):
        print(f"  {k:>15}: {sc[k]}/10")
