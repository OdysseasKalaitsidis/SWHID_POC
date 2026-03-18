"""
crates_analyzer.py - Deep PURL-to-SWHID analysis for crates.io packages.

Downloads the .crate artifact, identifies and strips the 3 registry-injected
files, computes a SWHID, and verifies it against the SWH git archive.

Key case demonstrated:
  pkg:cargo/serde@1.0.203 -> MATCH - one PURL, one stable, verifiable SWHID.

Usage:
    python analyze.py pkg:cargo/serde@1.0.203
"""

import io
import json
import os
import sys
import shutil
import tarfile
import requests
from swhid_verifier import compute_swhid

SWH_API        = "https://archive.softwareheritage.org/api/1"
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


def _fetch_crate_metadata(name, version):
    """Return merged metadata from the version endpoint and the crate endpoint."""
    resp = requests.get(
        f"https://crates.io/api/v1/crates/{name}/{version}",
        headers=CRATES_HEADERS,
    )
    resp.raise_for_status()
    ver_data = resp.json()

    if ver_data["version"]["yanked"]:
        raise ValueError(f"Crate {name} {version} is yanked")

    # Second call for crate-level fields (description, keywords, categories)
    resp2 = requests.get(
        f"https://crates.io/api/v1/crates/{name}",
        headers=CRATES_HEADERS,
    )
    resp2.raise_for_status()
    krate = resp2.json().get("crate", {})
    ver   = ver_data["version"]

    return {
        "description":  krate.get("description", ""),
        "license":      ver.get("license", ""),
        "repository":   krate.get("repository", ""),
        "homepage":     krate.get("homepage", ""),
        "keywords":     krate.get("keywords", []),
        "categories":   krate.get("categories", []),
        "crate_size":   ver.get("crate_size"),
        "downloads":    ver.get("downloads"),
        "rust_version": ver.get("rust_version"),
    }


def _download_and_extract(crate_url, name, version):
    target = "tmp"
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target)

    resp = requests.get(crate_url)
    resp.raise_for_status()

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        tar.extractall(path=target, filter="data")

    items = os.listdir(target)
    source_path = os.path.join(target, items[0]) if len(items) == 1 else target

    injected = {}
    for filename in INJECTED_FILES:
        full = os.path.join(source_path, filename)
        if os.path.exists(full):
            with open(full, "r", encoding="utf-8") as f:
                injected[filename] = f.read()

    return source_path, injected


def _count_files(path):
    count = 0
    for _, _, files in os.walk(path):
        count += len(files)
    return count


def _strip_injected(source_path):
    removed = []
    for filename in INJECTED_FILES:
        full = os.path.join(source_path, filename)
        if os.path.exists(full):
            os.remove(full)
            removed.append(filename)
    return removed


def _fetch_swh_dir_for_revision(sha1):
    resp = requests.get(f"{SWH_API}/revision/{sha1}/", headers=CRATES_HEADERS)
    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        raise RuntimeError("SWH API rate limit reached - try again later")
    resp.raise_for_status()
    return resp.json()["directory"]


def _compute_scores(match, is_monorepo, swh_archived):
    if is_monorepo:
        # Normalization rules are valid, comparison is out of scope
        return {"reproducibility": 7, "provenance": 7, "normalization": 8, "overall": 7}
    if match is True:
        return {"reproducibility": 10, "provenance": 10, "normalization": 10, "overall": 10}
    if not swh_archived:
        # Rules are known and deterministic; archive coverage is the gap
        return {"reproducibility": 8, "provenance": 3, "normalization": 9, "overall": 7}
    # MISMATCH - normalization did not recover the git tree
    return {"reproducibility": 2, "provenance": 2, "normalization": 2, "overall": 2}


def analyze(name, version, purl=None):
    """
    Download and analyze a crates.io package. Returns a structured findings dict.
    Does not print anything - the caller is responsible for display.
    """
    purl = purl or f"pkg:cargo/{name}@{version}"

    metadata = _fetch_crate_metadata(name, version)

    crate_url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
    source_path, injected = _download_and_extract(crate_url, name, version)

    file_count_before = _count_files(source_path)
    stripped          = _strip_injected(source_path)
    file_count_after  = _count_files(source_path)

    computed      = compute_swhid(source_path)
    computed_str  = str(computed)
    computed_hash = computed_str.split(":")[-1]

    # Parse VCS provenance from the injected manifest
    sha1        = None
    path_in_vcs = ""
    is_monorepo = False
    if ".cargo_vcs_info.json" in injected:
        vcs_info    = json.loads(injected[".cargo_vcs_info.json"])
        sha1        = vcs_info.get("git", {}).get("sha1")
        path_in_vcs = vcs_info.get("path_in_vcs", "")
        is_monorepo = bool(path_in_vcs)

    normalization = {
        "files_stripped":    stripped,
        "file_count_before": file_count_before,
        "file_count_after":  file_count_after,
        "git_sha1":          sha1,
        "path_in_vcs":       path_in_vcs,
        "is_monorepo":       is_monorepo,
    }

    # SWH lookup and comparison
    swh_dir_hash = None
    match        = None
    swh_archived = False

    if sha1 and not is_monorepo:
        swh_dir_hash = _fetch_swh_dir_for_revision(sha1)
        if swh_dir_hash is not None:
            swh_archived = True
            match = (computed_hash == swh_dir_hash)

    swhid_data = {
        "computed": computed_str,
        "from_swh": swh_dir_hash,
        "match":    match,
    }

    # Verdict
    if is_monorepo:
        verdict = "Monorepo crate - comparison skipped"
        explanation = (
            f"This crate is published from a subdirectory ({path_in_vcs}) of a larger "
            "repository. The SWH revision hash points to the repository root, not the "
            "crate subdirectory. Resolving this requires traversing the SWH directory "
            "tree - an extension planned for a future iteration."
        )
    elif match is True:
        verdict = "MATCH - normalization confirmed"
        explanation = (
            "Stripping the 3 registry-injected files (.cargo_vcs_info.json, Cargo.toml, "
            "Cargo.toml.orig) from the .crate artifact recovers the exact git tree "
            "archived by Software Heritage. One PURL -> one stable, verifiable SWHID."
        )
    elif not sha1:
        verdict = "No git sha1 - cannot compare"
        explanation = (
            "The .cargo_vcs_info.json file is absent or missing the git.sha1 field. "
            "Normalization was applied but the result cannot be verified against SWH."
        )
    elif not swh_archived:
        verdict = "Revision not yet archived by Software Heritage"
        explanation = (
            "The git commit recorded in .cargo_vcs_info.json has not been crawled by "
            "Software Heritage yet. The normalization rules are still valid; the SWHID "
            "can be verified once SWH archives the repository."
        )
    else:
        verdict = "MISMATCH - hashes differ"
        explanation = (
            "The computed SWHID does not match the SWH directory hash for this git commit. "
            "Possible causes: additional injected content, file permission differences, "
            "or an undocumented modification in the registry artifact."
        )

    analysis = {
        "verdict":     verdict,
        "explanation": explanation,
        "match":       match,
        "is_monorepo": is_monorepo,
    }

    scores = _compute_scores(match, is_monorepo, swh_archived)

    return {
        "purl":           purl,
        "ecosystem":      "cargo",
        "name":           name,
        "version":        version,
        "metadata":       metadata,
        "injected_files": injected,
        "normalization":  normalization,
        "swhid":          swhid_data,
        "analysis":       analysis,
        "scores":         scores,
    }


if __name__ == "__main__":
    import subprocess, sys as _sys
    _sys.exit(subprocess.call(["python", "analyze.py"] + _sys.argv[1:]))
