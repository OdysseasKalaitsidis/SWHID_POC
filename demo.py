# examples/demo.py
# Runs all five demonstrations in sequence.
#
# Usage: python examples/demo.py

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pypi import wheel_enumerator, swhid_verifier
from crates import crate_analyzer, crate_normalizer

demos = [
    ("PyPI - wheel-only package (torch)",
     "1 PURL -> 20 platform-specific wheels, no source artifact",
     lambda: wheel_enumerator.main("pkg:pypi/torch@2.6.0")),

    ("PyPI - pure Python package (six)",
     "sdist SWHID found in SWH archive",
     lambda: swhid_verifier.main("pkg:pypi/six@1.17.0")),

    ("PyPI - package with generated files (certifi)",
     "sdist SWHID not found - tree diverges from git",
     lambda: swhid_verifier.main("pkg:pypi/certifi@2024.12.14")),

    ("crates.io - registry-injected files (serde)",
     "3 files added/rewritten by registry, all other files unmodified",
     lambda: crate_analyzer.main("serde", "1.0.203")),

    ("crates.io - normalization and verification (serde)",
     "after normalization, 21/21 source file hashes match SWH archive",
     lambda: crate_normalizer.main("serde", "1.0.203")),
]

for i, (title, finding, run) in enumerate(demos, 1):
    print(f"\n=== Demo {i}: {title} ===")
    print(f"Finding: {finding}")
    print()
    run()
