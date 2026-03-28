# Usage: python main.py

import sys
import os
import json
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

from pypi import wheel_enumerator, swhid_verifier, attestation_verifier
from crates import crate_analyzer, crate_normalizer
from maven import maven_analyzer, sources_inspector

FINDINGS_DIR = os.path.join(os.path.dirname(__file__), "findings")

demos = [
    (
        "pypi",
        "PyPI - wheel-only package (torch)",
        "1 PURL -> 20 platform-specific wheels, no source artifact",
        lambda: wheel_enumerator.main("pkg:pypi/torch@2.6.0"),
    ),
    (
        "pypi",
        "PyPI - pure Python package (six)",
        "sdist SWHID found in SWH archive",
        lambda: swhid_verifier.main("pkg:pypi/six@1.17.0"),
    ),
    (
        "pypi",
        "PyPI - package with generated files (certifi)",
        "sdist SWHID not found - tree diverges from git",
        lambda: swhid_verifier.main("pkg:pypi/certifi@2024.12.14"),
    ),
    (
        "crates",
        "crates.io - registry-injected files (serde)",
        "3 files added/rewritten by registry, all other files unmodified",
        lambda: crate_analyzer.main("serde", "1.0.203"),
    ),
    (
        "crates",
        "crates.io - normalization and verification (serde)",
        "after normalization, 21/21 source file hashes match SWH archive",
        lambda: crate_normalizer.main("serde", "1.0.203"),
    ),
    (
        "pypi",
        "PyPI - PEP 740 attestation → SWH commit (pip)",
        "attestation commit SHA found in SWH revision archive",
        lambda: attestation_verifier.main("pip", "25.1.1"),
    ),
    (
        "maven",
        "Maven - SCM metadata survey (13 packages)",
        "SCM block completeness and -sources.jar availability across top JVM packages",
        lambda: maven_analyzer.main(),
    ),
    (
        "maven",
        "Maven - sources.jar deep inspection (jackson-databind)",
        "inventory jar contents, compare .java files against git tree at SCM tag",
        lambda: sources_inspector.main(),
    ),
]


def write_ecosystem_json(ecosystem, findings):
    path = os.path.join(FINDINGS_DIR, f"{ecosystem}_findings.json")
    data = {
        "ecosystem": ecosystem,
        "generated_at": str(date.today()),
        "findings": findings,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"  -> written: findings/{ecosystem}_findings.json")


def build_spdx_records(ecosystem_findings):
    records = []

    for f in ecosystem_findings.get("pypi", []):
        purl = f.get("purl", "")
        if "found_in_swh" in f:
            # sdist package — directory SWHID was computed
            records.append({
                "purl": purl,
                "swhid": f.get("swhid"),
                "confidence": "verified" if f["found_in_swh"] else "partial",
                "found_in_swh": f["found_in_swh"],
                "verifiedFiles": None,
                "totalFiles": None,
                "relationship": "hasDistributionArtifact",
                "note": f.get("finding", ""),
            })
        elif "commit_in_swh" in f:
            sha = f.get("commit_sha", "")
            records.append({
                "purl": purl,
                "swhid": f"swh:1:rev:{sha}" if sha else None,
                "confidence": "verified" if f["commit_in_swh"] else "inferred",
                "found_in_swh": f["commit_in_swh"],
                "verifiedFiles": None,
                "totalFiles": None,
                "relationship": "hasDistributionArtifact",
                "note": f.get("finding", ""),
            })
        else:
            records.append({
                "purl": purl,
                "swhid": None,
                "confidence": "not_applicable",
                "found_in_swh": None,
                "verifiedFiles": None,
                "totalFiles": None,
                "relationship": "hasDistributionArtifact",
                "note": f.get("finding", ""),
            })

    for f in ecosystem_findings.get("crates", []):
        if "swhid" not in f:
            continue
        purl = f"pkg:cargo/{f['name']}@{f['version']}"
        total = f.get("verified_matches", 0) + f.get("verified_mismatches", 0)
        records.append({
            "purl": purl,
            "swhid": f.get("swhid"),
            "confidence": "verified_file_level" if f.get("verified_mismatches") == 0 else "partial",
            "found_in_swh": f.get("verified_mismatches") == 0,
            "verifiedFiles": f.get("verified_matches"),
            "totalFiles": total,
            "relationship": "hasDistributionArtifact",
            "note": f.get("finding", ""),
        })

    for f in ecosystem_findings.get("maven", []):
        if "packages_surveyed" in f:
            continue
        coords = f.get("coords", "")
        if not coords:
            continue
        group, artifact, version = coords.split(":")
        purl = f"pkg:maven/{group}/{artifact}@{version}"
        verified = [r for r in f.get("content_verification", []) if r["status"] == "BYTE_IDENTICAL"]
        sample_swhid = f"swh:1:cnt:{verified[0]['jar_sha1']}" if verified else None
        
        confidence = "verified_file_level_sample"
        if f.get("content_byte_identical") == f.get("in_both_count") and f.get("in_both_count", 0) > 0:
            confidence = "verified_file_level"

        records.append({
            "purl": purl,
            "swhid": sample_swhid,
            "confidence": confidence,
            "found_in_swh": len(verified) > 0,
            "verifiedFiles": f.get("content_byte_identical"),
            "totalFiles": f.get("in_both_count"),
            "relationship": "hasDistributionArtifact",
            "note": f.get("finding", ""),
        })

    return records


def write_spdx_json(records):
    path = os.path.join(FINDINGS_DIR, "SPDX.json")
    data = {
        "spdxVersion": "SPDX-2.3",
        "generated_at": str(date.today()),
        "comment": "SWHID provenance records computed by swhid-poc across PyPI, crates.io, and Maven",
        "packages": records,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"  -> written: findings/SPDX.json  ({len(records)} records)")


ecosystem_findings = {"pypi": [], "crates": [], "maven": []}

for i, (ecosystem, title, finding, run) in enumerate(demos, 1):
    print(f"\n=== Demo {i}: {title} ===")
    print(f"Finding: {finding}")
    print()
    result = run()
    if result:
        ecosystem_findings[ecosystem].append(result)

print("\n" + "=" * 60)
print("Writing findings JSON files...")
print()
for ecosystem, findings in ecosystem_findings.items():
    if findings:
        write_ecosystem_json(ecosystem, findings)

spdx_records = build_spdx_records(ecosystem_findings)
write_spdx_json(spdx_records)

