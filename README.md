# SWHID PoC: Mapping PURLs to Software Heritage Identifiers

A research proof-of-concept exploring the gap between Package URLs (PURLs) and
Software Heritage Intrinsic Identifiers (SWHIDs) across two ecosystems: PyPI and crates.io.

Built as supporting evidence for a GSoC proposal to implement production-grade
PURL→SWHID resolution in the Software Heritage infrastructure.

---

## The Problem

[PURLs](https://github.com/package-url/purl-spec) identify packages in registries
(`pkg:pypi/torch@2.6.0`). [SWHIDs](https://docs.softwareheritage.org/devel/swh-model/persistent-identifiers.html)
identify source code by content hash (`swh:1:dir:...`). Bridging them is not trivial:

- **The mapping is not 1-to-1.** One PURL can resolve to 0, 1, or 20+ artifacts.
- **Registry artifacts diverge from git trees.** Registries inject or rewrite files
  before publishing, so the artifact's content hash ≠ the git tag's content hash.
- **The problem is ecosystem-specific.** crates.io injects exactly 3 known files.
  PyPI sdists contain generated files with no standardized stripping rules.

---

## Key Findings

### Finding 1: PyPI — one PURL, many (or no) source identifiers

`pkg:pypi/torch@2.6.0` resolves to **0 sdists and 20+ wheels** on PyPI.
There is no source artifact. A SWHID cannot be computed at all.

Even when a PyPI package publishes an sdist, the SWHID may not match the git tree
archived by Software Heritage because of generated files absent from the repository.

| Package | sdists | wheels | Computed SWHID | Found in SWH? | Why |
|---|---|---|---|---|---|
| `six==1.17.0` | 1 | 1 | `swh:1:dir:…` | ✓ **FOUND** | Pure Python, no generated files |
| `certifi==2024.12.14` | 1 | 1 | `swh:1:dir:…` | ✗ **not found** | Ships CA bundle not in git repo |
| `torch==2.6.0` | 0 | 20+ | — | — | No sdist published |

The size contrast makes the torch case vivid:

```
torch-2.6.0-cp310-cp310-linux_x86_64.whl       ~750 MB   (CUDA, Linux, Python 3.10)
torch-2.6.0-cp312-cp312-win_amd64.whl          ~730 MB   (CUDA, Windows, Python 3.12)
torch-2.6.0-cp310-cp310-manylinux...x86_64.whl ~750 MB
...20+ more
```

Run `python analyze.py pkg:pypi/torch@2.6.0` to see the full wheel enumeration.

### Finding 2: crates.io — normalization produces a stable SWHID

`pkg:cargo/serde@1.0.203` has exactly one source artifact. The `.crate` file
(a tar.gz) contains three files injected by the registry that are **not present
in the git repository**:

| File | Purpose |
|---|---|
| `.cargo_vcs_info.json` | Records the git commit sha1 used to build this release |
| `Cargo.toml` | Rewritten by `cargo publish` (dependency versions normalized) |
| `Cargo.toml.orig` | Original `Cargo.toml` before rewriting |

After stripping these three files, the SWHID of the remaining tree **matches**
the directory SWHID of the corresponding git commit in the Software Heritage archive.

```
Computed SWHID (stripped .crate):  swh:1:dir:3a2c5ef3e33bfbb98bb51e6fd7ef7fdac4082f17
SWH directory (git commit lookup): 3a2c5ef3e33bfbb98bb51e6fd7ef7fdac4082f17

Result: MATCH — normalization confirmed.
```

Run `python analyze.py pkg:cargo/serde@1.0.203` to reproduce this result.

### Finding 3: the contrast is the finding

| Ecosystem | PURL → artifacts | Source SWHID possible? | Normalization |
|---|---|---|---|
| PyPI | 1 PURL → 0–20+ wheels | Sometimes (sdist-only, no generated files) | No standard rules exist |
| crates.io | 1 PURL → 1 `.crate` | Yes, after stripping 3 known files | Deterministic |

This asymmetry defines the scope of the GSoC project.

---

## Setup

```bash
python -m venv venv
source venv/Scripts/activate  # Windows
# source venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
```

---

## Usage

```bash
python analyze.py <purl>
```

```bash
# PyPI: wheel-only package — shows the 1-to-many problem
python analyze.py pkg:pypi/torch@2.6.0

# PyPI: SWHID found in SWH archive
python analyze.py pkg:pypi/six@1.17.0

# PyPI: SWHID not found (generated files diverge from git)
python analyze.py pkg:pypi/certifi@2024.12.14

# crates.io: normalization proof
python analyze.py pkg:cargo/serde@1.0.203

# Machine-readable output
python analyze.py pkg:pypi/six@1.17.0 --format json
```

Findings are saved automatically to `findings/` (gitignored — runtime output).

---

## Repository Structure

```
├── analyze.py           # Entry point — accepts any PURL, dispatches by ecosystem
├── pypi_analyzer.py     # PyPI analysis: metadata, artifact inventory, SWHID, scoring
├── crates_analyzer.py   # crates.io analysis: injected files, normalization proof, scoring
├── calculator.py        # Download, extract, strip injected files, compute SWHID
├── parser.py            # Registry API queries (PyPI JSON API, crates.io API)
├── swh_api.py           # Software Heritage archive REST API client
├── swhid_verifier.py    # Standalone: compute SWHID for any local directory
├── tests/               # Unit tests for calculator, parser, swh_api
├── examples/
│   └── demo.sh          # Runs the four key demonstrations
└── requirements.txt
```

---

## What's Next

This PoC establishes the problem boundaries. The proposed GSoC project will implement
a production-grade PURL→SWHID resolution service for Software Heritage that:

1. **Handles PyPI sdists** — computes SWHIDs and documents which packages produce
   verifiable identifiers vs. which diverge from the archived git tree
2. **Normalizes crates.io artifacts** — applies the demonstrated stripping technique
   at scale across the full crates.io index
3. **Extends to npm and Maven** — each ecosystem has its own injection/rewriting
   conventions; the normalization rules must be discovered and codified per ecosystem
4. **Produces a dataset** — a mapping of `(PURL, SWHID, match_status)` tuples that
   can be integrated into the Software Heritage infrastructure for provenance tracking
   and supply chain security analysis
