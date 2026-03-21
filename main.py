# main.py
# Runs all demonstrations in sequence and writes per-ecosystem findings JSON.
#
# Usage: python main.py

import sys
import os
import json
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

from pypi import wheel_enumerator, swhid_verifier
from crates import crate_analyzer, crate_normalizer
from maven import maven_analyzer, sources_inspector

FINDINGS_DIR = os.path.join(os.path.dirname(__file__), "findings")

# Each entry: (ecosystem, title, one-line finding, callable)
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


# Collect findings keyed by ecosystem
ecosystem_findings = {"pypi": [], "crates": [], "maven": []}

for i, (ecosystem, title, finding, run) in enumerate(demos, 1):
    print(f"\n=== Demo {i}: {title} ===")
    print(f"Finding: {finding}")
    print()
    result = run()
    if result:
        ecosystem_findings[ecosystem].append(result)

# Write one JSON file per ecosystem
print("\n" + "=" * 60)
print("Writing findings JSON files...")
print()
for ecosystem, findings in ecosystem_findings.items():
    if findings:
        write_ecosystem_json(ecosystem, findings)
