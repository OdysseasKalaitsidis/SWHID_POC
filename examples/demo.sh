#!/usr/bin/env bash
# demo.sh — run all three demonstrations and save findings
# Usage: bash examples/demo.sh

set -e
cd "$(dirname "$0")/.."

source venv/Scripts/activate 2>/dev/null || source venv/bin/activate

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Demo 1: PyPI — wheel-only package (torch)              ║"
echo "║  Finding: 1 PURL → many artifacts, no unique SWHID      ║"
echo "╚══════════════════════════════════════════════════════════╝"
python pypi_analyzer.py pkg:pypi/torch@2.6.0 | tee findings/pytorch_wheels.txt

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Demo 2: PyPI — simple package (six)                    ║"
echo "║  Finding: sdist SWHID found in archive                  ║"
echo "╚══════════════════════════════════════════════════════════╝"
python pypi_analyzer.py pkg:pypi/six@1.17.0

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Demo 3: PyPI — generated-files package (certifi)       ║"
echo "║  Finding: sdist SWHID not found — tree diverges from git║"
echo "╚══════════════════════════════════════════════════════════╝"
python pypi_analyzer.py pkg:pypi/certifi@2024.12.14

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Demo 4: crates.io — normalization (serde)              ║"
echo "║  Finding: strip 3 files → SWHID matches git tag         ║"
echo "╚══════════════════════════════════════════════════════════╝"
python crates_analyzer.py pkg:cargo/serde@1.0.203 | tee findings/serde_diff.txt

echo ""
echo "Findings saved to findings/"
