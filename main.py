import argparse
import requests
from parser import fetch_package
from calculator import unpack_file, find_source, swhid_generator

def verify_swhid(swhid):
    hash_part = str(swhid).split(":")[-1]
    url = f"https://archive.softwareheritage.org/api/1/directory/{hash_part}/"
    resp = requests.get(url)
    return resp.status_code == 200

parser = argparse.ArgumentParser()
parser.add_argument("package", nargs="?")
parser.add_argument("version", nargs="?")
args = parser.parse_args()

package = args.package or input("Package: ")
version = args.version or input("Version: ")

file_url = fetch_package(package, version)
path = unpack_file(file_url)
source_path = find_source(path)
swhid = swhid_generator(source_path)

print(f"SWHID: {swhid}")
print(f"SWH:   {'FOUND' if verify_swhid(swhid) else 'not found'}")
