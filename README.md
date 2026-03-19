# SWHID Verification Prototype -- Exploring the PURL-to-SWHID Gap

This prototype explores the practical challenges of mapping Package URLs (PURLs) to
Software Heritage Identifiers (SWHIDs) across different package ecosystems. It was
built as pre-GSoC research for the "Using SWHID to Identify Software Components"
project under GFOSS/EELLAK.

---

## Three Key Findings

### Finding 1: The mapping is not 1-to-1

`pkg:pypi/torch@2.6.0` resolves to **0 sdists and 20 wheels** on PyPI.
There is no source artifact. A SWHID cannot be computed at all.

Even when a PyPI package publishes an sdist, the SWHID may not match the git tree
archived by Software Heritage because of generated files absent from the repository.

| Package               | sdists | wheels | Computed SWHID        | Found in SWH? | Why                             |
| --------------------- | ------ | ------ | --------------------- | ------------- | ------------------------------- |
| `six==1.17.0`         | 1      | 1      | `swh:1:dir:06d75b...` | **FOUND**     | Pure Python, no generated files |
| `certifi==2024.12.14` | 1      | 1      | `swh:1:dir:...`       | not found     | Ships CA bundle not in git repo |
| `torch==2.6.0`        | 0      | 20     | --                    | --            | No sdist published              |

The size contrast makes the torch case vivid:

```
torch-2.6.0-cp310-cp310-manylinux1_x86_64.whl    731.2 MB  (CUDA, Linux, Python 3.10)
torch-2.6.0-cp311-none-macosx_11_0_arm64.whl      63.4 MB  (macOS ARM)
torch-2.6.0-cp312-cp312-win_amd64.whl            194.7 MB  (Windows)
... 17 more
```

### Finding 2: The mismatch varies by ecosystem

`pkg:cargo/serde@1.0.203` has exactly one source artifact. The `.crate` file
differs from the git repository in exactly three files injected by the registry:

| File                   | Purpose                                                       |
| ---------------------- | ------------------------------------------------------------- |
| `.cargo_vcs_info.json` | Records the git commit sha1 used to build this release        |
| `Cargo.toml`           | Rewritten by `cargo publish` (dependency versions normalized) |
| `Cargo.toml.orig`      | Original `Cargo.toml` before rewriting                        |

After normalization (restore `Cargo.toml.orig` as `Cargo.toml`, remove the other
two), every source file's content hash matches the corresponding SWH blob exactly:

```
  MATCH  Cargo.toml
  MATCH  build.rs
  MATCH  src/lib.rs
  MATCH  src/de/mod.rs
  ... 17 more source files
============================================================
Result: MATCH - all crate source files verified
============================================================
  21 files verified against SWH archive blobs: ALL MATCH
```

See `findings/serde_swhid_match.txt` for the full output.

### Finding 3: Some ecosystems provide built-in provenance

Crates.io embeds the source git commit hash in every crate via `.cargo_vcs_info.json`.
This gives a direct link from the published artifact back to the exact git commit
archived by Software Heritage -- making the verification chain complete.

On PyPI, PEP 740 attestations (Sigstore-based) can link wheels to their source
commit for packages using Trusted Publishing, but adoption is not yet universal.

---

## Setup

```bash
python -m venv venv
source venv/Scripts/activate   # Windows (bash)
# source venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

---

## Usage

```bash
# PyPI: wheel-only package -- shows the 1-to-many problem
python pypi/wheel_enumerator.py pkg:pypi/torch@2.6.0

# PyPI: SWHID found in SWH archive (pure Python, no generated files)
python pypi/swhid_verifier.py pkg:pypi/six@1.17.0

# PyPI: SWHID not found (generated CA bundle diverges from git)
python pypi/swhid_verifier.py pkg:pypi/certifi@2024.12.14

# crates.io: shows which files the registry injected
python crates/crate_analyzer.py pkg:cargo/serde@1.0.203

# crates.io: normalize and verify all source files against SWH
python crates/crate_normalizer.py pkg:cargo/serde@1.0.203

# Run all demos in sequence
bash examples/demo.sh
```

---

## Repository Structure

```
SWHID_POC/
|
+-- README.md
|
+-- pypi/
|   +-- wheel_enumerator.py      # Queries PyPI API, lists all wheels
|   |                             # for a package version with sizes
|   |                             # and platform details
|   |
|   +-- swhid_verifier.py        # Downloads sdist, computes SWHID
|                                 # using swh.model, verifies against
|                                 # Software Heritage archive API
|
+-- crates/
|   +-- crate_analyzer.py        # Downloads crate from crates.io,
|   |                             # extracts and reports registry-added
|   |                             # files and their purpose
|   |
|   +-- crate_normalizer.py      # Strips registry files, restores
|                                 # original Cargo.toml, verifies all
|                                 # source file hashes against SWH
|
+-- findings/
|   +-- torch_2.6.0_wheels.txt   # Raw PyPI API output for torch
|   +-- serde_1.0.203_diff.txt   # Registry-injected files in serde
|   +-- serde_swhid_match.txt    # File-level verification showing
|                                 # 21/21 MATCH after normalization
|
+-- requirements.txt              # swh.model, requests
|
+-- examples/
    +-- demo.sh                   # Runs all demos in sequence
```

---

## What each script does

**pypi/wheel_enumerator.py** -- Takes a PURL like `pkg:pypi/torch@2.6.0`, queries
PyPI, and prints: number of wheels, number of sdists, each wheel filename with size
and platform tags.

**pypi/swhid_verifier.py** -- Takes a PURL for a PyPI package like
`pkg:pypi/six@1.17.0`, downloads the sdist, computes its directory SWHID using
`swh.model`, and checks if it exists in the Software Heritage archive.

**crates/crate_analyzer.py** -- Takes a crate PURL like `pkg:cargo/serde@1.0.203`,
downloads from crates.io, and reports exactly which files the registry added or
modified, with their sizes and content.

**crates/crate_normalizer.py** -- Takes the crate, restores `Cargo.toml` from
`Cargo.toml.orig`, removes `.cargo_vcs_info.json` and `Cargo.toml.orig`, then
verifies every remaining source file's content hash against the SWH blob archive.
Prints MATCH or MISMATCH per file.

This is a research prototype, not the final tool.
