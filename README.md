# SWHID Verification – Pre-GSoC Research

Prototype exploring how to map Package URLs (PURLs) to Software Heritage Identifiers
(SWHIDs) across PyPI, crates.io, and Maven Central.

Built as background research for the GSoC project "Using SWHID to Identify Software
Components" (GFOSS/EELLAK, mentor: Alexios Zavras).

---

## What it does

For each ecosystem, it fetches the published artifact, compares it against the git
tree archived by Software Heritage, and reports where the mapping holds and where it
breaks down.

**PyPI**

- `pkg:pypi/six@1.17.0` — pure Python sdist, SWHID found in SWH archive
- `pkg:pypi/certifi@2024.12.14` — sdist includes a generated CA bundle not present
  in the git repository; SWHID does not match
- `pkg:pypi/torch@2.6.0` — wheel-only package (20 platform-specific wheels, no
  sdist); SWHID cannot be computed at all
- `pkg:pypi/pip@25.1.1` — has a PEP 740 Sigstore attestation linking the artifact
  to an exact git commit; that commit is present in SWH

**crates.io**

- `pkg:cargo/serde@1.0.203` — the registry injects three files during publish
  (`.cargo_vcs_info.json`, a rewritten `Cargo.toml`, and `Cargo.toml.orig`); after
  stripping those and restoring the original `Cargo.toml`, all 21 source file hashes
  match the SWH archive exactly

**Maven**

- Surveyed 13 popular JVM packages: most publish SCM metadata in the POM, but tag
  naming is inconsistent across projects
- `com.fasterxml.jackson.core:jackson-databind:2.17.0` — downloaded `-sources.jar`,
  compared every `.java` file against the git tree at the SCM tag; all files present
  in both are byte-identical to the SWH archived blobs

---

## Setup

```bash
python -m venv venv
source venv/Scripts/activate   # Windows (bash)
# source venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

---

## Running

Run all demos and write findings JSON files:

```bash
python main.py
```

Or run individual scripts:

```bash
python pypi/wheel_enumerator.py pkg:pypi/torch@2.6.0
python pypi/swhid_verifier.py pkg:pypi/six@1.17.0
python pypi/attestation_verifier.py pip 25.1.1
python crates/crate_analyzer.py pkg:cargo/serde@1.0.203
python crates/crate_normalizer.py pkg:cargo/serde@1.0.203
python maven/maven_analyzer.py
python maven/sources_inspector.py
```

---

## Repository structure

```
pypi/
  wheel_enumerator.py       list all wheels and sdists for a package version
  swhid_verifier.py         download sdist, compute SWHID, check SWH archive
  attestation_verifier.py   extract git commit from PEP 740 attestation, verify in SWH

crates/
  crate_analyzer.py         download crate, report files injected by the registry
  crate_normalizer.py       normalize crate, verify all file hashes against SWH blobs

maven/
  maven_analyzer.py         survey SCM metadata across top JVM packages
  sources_inspector.py      compare -sources.jar .java files against git tree

main.py                     runs all of the above and writes findings/

findings/                   pre-computed output (tracked in git)
  pypi_findings.json
  crates_findings.json
  maven_findings.json
  SPDX.json                 SPDX 2.3 provenance records for all packages
  serde_1.0.203_diff.txt
  serde_swhid_match.txt
  jackson-databind_2.17.0_sources_inspection.txt

examples/
  six_spdx3.json            same result expressed in SPDX 3.0 format
```

---

This is a research prototype. Not production code.

---

## Development Notes

The focus of this PoC is research, not engineering. Code was written purely as a
validation tool to confirm or disprove hypotheses about how published artifacts map
to Software Heritage's archived git trees. Every finding and conclusion was driven by
Odysseas Kalaitsidis.

Claude Opus 4.6 was used as an AI assistant for syntax lookups and for
navigating complex areas where AI tooling provides genuine leverage beyond what is
reasonable to expect from a student alone specifically: cross-referencing the SWH
data model internals, interpreting SPDX 2.3/3.0 specification edge cases, and
reasoning about registry-injected file normalization across three different ecosystems
simultaneously. These are tasks that involve synthesizing large volumes of
documentation quickly, not original research insight.

All research questions, ecosystem selection, architectural decisions, and conclusions
are the original work of Odysseas Kalaitsidis.
