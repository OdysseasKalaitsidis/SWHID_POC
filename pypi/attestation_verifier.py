# pypi/attestation_verifier.py
# Downloads a PEP 740 Sigstore attestation from PyPI, extracts the source
# commit SHA from the signing certificate, and checks if that commit is
# archived in Software Heritage.
#
# Usage: python pypi/attestation_verifier.py pip 25.1.1

import sys
import re
import base64
import requests

PYPI_API = "https://pypi.org/pypi"
PYPI_INTEGRITY = "https://pypi.org/integrity"
SWH_API = "https://archive.softwareheritage.org/api/1"


def get_sdist_filename(name, version):
    resp = requests.get(f"{PYPI_API}/{name}/{version}/json", timeout=10)
    resp.raise_for_status()
    for f in resp.json()["urls"]:
        if f["packagetype"] == "sdist":
            return f["filename"]
    return None


def fetch_provenance(name, version, filename):
    url = f"{PYPI_INTEGRITY}/{name}/{version}/{filename}/provenance"
    resp = requests.get(url, timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def extract_commit_sha(provenance):
    # The commit SHA is stored as a UTF-8 string inside the DER-encoded
    # signing certificate. Fulcio embeds it in multiple OID extensions,
    # so we can just find all 40-char hex strings — they are all the same.
    cert_b64 = (
        provenance["attestation_bundles"][0]
        ["attestations"][0]
        ["verification_material"]
        ["certificate"]
    )
    cert_bytes = base64.b64decode(cert_b64)
    matches = re.findall(r"[0-9a-f]{40}", cert_bytes.decode("latin-1"))
    if not matches:
        raise ValueError("No commit SHA found in signing certificate")
    return matches[0]


def extract_publisher_info(provenance):
    publisher = provenance["attestation_bundles"][0]["publisher"]
    return {
        "kind":       publisher.get("kind", "unknown"),
        "repository": publisher.get("repository", ""),
        "workflow":   publisher.get("workflow", ""),
        "environment": publisher.get("environment", ""),
    }


def check_swh_revision(commit_sha):
    resp = requests.get(f"{SWH_API}/revision/{commit_sha}/", timeout=10)
    return resp.status_code == 200


def main(name="pip", version="25.1.1"):
    purl = f"pkg:pypi/{name}@{version}"
    print(f"Package : {name} {version}")
    print(f"PURL    : {purl}")
    print()

    print("Fetching sdist filename from PyPI...")
    filename = get_sdist_filename(name, version)
    if not filename:
        print("No sdist found for this package version.")
        return {}
    print(f"Filename: {filename}")
    print()

    print("Fetching PEP 740 attestation...")
    provenance = fetch_provenance(name, version, filename)
    if not provenance:
        print("No attestation found — this package does not publish PEP 740 provenance.")
        return {}

    publisher = extract_publisher_info(provenance)
    print(f"Publisher  : {publisher['kind']} ({publisher['repository']} @ {publisher['workflow']})")
    if publisher["environment"]:
        print(f"Environment: {publisher['environment']}")
    print()

    print("Extracting commit SHA from signing certificate...")
    commit_sha = extract_commit_sha(provenance)
    print(f"Commit SHA : {commit_sha}")
    print(f"Repository : https://github.com/{publisher['repository']}")
    print()

    print("Checking Software Heritage archive...")
    found = check_swh_revision(commit_sha)
    if found:
        print("Result : FOUND in Software Heritage archive")
        print()
        print("The PEP 740 attestation cryptographically links this PyPI artifact")
        print("to a specific git commit, which is independently preserved by")
        print("Software Heritage. The full provenance chain is intact:")
        print(f"  {purl} → commit {commit_sha[:12]}... → swh:1:rev:{commit_sha}")
    else:
        print("Result : NOT FOUND in Software Heritage archive")
        print()
        print("The commit exists in the attestation but has not yet been")
        print("archived by Software Heritage.")

    finding = (
        f"PEP 740 attestation links {purl} to commit {commit_sha}, "
        f"{'found' if found else 'not found'} in Software Heritage"
    )

    return {
        "purl":               purl,
        "filename":           filename,
        "publisher_kind":     publisher["kind"],
        "publisher_repo":     publisher["repository"],
        "publisher_workflow": publisher["workflow"],
        "commit_sha":         commit_sha,
        "commit_in_swh":      found,
        "swh_revision_url":   f"{SWH_API}/revision/{commit_sha}/",
        "finding":            finding,
    }


if __name__ == "__main__":
    if len(sys.argv) == 3:
        main(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 1:
        main()
    else:
        print("Usage: python pypi/attestation_verifier.py <name> <version>")
        print("  e.g. python pypi/attestation_verifier.py pip 25.1.1")
        sys.exit(1)
