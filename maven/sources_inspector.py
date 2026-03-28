import hashlib
import io
import os
import re
import zipfile
import requests
import xml.etree.ElementTree as ET
from collections import defaultdict

TARGET = "com.fasterxml.jackson.core:jackson-databind:2.17.0"
MAVEN_CENTRAL = "https://repo1.maven.org/maven2"
GITHUB_API = "https://api.github.com"
SWH_API = "https://archive.softwareheritage.org/api/1"
NS = "http://maven.apache.org/POM/4.0.0"

FINDINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "findings")


def coords_to_base_url(coords):
    group_id, artifact_id, version = coords.split(":")
    group_path = group_id.replace(".", "/")
    return f"{MAVEN_CENTRAL}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}"


def fetch_pom(base_url):
    resp = requests.get(base_url + ".pom", timeout=10)
    if resp.status_code == 200:
        return resp.text
    return None


def parse_scm_details(pom_text):
    root = ET.fromstring(pom_text)

    def find(element, tag):
        node = element.find(f"{{{NS}}}{tag}")
        if node is None:
            node = element.find(tag)
        return node

    scm = find(root, "scm")
    if scm is None:
        return {}

    def text(tag):
        node = find(scm, tag)
        return (node.text or "").strip() if node is not None else ""

    return {"url": text("url"), "connection": text("connection"), "tag": text("tag")}


def download_sources_jar(base_url):
    resp = requests.get(base_url + "-sources.jar", timeout=30)
    resp.raise_for_status()
    return zipfile.ZipFile(io.BytesIO(resp.content))


def inventory_jar(zf):
    by_ext = defaultdict(list)
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        ext = os.path.splitext(name)[1].lower() or "(no ext)"
        by_ext[ext].append(name)
    return dict(by_ext)


def extract_github_owner_repo(url):
    m = re.search(r"github\.com/([^/]+)/([^/\s]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2)
    return None, None


def fetch_git_tree(owner, repo, tag):
    for ref in [tag, f"v{tag}"]:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"
        resp = requests.get(url, timeout=15, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code == 200:
            data = resp.json()
            return {e["path"]: e["sha"] for e in data.get("tree", []) if e["type"] == "blob"}
    return None


def strip_src_prefix(path):
    for prefix in ["src/main/java/", "src/test/java/", "src/main/resources/", "src/test/resources/"]:
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def git_blob_sha1(data):
    # Git and SWH both hash blobs as sha1("blob {len}\0{content}")
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def verify_content_overlap(zf, overlap_files, git_java_shas):
    sorted_files = sorted(overlap_files)

    results = []
    swh_checked = False  # only do one SWH API call

    for path in sorted_files:
        jar_bytes = zf.read(path)
        jar_sha = git_blob_sha1(jar_bytes)
        git_sha = git_java_shas[path]

        if jar_sha == git_sha:
            status = "BYTE_IDENTICAL"
            note = ""
            if not swh_checked:
                swh_resp = requests.get(f"{SWH_API}/content/sha1_git:{jar_sha}/", timeout=10)
                swh_found = swh_resp.status_code == 200
                swh_checked = True
                note = f"verified in SWH archive: {'YES' if swh_found else 'NOT FOUND'}"
        else:
            normalised = jar_bytes.replace(b"\r\n", b"\n")
            if git_blob_sha1(normalised) == git_sha:
                status = "LINE_ENDING_DIFF"
                note = "jar has CRLF, git has LF"
            else:
                status = "CONTENT_DIFFERS"
                note = "content genuinely different"

        results.append({
            "file": path,
            "jar_sha1": jar_sha,
            "git_sha1": git_sha,
            "status": status,
            "note": note,
            "jar_size_bytes": len(jar_bytes),
        })

    return results


def write_findings_txt(coords, scm, inventory, git_total, only_in_jar, only_in_git,
                       in_both, content_results):
    _, artifact_id, version = coords.split(":")
    filename = f"{artifact_id}_{version}_sources_inspection.txt"
    path = os.path.join(FINDINGS_DIR, filename)

    total = sum(len(v) for v in inventory.values())
    java_count = len(inventory.get(".java", []))
    other_files = sorted(
        f for ext, files in inventory.items() if ext != ".java" for f in files
    )

    lines = []
    lines.append(f"Package : {coords}")
    lines.append(f"SCM tag : {scm.get('tag', 'n/a')}")
    lines.append(f"SCM url : {scm.get('url', 'n/a')}")
    lines.append("")
    lines.append("sources.jar contents:")
    lines.append(f"  Total entries : {total}")
    lines.append(f"  .java files   : {java_count}")
    for ext, files in sorted(inventory.items()):
        if ext != ".java":
            lines.append(f"  {ext:20}: {len(files)}")
    lines.append("")
    lines.append("Non-.java files in sources.jar:")
    for f in other_files:
        lines.append(f"  {f}")
    lines.append("")
    lines.append(f"Git tree total files (tag {scm.get('tag', '?')}): {git_total}")
    lines.append("")
    lines.append(f"Files only in sources.jar (not in git): {len(only_in_jar)}")
    for f in only_in_jar[:40]:
        lines.append(f"  + {f}")
    if len(only_in_jar) > 40:
        lines.append(f"  ... and {len(only_in_jar) - 40} more")
    lines.append("")
    lines.append(f"Files only in git (not in sources.jar): {len(only_in_git)}")
    for f in only_in_git[:40]:
        lines.append(f"  - {f}")
    if len(only_in_git) > 40:
        lines.append(f"  ... and {len(only_in_git) - 40} more")
    lines.append("")
    lines.append(f"Files in both: {in_both}")
    lines.append("Note: git paths have src/main/java/ prefix stripped before comparison.")
    lines.append("")

    if content_results:
        byte_identical = sum(1 for r in content_results if r["status"] == "BYTE_IDENTICAL")
        lines.append(f"Content verification — checked all {len(content_results)} files from {in_both} overlapping:")
        lines.append("")
        for r in content_results:
            lines.append(f"  {r['file']}")
            lines.append(f"    jar SHA1 : {r['jar_sha1']}")
            lines.append(f"    git SHA1 : {r['git_sha1']}")
            status_str = {
                "BYTE_IDENTICAL": "BYTE-IDENTICAL",
                "LINE_ENDING_DIFF": "LINE ENDING DIFF (CRLF vs LF)",
                "CONTENT_DIFFERS": "CONTENT DIFFERS",
            }.get(r["status"], r["status"])
            line = f"    result   : {status_str}"
            if r["note"]:
                line += f"  ({r['note']})"
            lines.append(line)
            lines.append("")
        lines.append(f"Summary: {byte_identical}/{len(content_results)} files are byte-identical to git.")
        if byte_identical == len(content_results):
            lines.append("All content SWHIDs (swh:1:cnt:{sha1}) will match the archive.")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"  -> written: findings/{filename}")


def main():
    coords = TARGET

    print(f"Package : {coords}")
    print()

    base_url = coords_to_base_url(coords)

    print("Fetching POM...")
    pom_text = fetch_pom(base_url)
    if not pom_text:
        print("ERROR: could not fetch POM")
        return {}

    scm = parse_scm_details(pom_text)
    print(f"  scm.url : {scm.get('url', 'n/a')}")
    print(f"  scm.tag : {scm.get('tag', 'n/a')}")
    print()

    print("Downloading -sources.jar ...")
    zf = download_sources_jar(base_url)
    print(f"  entries in zip : {len(zf.namelist())}")
    print()

    print("Inventorying jar contents...")
    inventory = inventory_jar(zf)
    total = sum(len(v) for v in inventory.values())
    for ext, files in sorted(inventory.items(), key=lambda x: -len(x[1])):
        print(f"  {ext:20}: {len(files):4d} files")
    print(f"  {'TOTAL':20}: {total:4d} files")
    print()

    owner, repo = extract_github_owner_repo(scm.get("url", ""))
    tag = scm.get("tag", "")

    git_total = -1
    only_in_jar, only_in_git, in_both = [], [], 0
    content_results = []
    git_java_shas = {}

    if owner and tag:
        print(f"Fetching git tree: github.com/{owner}/{repo} @ {tag} ...")
        git_tree = fetch_git_tree(owner, repo, tag)

        if git_tree is not None:
            git_total = len(git_tree)

            git_java_shas = {
                strip_src_prefix(p): sha
                for p, sha in git_tree.items()
                if p.endswith(".java")
            }
            jar_java = set(inventory.get(".java", []))

            overlap = jar_java & set(git_java_shas.keys())
            only_in_jar = sorted(jar_java - set(git_java_shas.keys()))
            only_in_git = sorted(set(git_java_shas.keys()) - jar_java)
            in_both = len(overlap)

            print(f"  git total files  : {git_total}")
            print(f"  git .java files  : {len(git_java_shas)}  (after stripping src/ prefix)")
            print(f"  jar .java files  : {len(jar_java)}")
            print(f"  only in jar      : {len(only_in_jar)}")
            print(f"  only in git      : {len(only_in_git)}")
            print(f"  in both          : {in_both}")
            print()

            if overlap:
                print(f"Content verification — checking all {in_both} overlapping files...")
                content_results = verify_content_overlap(zf, overlap, git_java_shas)
                print()
                byte_identical = sum(1 for r in content_results if r["status"] == "BYTE_IDENTICAL")
                for r in content_results:
                    icon = "=" if r["status"] == "BYTE_IDENTICAL" else "!" if r["status"] == "LINE_ENDING_DIFF" else "X"
                    note = f"  ({r['note']})" if r["note"] else ""
                    print(f"  [{icon}] {r['file']}")
                    if r["status"] == "BYTE_IDENTICAL":
                        print(f"        SHA1: {r['jar_sha1']}{note}")
                    else:
                        print(f"        jar SHA1: {r['jar_sha1']}")
                        print(f"        git SHA1: {r['git_sha1']}")
                        print(f"        {note}")
                print()
                print(f"  {byte_identical}/{len(content_results)} files byte-identical to git")
                if byte_identical == len(content_results):
                    print("  All content SWHIDs (swh:1:cnt:<sha1>) will match the archive.")
        else:
            print("  WARNING: tag not found on GitHub — skipping tree comparison")
        print()

    other_files = sorted(
        f for ext, files in inventory.items() if ext != ".java" for f in files
    )
    if other_files:
        print("Non-.java files in sources.jar:")
        for f in other_files:
            print(f"  {f}")
        print()

    write_findings_txt(coords, scm, inventory, git_total, only_in_jar, only_in_git,
                       in_both, content_results)
    print()

    byte_identical_count = sum(1 for r in content_results if r["status"] == "BYTE_IDENTICAL")
    if content_results and byte_identical_count == len(content_results):
        finding = (
            f"{in_both} overlapping files; "
            f"all {len(content_results)} files byte-identical to git — "
            f"SWH content SWHIDs match end-to-end"
        )
    elif content_results:
        finding = (
            f"{in_both} overlapping files; "
            f"{byte_identical_count}/{len(content_results)} files byte-identical; "
            f"{len(content_results) - byte_identical_count} differ"
        )
    elif only_in_jar:
        finding = f"{len(only_in_jar)} .java files in jar not present in git (generated)"
    else:
        finding = f"{in_both} overlapping files; content not verified"

    print(f"Finding: {finding}")

    return {
        "coords": coords,
        "scm_url": scm.get("url", ""),
        "scm_tag": scm.get("tag", ""),
        "jar_total_entries": total,
        "jar_by_extension": {k: len(v) for k, v in inventory.items()},
        "jar_non_java_files": other_files,
        "git_total_files": git_total,
        "only_in_jar_count": len(only_in_jar),
        "only_in_git_count": len(only_in_git),
        "in_both_count": in_both,
        "only_in_jar_sample": only_in_jar[:20],
        "only_in_git_sample": only_in_git[:20],
        "content_verification": content_results,
        "content_byte_identical": byte_identical_count,
        "finding": finding,
    }


if __name__ == "__main__":
    main()
