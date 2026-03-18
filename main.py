import argparse
import json
import requests
from parser import fetch_package, fetch_crate, list_wheels
from calculator import unpack_file, unpack_wheel, unpack_crate, strip_cargo_injected_files, find_source, swhid_generator
from swh_api import fetch_directory_hash_for_revision, verify_directory

def verify_swhid(swhid):
    hash_part = str(swhid).split(":")[-1]
    resp = requests.get(f"https://archive.softwareheritage.org/api/1/directory/{hash_part}/")
    return resp.status_code == 200

def parse_purl(purl):
    for prefix, ecosystem in [("pkg:pypi/", "pypi"), ("pkg:cargo/", "cargo")]:
        if purl.startswith(prefix):
            rest = purl[len(prefix):]
            if "@" not in rest:
                raise ValueError(f"PURL must include a version (@version), got: {purl}")
            name, version = rest.split("@", 1)
            return ecosystem, name, version
    raise ValueError(f"Unsupported PURL ecosystem: {purl}")

def print_wheels_table(wheels, package, version):
    if not wheels:
        print(f"No wheels found for {package} {version}.")
        return
    sizes = [f"{w['size'] // 1024:,} KB" for w in wheels]
    col_f = max(len(w['filename']) for w in wheels)
    col_s = max(len(s) for s in sizes)
    col_p = max(len(w['python'])   for w in wheels)
    col_a = max(len(w['abi'])      for w in wheels)
    col_t = max(len(w['platform']) for w in wheels)
    print(f"\nWheels for {package} {version} ({len(wheels)} found):")
    print(f"  {'Filename':<{col_f}}  {'Size':>{col_s}}  {'Python':<{col_p}}  {'ABI':<{col_a}}  Platform")
    print(f"  {'-'*col_f}  {'-'*col_s}  {'-'*col_p}  {'-'*col_a}  {'-'*col_t}")
    for w, size_kb in zip(wheels, sizes):
        print(f"  {w['filename']:<{col_f}}  {size_kb:>{col_s}}  {w['python']:<{col_p}}  {w['abi']:<{col_a}}  {w['platform']}")

def process_wheels(wheels):
    print()
    for w in wheels:
        path = unpack_wheel(w['url'], w['filename'])
        swhid = swhid_generator(path)
        found = verify_swhid(swhid)
        print(f"  {w['filename']}")
        print(f"    SWHID: {swhid}")
        print(f"    SWH:   {'FOUND' if found else 'not found'}")

def process_cargo(name, version):
    print(f"\nCrate: {name} {version}")

    crate_url = fetch_crate(name, version)
    source_path, injected = unpack_crate(crate_url, name, version)

    # --- show injected files ---
    print("\nRegistry-injected files (will be stripped):")
    for filename in [".cargo_vcs_info.json", "Cargo.toml", "Cargo.toml.orig"]:
        if filename not in injected:
            continue
        lines = injected[filename].splitlines()
        preview = "\n    ".join(lines[:5])
        suffix = "\n    [...]" if len(lines) > 5 else ""
        print(f"\n  {filename}:\n    {preview}{suffix}")

    # --- strip ---
    removed = strip_cargo_injected_files(source_path)
    print(f"\nStripping injected files: {', '.join(removed)}")

    # --- compute SWHID on stripped tree ---
    computed_swhid = swhid_generator(source_path)
    computed_hash = str(computed_swhid).split(":")[-1]
    print(f"\nComputed SWHID (stripped tree):\n  {computed_swhid}")

    # --- SWH git lookup ---
    if ".cargo_vcs_info.json" not in injected:
        print("\nNo .cargo_vcs_info.json found — cannot retrieve git sha1 for SWH comparison.")
        return

    vcs_info = json.loads(injected[".cargo_vcs_info.json"])
    sha1 = vcs_info.get("git", {}).get("sha1")
    path_in_vcs = vcs_info.get("path_in_vcs", "")

    if not sha1:
        print("\nNo git sha1 in .cargo_vcs_info.json — cannot compare.")
        return

    if path_in_vcs:
        print(f"\nNote: path_in_vcs is '{path_in_vcs}' — crate is from a monorepo subdirectory.")
        print("      SWH revision points to the repo root; skipping comparison.")
        return

    print(f"\nSWH lookup for git commit {sha1}:")
    swh_dir_hash = fetch_directory_hash_for_revision(sha1)
    if swh_dir_hash is None:
        print(f"  Revision not yet archived by Software Heritage.")
        print(f"  Computed SWHID: {computed_swhid}")
        print(f"  Cannot verify normalization without SWH archive entry.")
        return

    print(f"  Directory hash: {swh_dir_hash}")

    # --- compare ---
    print()
    if computed_hash == swh_dir_hash:
        print("Result: MATCH — normalization confirmed.")
    else:
        print("Result: MISMATCH")
        print(f"  Computed: {computed_swhid}")
        print(f"  SWH:      swh:1:dir:{swh_dir_hash}")

# --- resolve ecosystem + package + version ---
arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("package", nargs="?")
arg_parser.add_argument("version", nargs="?")
arg_parser.add_argument("--purl", help="Package URL, e.g. pkg:pypi/six@1.17.0 or pkg:cargo/serde@1.0.203")
args = arg_parser.parse_args()

if args.purl:
    ecosystem, package, version = parse_purl(args.purl)
else:
    raw = args.package or input("Package or PURL: ")
    if raw.startswith("pkg:"):
        ecosystem, package, version = parse_purl(raw)
    else:
        ecosystem = "pypi"
        package = raw
        version = args.version or input("Version: ")

# --- dispatch by ecosystem ---
if ecosystem == "cargo":
    process_cargo(package, version)

else:  # pypi
    wheels = list_wheels(package, version)
    print_wheels_table(wheels, package, version)
    print()

    try:
        file_url = fetch_package(package, version)
        path = unpack_file(file_url)
        source_path = find_source(path)
        swhid = swhid_generator(source_path)
        print(f"SWHID: {swhid}")
        print(f"SWH:   {'FOUND' if verify_swhid(swhid) else 'not found'}")

    except ValueError as e:
        print(f"Note: {e}")
        print("Computing SWHIDs from wheels instead:")
        process_wheels(wheels)
