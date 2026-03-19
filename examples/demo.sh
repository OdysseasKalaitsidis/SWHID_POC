#!/usr/bin/env bash
# demo.sh -- run all demonstrations in sequence
# Usage: bash examples/demo.sh

set -e
cd "$(dirname "$0")/.."

source venv/Scripts/activate 2>/dev/null || source venv/bin/activate

echo ""
echo "=== Demo 1: PyPI - wheel-only package (torch) ==="
echo "Finding: 1 PURL -> 20 platform-specific wheels, no source artifact"
python pypi/wheel_enumerator.py pkg:pypi/torch@2.6.0

echo ""
echo "=== Demo 2: PyPI - pure Python package (six) ==="
echo "Finding: sdist SWHID found in SWH archive"
python pypi/swhid_verifier.py pkg:pypi/six@1.17.0

echo ""
echo "=== Demo 3: PyPI - package with generated files (certifi) ==="
echo "Finding: sdist SWHID not found - tree diverges from git"
python pypi/swhid_verifier.py pkg:pypi/certifi@2024.12.14

echo ""
echo "=== Demo 4: crates.io - registry-injected files (serde) ==="
echo "Finding: 3 files added/rewritten by registry, all other files unmodified"
python crates/crate_analyzer.py pkg:cargo/serde@1.0.203

echo ""
echo "=== Demo 5: crates.io - normalization and verification (serde) ==="
echo "Finding: after normalization, 21/21 source file hashes match SWH archive"
python crates/crate_normalizer.py pkg:cargo/serde@1.0.203
