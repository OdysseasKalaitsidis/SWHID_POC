import requests
from parser import fetch_package
from calculator import unpack_file, find_source, swhid_generator

def verify_swhid(swhid):
    hash_part = str(swhid).split(":")[-1]
    url = f"https://archive.softwareheritage.org/api/1/directory/{hash_part}/"
    resp = requests.get(url)
    return resp.status_code == 200

file_url = fetch_package("numpy", "2.2.0")
path = unpack_file(file_url)
c_path = find_source(path)
id = swhid_generator(c_path)
print(id)

if verify_swhid(id):
    print("Found in Software Heritage archive")
else:
    print("Not found in archive")