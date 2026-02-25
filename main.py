import argparse
import requests
from parser import fetch_package
from calculator import unpack_file, find_source, swhid_generator

def verify_swhid(swhid):
    hash_part = str(swhid).split(":")[-1]
    url = f"https://archive.softwareheritage.org/api/1/directory/{hash_part}/"
    resp = requests.get(url)
    return resp.status_code == 200

def run(package, version):
    print(f"\n--- {package} {version} ---")

    file_url = fetch_package(package, version)
    path = unpack_file(file_url)

    inner_path = find_source(path)
    outer_path = path

    inner_swhid = swhid_generator(inner_path)
    outer_swhid = swhid_generator(outer_path)

    print(f"Inner dir ({inner_path}): {inner_swhid}")
    print(f"  -> SWH: {'FOUND' if verify_swhid(inner_swhid) else 'not found'}")

    print(f"Outer dir ({outer_path}): {outer_swhid}")
    print(f"  -> SWH: {'FOUND' if verify_swhid(outer_swhid) else 'not found'}")

parser = argparse.ArgumentParser(description="Compute and verify SWHID for a PyPI package")
parser.add_argument("package", nargs="?", default=None)
parser.add_argument("version", nargs="?", default=None)
args = parser.parse_args()

if args.package and args.version:
    run(args.package, args.version)
else:
    # Test suite of small packages
    packages = [
        ("six", "1.17.0"),
        ("certifi", "2024.12.14"),
        ("charset-normalizer", "3.4.1"),
    ]
    for pkg, ver in packages:
        run(pkg, ver)
