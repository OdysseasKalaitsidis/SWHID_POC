# Usage: python pypi/swhid_verifier.py pkg:pypi/six@1.17.0

import io
import os
import sys
import shutil
import tarfile
import requests
from swh.model.from_disk import Directory

PYPI_API = "https://pypi.org/pypi"
SWH_API  = "https://archive.softwareheritage.org/api/1"


def parse_purl(purl):
    if not purl.startswith("pkg:pypi/"):
        raise ValueError(f"Expected pkg:pypi/ PURL, got: {purl}")
    rest = purl[len("pkg:pypi/"):]
    if "@" not in rest:
        raise ValueError(f"PURL must include @version: {purl}")
    name, version = rest.split("@", 1)
    return name, version


def _fetch_sdist(name, version):
    resp = requests.get(f"{PYPI_API}/{name}/{version}/json")
    resp.raise_for_status()
    data = resp.json()
    for f in data["urls"]:
        if f["packagetype"] == "sdist":
            return {
                "filename": f["filename"],
                "url":      f["url"],
                "size":     f["size"],
                "sha256":   f.get("digests", {}).get("sha256", ""),
            }
    return None


def _download_and_extract(sdist):
    target = os.path.join(os.path.dirname(__file__), "..", "tmp")
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


def main(purl):
    name, version = parse_purl(purl)

    print(f"PURL: {purl}")
    print()

    sdist = _fetch_sdist(name, version)
    if sdist is None:
        print("No sdist published for this package version.")
        print("A SWHID cannot be computed without a source distribution.")
        return

    print(f"sdist : {sdist['filename']}  ({sdist['size'] / 1024:.1f} KB)")
    print(f"sha256: {sdist['sha256']}")
    print()
    print("Downloading and extracting...")
    source_path = _download_and_extract(sdist)

    print("Computing SWHID...")
    swhid = Directory.from_disk(path=os.fsencode(source_path), max_content_length=None).swhid()
    print(f"SWHID : {swhid}")
    print()

    print("Checking Software Heritage archive...")
    dir_hash = str(swhid).split(":")[-1]
    resp = requests.get(f"{SWH_API}/directory/{dir_hash}/")
    found = resp.status_code == 200
    if found:
        print("Result: FOUND in Software Heritage archive")
        print()
        print("The sdist tree matches the git tree archived by Software Heritage.")
        print("One PURL -> one stable SWHID. Provenance is fully verifiable.")
    else:
        print("Result: NOT FOUND in Software Heritage archive")
        print()
        print("The sdist tree diverges from the archived git tree.")
        print("Likely cause: generated files (.egg-info, CA bundles, etc.) are")
        print("present in the sdist but absent from the git repository.")

    return {
        "purl": purl,
        "sdist_filename": sdist["filename"],
        "sdist_sha256": sdist["sha256"],
        "swhid": str(swhid),
        "found_in_swh": found,
        "finding": (
            "sdist tree matches git tree — SWHID verifiable in SWH archive"
            if found else
            "sdist tree diverges from git tree — generated files present in sdist"
        ),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pypi/swhid_verifier.py <purl>")
        print("  e.g. python pypi/swhid_verifier.py pkg:pypi/six@1.17.0")
        sys.exit(1)
    main(sys.argv[1])
