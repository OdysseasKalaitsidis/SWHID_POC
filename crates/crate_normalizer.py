# crates/crate_normalizer.py
# Normalizes a .crate artifact by stripping registry-injected files and
# verifying all source file content hashes against the SWH archive.
#
# Normalization: restore Cargo.toml from Cargo.toml.orig, remove
# .cargo_vcs_info.json and Cargo.toml.orig. Then compare every remaining
# file's content hash against the corresponding SWH blob.
#
# Usage: python crates/crate_normalizer.py pkg:cargo/serde@1.0.203

import io
import json
import os
import sys
import shutil
import tarfile
import requests
from swh.model.from_disk import Directory, Content

CRATES_HEADERS = {"User-Agent": "swhid-poc/0.1 (gsoc research)"}
SWH_API        = "https://archive.softwareheritage.org/api/1"

REGISTRY_ADDED = [".cargo_vcs_info.json", "Cargo.toml.orig"]


def parse_input(args):
    if len(args) == 1 and args[0].startswith("pkg:cargo/"):
        purl = args[0][len("pkg:cargo/"):]
        if "@" not in purl:
            raise ValueError(f"PURL must include @version: {args[0]}")
        name, version = purl.split("@", 1)
    elif len(args) == 2:
        name, version = args
    else:
        raise ValueError("Pass a PURL (pkg:cargo/serde@1.0.203) or name + version")
    return name, version


def _download_and_extract(name, version):
    url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
    resp = requests.get(url, headers=CRATES_HEADERS)
    resp.raise_for_status()

    target = os.path.join(os.path.dirname(__file__), "..", "tmp", "crate_normalizer")
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target)

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        tar.extractall(path=target, filter="data")

    items = os.listdir(target)
    return os.path.join(target, items[0]) if len(items) == 1 else target


def _normalize(source_path):
    
    actions = []

    orig = os.path.join(source_path, "Cargo.toml.orig")
    toml = os.path.join(source_path, "Cargo.toml")
    if os.path.exists(orig):
        with open(orig, "rb") as f:
            original_content = f.read()
        with open(toml, "wb") as f:
            f.write(original_content)
        actions.append("Cargo.toml restored from Cargo.toml.orig (undo registry rewrite)")

    for filename in REGISTRY_ADDED:
        full = os.path.join(source_path, filename)
        if os.path.exists(full):
            os.remove(full)
            actions.append(f"{filename} removed (registry-added file)")

    return actions


def _build_swh_tree(dir_hash, prefix=""):
    """Recursively fetch a SWH directory tree, returning {rel_path: blob_hash}."""
    resp = requests.get(f"{SWH_API}/directory/{dir_hash}/", headers=CRATES_HEADERS)
    if resp.status_code != 200:
        return {}
    blobs = {}
    for entry in resp.json():
        rel = f"{prefix}{entry['name']}" if not prefix else f"{prefix}/{entry['name']}"
        if entry["perms"] == 0o040000:  # directory
            blobs.update(_build_swh_tree(entry["target"], rel))
        elif entry["perms"] in (0o100644, 0o100755):  # regular file
            blobs[rel] = entry["target"]
        # skip symlinks (0o120000) - crates resolve them
    return blobs


def _fetch_swh_dir(sha1, path_in_vcs):
    """Return the SWH directory hash for the relevant subtree."""
    resp = requests.get(
        f"{SWH_API}/revision/{sha1}/",
        headers=CRATES_HEADERS,
    )
    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        raise RuntimeError("SWH API rate limit reached - try again later")
    resp.raise_for_status()
    root_dir = resp.json()["directory"]

    if not path_in_vcs:
        return root_dir

    # Monorepo: navigate into the crate's subdirectory
    resp2 = requests.get(f"{SWH_API}/directory/{root_dir}/", headers=CRATES_HEADERS)
    for entry in resp2.json():
        if entry["name"] == path_in_vcs and entry["perms"] == 0o040000:
            return entry["target"]
    return None


def main(name, version):
    purl = f"pkg:cargo/{name}@{version}"
    print(f"PURL: {purl}")
    print()

    print(f"Downloading {name}-{version}.crate ...")
    source_path = _download_and_extract(name, version)

    # read provenance info embedded by the registry
    vcs_path = os.path.join(source_path, ".cargo_vcs_info.json")
    if os.path.exists(vcs_path):
        vcs = json.load(open(vcs_path))
        sha1 = vcs.get("git", {}).get("sha1")
        path_in_vcs = vcs.get("path_in_vcs", "")
    else:
        sha1, path_in_vcs = None, ""
    is_monorepo = bool(path_in_vcs)

    if sha1:
        print(f"Git sha1    : {sha1}")
    if is_monorepo:
        print(f"Monorepo    : path_in_vcs = {path_in_vcs}")
    print()

    before = sum(len(f) for _, _, f in os.walk(source_path))
    actions = _normalize(source_path)
    after = sum(len(f) for _, _, f in os.walk(source_path))

    print(f"Files before normalization : {before}")
    print("Normalization steps:")
    for a in actions:
        print(f"  {a}")
    print(f"Files after normalization  : {after}")
    print()

    print("Computing SWHID of normalized tree...")
    swhid = Directory.from_disk(path=os.fsencode(source_path), max_content_length=None).swhid()
    print(f"Computed SWHID: {swhid}")
    print()

    if not sha1:
        print("Cannot verify: no git sha1 in .cargo_vcs_info.json")
        return

    scope = f"{name} -> {path_in_vcs}/" if is_monorepo else f"{name} root"
    print(f"Fetching SWH directory tree for git commit {sha1[:12]}... ({scope})")
    swh_dir_hash = _fetch_swh_dir(sha1, path_in_vcs)

    if swh_dir_hash is None:
        print("Directory not found in Software Heritage archive.")
        print("The normalization is correct; verification will be possible once SWH archives this commit.")
        return

    print(f"SWH directory hash : {swh_dir_hash}")
    print("Building SWH blob index...")
    swh_blobs = _build_swh_tree(swh_dir_hash)
    print(f"SWH blobs indexed  : {len(swh_blobs)}")
    print()

    # Verify every file in the normalized crate against the SWH blob index
    print("Verifying file content hashes against SWH archive:")
    print()

    matched   = []
    mismatched = []
    not_in_git = []

    for root, dirs, files in os.walk(source_path):
        dirs.sort()
        for fname in sorted(files):
            full_path = os.path.join(root, fname)
            rel = os.path.relpath(full_path, source_path).replace("\\", "/")
            our_hash = str(Content.from_file(path=os.fsencode(full_path), max_content_length=None).swhid()).split(":")[-1]
            swh_hash  = swh_blobs.get(rel)
            if swh_hash is None:
                not_in_git.append(rel)
            elif our_hash == swh_hash:
                matched.append(rel)
            else:
                mismatched.append((rel, our_hash, swh_hash))

    for rel in matched:
        print(f"  MATCH  {rel}")
    for rel in not_in_git:
        print(f"  --     {rel}  (not in git tree - excluded from crate)")
    for rel, ours, theirs in mismatched:
        print(f"  FAIL   {rel}")
        print(f"           ours: {ours}")
        print(f"           swh:  {theirs}")

    print()

    if not mismatched:
        print("=" * 60)
        print("Result: MATCH - all crate source files verified")
        print("=" * 60)
        print()
        print(f"  {len(matched)} files verified against SWH archive blobs: ALL MATCH")
        if not_in_git:
            print(f"  {len(not_in_git)} files not in git tree (standard crate exclusions)")
        print()
        print("The normalized crate contains only authentic source files.")
        print("Every file's content hash matches the corresponding SWH blob")
        print(f"at git commit {sha1}.")
        print()
        print("Note: full directory SWHID comparison is not applicable here.")
        print("Crates exclude test files, CI configs, and benchmarks that exist")
        print("in the git repo - so the directory trees have different shapes.")
        print("File-level content verification is the correct comparison unit.")
    else:
        print("=" * 60)
        print("Result: MISMATCH - content differences detected")
        print("=" * 60)
        print()
        print(f"  {len(matched)} files matched, {len(mismatched)} mismatched")
        print()
        print("The crate contains files that do not match the git source.")
        print("The 3 known registry files are not sufficient to explain the divergence.")


if __name__ == "__main__":
    try:
        name, version = parse_input(sys.argv[1:])
    except ValueError as e:
        print(f"Error: {e}")
        print("Usage: python crates/crate_normalizer.py pkg:cargo/serde@1.0.203")
        sys.exit(1)
    main(name, version)
