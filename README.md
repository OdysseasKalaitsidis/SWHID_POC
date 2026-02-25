# SWHID POC

Fetches a Python package from PyPI and computes its [SWHID](https://swhid.org) (Software Heritage Intrinsic Identifier).

## Setup

```bash
python -m venv venv
source venv/Scripts/activate  # Windows
pip install -r requirements.txt
```

## Usage

```bash
python main.py              # will prompt for package and version
python main.py six 1.17.0  # or pass them directly
```

Output:
```
SWHID: swh:1:dir:...
SWH:   FOUND
```

## How it works

1. Hits the PyPI JSON API to get the sdist download URL
2. Downloads and extracts the tarball to `tmp/`
3. Computes the SWHID using `swh.model`
4. Verifies the SWHID against the Software Heritage archive

## Notes

Works reliably for pure-Python packages like `six` where the sdist matches what SWH has archived from git. Packages with generated files (`.egg-info`, compiled C, etc.) will compute a valid SWHID but it won't be found in the archive — the sdist and git tree differ.
