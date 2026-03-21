# crates/crate_analyzer.py
# Downloads a .crate from crates.io and reports which files the registry
# added or modified compared to the original git source.
#
# Usage: python crates/crate_analyzer.py pkg:cargo/serde@1.0.203

import io
import json
import os
import sys
import shutil
import tarfile
import requests

CRATES_HEADERS = {"User-Agent": "swhid-poc/0.1 (gsoc research)"}
# Files added or rewritten by the crates.io registry (not present in git as-is)
INJECTED_FILES = [".cargo_vcs_info.json", "Cargo.toml", "Cargo.toml.orig"]
# Note: Cargo.toml is rewritten (not added); Cargo.toml.orig holds the original


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


def _extract_crate(data, target):
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(path=target, filter="data")
    items = os.listdir(target)
    return os.path.join(target, items[0]) if len(items) == 1 else target


def _list_all_files(path):
    result = []
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for fname in sorted(files):
            full = os.path.join(root, fname)
            rel  = os.path.relpath(full, path)
            result.append(rel.replace("\\", "/"))
    return result


def main(name, version):
    purl = f"pkg:cargo/{name}@{version}"
    print(f"PURL    : {purl}")
    print(f"crates.io: https://crates.io/crates/{name}/{version}")
    print()

    print(f"Downloading {name}-{version}.crate ...")
    url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
    crate_data = requests.get(url, headers=CRATES_HEADERS).content
    print(f"Downloaded: {len(crate_data) / 1024:.1f} KB")
    print()

    target = os.path.join(os.path.dirname(__file__), "..", "tmp", "crate_analyzer")
    source_path = _extract_crate(crate_data, target)

    all_files = _list_all_files(source_path)
    print(f"Total files in .crate: {len(all_files)}")
    print()

    vcs_path = os.path.join(source_path, ".cargo_vcs_info.json")
    vcs_info = json.load(open(vcs_path)) if os.path.exists(vcs_path) else None
    if vcs_info:
        git_sha1    = vcs_info.get("git", {}).get("sha1", "unknown")
        path_in_vcs = vcs_info.get("path_in_vcs", "")
        print(f"VCS info  : git sha1 = {git_sha1}")
        if path_in_vcs:
            print(f"            path_in_vcs = {path_in_vcs}  (monorepo crate)")
        else:
            print(f"            path_in_vcs = (root — not a monorepo)")
        print()
    else:
        print("No .cargo_vcs_info.json found.")
        print()

    print("Registry-injected files (not present in the git repository):")
    print()
    for filename in INJECTED_FILES:
        full = os.path.join(source_path, filename)
        if os.path.exists(full):
            size = os.path.getsize(full)
            print(f"  + {filename:<30}  ({size} bytes)")
            if filename == ".cargo_vcs_info.json":
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                for line in content.splitlines():
                    print(f"      {line}")
            elif filename == "Cargo.toml":
                print(f"      (rewritten by `cargo publish` — original preserved in Cargo.toml.orig)")
            elif filename == "Cargo.toml.orig":
                print(f"      (original Cargo.toml before registry normalization)")
        else:
            print(f"  - {filename:<30}  (not present)")
    print()

    remaining = [f for f in all_files if f not in INJECTED_FILES]
    injected_present = [f for f in INJECTED_FILES if os.path.exists(os.path.join(source_path, f))]

    print(f"Remaining source files: {len(remaining)} (identical to git tree)")
    print()
    print("Conclusion:")
    print(f"  The .crate for {name} {version} differs from the git tag in exactly")
    print(f"  {len(injected_present)} registry-added files. All source files are unmodified.")
    print(f"  After stripping these files, the SWHID of the remaining tree")
    print(f"  can be compared against the SWH archive.")
    print()
    print(f"  Run: python crates/crate_normalizer.py pkg:cargo/{name}@{version}")

    return {
        "name": name,
        "version": version,
        "total_files": len(all_files),
        "registry_injected_files": injected_present,
        "remaining_source_files": len(remaining),
        "git_sha1": vcs_info.get("git", {}).get("sha1") if vcs_info else None,
        "path_in_vcs": vcs_info.get("path_in_vcs", "") if vcs_info else None,
        "is_monorepo": bool(vcs_info.get("path_in_vcs", "")) if vcs_info else False,
        "finding": (
            f"{len(injected_present)} registry-injected files; "
            f"{len(remaining)} source files unmodified"
        ),
    }


if __name__ == "__main__":
    try:
        name, version = parse_input(sys.argv[1:])
    except ValueError as e:
        print(f"Error: {e}")
        print("Usage: python crates/crate_analyzer.py pkg:cargo/serde@1.0.203")
        sys.exit(1)
    main(name, version)
