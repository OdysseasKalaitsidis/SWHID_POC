# PyPI SWHID POC

A proof of concept for computing and verifying [Software Heritage Intrinsic Identifiers](https://swhid.org) (SWHIDs) for PyPI packages — built as part of exploring the GSoC project _"Using SWHID to Identify Software Components"_.

## What it does

Given a PyPI package name and version, this tool:

1. Fetches the sdist URL from the PyPI JSON API
2. Downloads and extracts the tarball in-memory
3. Computes the `swh:1:dir:` SWHID of the source tree using `swh.model`
4. Verifies the computed SWHID against the Software Heritage archive API

## Usage

```bash
pip install -r requirement.txt
python main.py                  # interactive prompt
python main.py six 1.17.0       # direct
```

## Key finding

Validation against the SWH archive confirmed correct computation for `six 1.17.0` — a pure-Python package with no generated files, where the sdist and git tree are identical.

For packages like `certifi` and `charset-normalizer`, the computed SWHID is not found in the SWH archive. This is expected: SWH primarily archives from VCS (git), while PyPI sdists often contain generated files (e.g. `.egg-info`, Cython-compiled `.c` files) absent from the repository. This **sdist-vs-git divergence** is the core mapping challenge the full project needs to solve.
