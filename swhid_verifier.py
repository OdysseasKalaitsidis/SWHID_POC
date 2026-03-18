"""
swhid_verifier.py — compute a SWHID for a local directory and verify it
                    against the Software Heritage archive.

Usage (standalone):
    python swhid_verifier.py <path/to/directory>
"""

import os
import sys
import requests
from swh.model.from_disk import Directory

SWH_API = "https://archive.softwareheritage.org/api/1"


def compute_swhid(folder_path):
    directory = Directory.from_disk(
        path=os.fsencode(folder_path), max_content_length=None
    )
    return directory.swhid()


def verify_swhid(swhid):
    dir_hash = str(swhid).split(":")[-1]
    resp = requests.get(f"{SWH_API}/directory/{dir_hash}/")
    if resp.status_code == 429:
        raise RuntimeError("SWH API rate limit reached — try again later")
    return resp.status_code == 200


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python swhid_verifier.py <path>")
        sys.exit(1)
    path = sys.argv[1]
    swhid = compute_swhid(path)
    found = verify_swhid(swhid)
    print(f"SWHID: {swhid}")
    print(f"SWH:   {'FOUND' if found else 'not found'}")
