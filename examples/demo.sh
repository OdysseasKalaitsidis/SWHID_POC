#!/usr/bin/env bash
# demo.sh — run all four demonstrations
# Usage: bash examples/demo.sh

set -e
cd "$(dirname "$0")/.."

source venv/Scripts/activate 2>/dev/null || source venv/bin/activate

echo ""
echo "Demo 1: PyPI - wheel-only package (torch)"
echo "Finding: 1 PURL -> many artifacts, no unique SWHID"
python analyze.py pkg:pypi/torch@2.6.0

echo ""
echo "Demo 2: PyPI - simple package (six)"
echo "Finding: sdist SWHID found in SWH archive"
python analyze.py pkg:pypi/six@1.17.0

echo ""
echo "Demo 3: PyPI - generated-files package (certifi)"
echo "Finding: sdist SWHID not found - tree diverges from git"
python analyze.py pkg:pypi/certifi@2024.12.14

echo ""
echo "Demo 4: crates.io - normalization proof (serde)"
echo "Finding: strip 3 injected files -> SWHID matches git commit"
python analyze.py pkg:cargo/serde@1.0.203
