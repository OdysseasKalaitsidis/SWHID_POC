# Usage: python pypi/wheel_enumerator.py pkg:pypi/torch@2.6.0

import sys
import requests

PYPI_API = "https://pypi.org/pypi"


def parse_purl(purl):
    if not purl.startswith("pkg:pypi/"):
        raise ValueError(f"Expected pkg:pypi/ PURL, got: {purl}")
    rest = purl[len("pkg:pypi/"):]
    if "@" not in rest:
        raise ValueError(f"PURL must include @version: {purl}")
    name, version = rest.split("@", 1)
    return name, version


def enumerate_artifacts(name, version):
    resp = requests.get(f"{PYPI_API}/{name}/{version}/json")
    resp.raise_for_status()
    data = resp.json()

    sdists = []
    wheels = []

    for f in data["urls"]:
        size_mb = f["size"] / (1024 * 1024)
        entry = {
            "filename": f["filename"],
            "size": f["size"],
            "size_mb": size_mb,
            "url": f["url"],
            "sha256": f.get("digests", {}).get("sha256", ""),
        }
        if f["packagetype"] == "sdist":
            sdists.append(entry)
        elif f["packagetype"] == "bdist_wheel":
            parts = f["filename"][:-4].split("-")
            entry["python"] = parts[2] if len(parts) > 2 else "?"
            entry["abi"] = parts[3] if len(parts) > 3 else "?"
            entry["platform"] = parts[4] if len(parts) > 4 else "?"
            wheels.append(entry)

    return sdists, wheels


def main(purl):
    name, version = parse_purl(purl)

    print(f"PURL: {purl}")
    print(f"PyPI: https://pypi.org/project/{name}/{version}/")
    print()

    sdists, wheels = enumerate_artifacts(name, version)

    print(f"sdists : {len(sdists)}")
    print(f"wheels : {len(wheels)}")
    print()

    if sdists:
        print("Source distributions:")
        for s in sdists:
            print(f"  {s['filename']:<60}  {s['size_mb']:>7.1f} MB")
        print()

    if wheels:
        print("Wheels:")
        for w in wheels:
            print(f"  {w['filename']:<80}  {w['size_mb']:>7.1f} MB  "
                  f"python={w['python']}  abi={w['abi']}  platform={w['platform']}")
    else:
        print("No wheels published.")

    if not sdists:
        print()
        print(f"Finding: 0 sdists, {len(wheels)} wheels.")
        print("A SWHID cannot be computed — there is no source artifact.")
        print("One PURL maps to many platform-specific binary artifacts.")

    return {
        "purl": purl,
        "sdist_count": len(sdists),
        "wheel_count": len(wheels),
        "sdists": [{"filename": s["filename"], "sha256": s["sha256"]} for s in sdists],
        "finding": (
            f"wheel-only: {len(wheels)} platform wheels, no sdist — SWHID not possible"
            if not sdists else f"{len(sdists)} sdist(s), {len(wheels)} wheel(s)"
        ),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python pypi/wheel_enumerator.py <purl>")
        print("  e.g. python pypi/wheel_enumerator.py pkg:pypi/torch@2.6.0")
        sys.exit(1)
    main(sys.argv[1])
