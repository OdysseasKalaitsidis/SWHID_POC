# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A verification framework that maps Package URLs (PURLs) to verified Software Heritage Identifiers (SWHIDs), bridging the gap between mutable package-manager releases (PyPI, npm, Cargo, Go Modules, Maven, NuGet) and Software Heritage's content-addressed archive. Findings are exported as SPDX 3.0 JSON-LD manifests and can gate CI/CD pipelines via a policy engine.

## Commands

```bash
# Setup
pip install -e ".[dev]"          # editable install + ruff, mypy, pytest, responses, pytest-cov, build, twine

# Lint / type check (both run in CI, both must pass)
ruff check .
mypy swhid_tool/                 # strict mode, targets python 3.10 (see [tool.mypy] in pyproject.toml)

# Tests
pytest tests/
pytest tests/test_strategies.py                     # one module
pytest tests/test_strategies.py::test_cargo_resolve  # one test
pytest tests/ -k cargo                               # by keyword
pytest tests/ --cov=swhid_tool                       # with coverage

# CLI (entry point: swhid_tool.cli:app, installed as `swhid-tool`)
python -m swhid_tool.cli swhid-map pkg:pypi/six@1.17.0
python -m swhid_tool.cli batch-process input_purls.txt output_report.jsonld
python -m swhid_tool.cli audit . --policy swhid-policy.toml --markdown-summary audit-report.md
python -m swhid_tool.cli verify-path /path/to/installed/library manifest.jsonld

# REST API (FastAPI, experimental)
python -m uvicorn swhid_tool.api:app --port 8000
```

Config is via env vars / `.env`: `SWH_TOKEN`/`SWH_AUTH_TOKEN` (Software Heritage auth token — anonymous requests are heavily rate-limited), `CACHE_DIR` (defaults to `./cache`), `LOG_LEVEL`.

## Architecture

**Strategy pattern decouples ecosystem-specific resolution logic from the core engine.** Flow for a single PURL:

```
CLI/API → SWHIDManager.resolve(purl)
            → purl_parser.parse_purl()            # ecosystem, name, version, qualifiers
            → strategies[ecosystem].resolve(...)  # ecosystem-specific VerificationStrategy
            → SWHClient                            # talks to archive.softwareheritage.org/api/1
```

- `swhid_tool/manager.py` — `SWHIDManager` is the central router; it owns one `SWHClient` and a `strategies` dict keyed by PURL ecosystem (`pypi`, `cargo`, `maven`, `npm`, `golang`, `nuget`). To add a new ecosystem: create `swhid_tool/strategies/<eco>_strategy.py` implementing `VerificationStrategy` (`swhid_tool/strategies/base.py`, single abstract method `resolve(name, version, qualifiers) -> Dict`), then register it in `SWHIDManager.__init__`.
- `swhid_tool/core.py` — `SWHClient` wraps the SWH Archive REST API (retries with backoff on 429/5xx built in) and provides `check_swhid`, `get_revision`, `get_directory_for_revision` (handles monorepo `path_in_vcs`), `build_directory_blob_index` (recursive dir → `{relpath: content_sha1_git}`), and `trigger_save_code_now` (no-op by default; `suppress_save` must be explicitly disabled). Also has free functions `compute_content_swhid`/`compute_directory_swhid` using `swh.model`.
- Each strategy's `resolve()` returns a findings dict with at minimum `purl`, `status` (`Verified` / `Inferred` / `Partial` / `Failed` / `Error`) and `confidence` (mirrors status, used for policy comparisons: Verified=3, Inferred=2, Partial=1, else 0).
  - **PyPI** (`strategies/pypi_strategy.py`) cascades three strategies until one verifies: **A** extract commit SHA from Sigstore/PEP 740 Fulcio certificate (OID `1.3.6.1.4.1.57264.1.13`) → check SWH directly; **B** match PyPI `project_urls` (Source/GitHub/Repository/Homepage) against SWH snapshot branches via fuzzy tag matching (`version`, `v{version}`, `release-{version}`, `{name}-{version}`); **C** download sdist/wheel, strip generated files (`.egg-info`, `__pycache__`, `.dist-info`, `PKG-INFO`, `setup.cfg`, `.pyc`), compute directory SWHID and check it against the archive.
  - **Cargo** (`strategies/cargo_strategy.py`) downloads the `.crate`, restores `Cargo.toml` from `Cargo.toml.orig` and strips registry-added files (`.cargo_vcs_info.json`), then does byte-for-byte file-level comparison against the SWH blob index for the commit recorded in `.cargo_vcs_info.json` (tolerating known-mutated metadata files like `Cargo.lock`/`README*`/`LICENSE*`).
  - Maven/npm/Go/NuGet strategies follow the same `VerificationStrategy` contract with ecosystem-appropriate source discovery (see `maintainer_guide.md` for what makes a package verifiable per ecosystem).
- `swhid_tool/batch_processor.py` — `BatchProcessor` resolves many PURLs concurrently (`ThreadPoolExecutor`, 5 workers anonymous / 10 authenticated), with per-PURL JSON caching under `cache/` (filename derived from the PURL) so repeated runs skip network calls.
- `swhid_tool/project_detector.py` — `ProjectDetector` walks a project directory (skipping `node_modules`, `venv`, `.git`, `bin`, `obj`, `dist`, `build`, `tmp`) for `package.json`, `*.csproj`, `requirements.txt`, `Cargo.toml`, `go.mod`, `pom.xml` and emits PURLs; backs the `audit` CLI command's auto-detection.
- `swhid_tool/scanner.py` — `InstallationScanner` recomputes content/directory SWHIDs for files on disk (e.g. `node_modules`, NuGet cache, venv `site-packages`) and diffs against expected SWHIDs from a manifest, for post-install integrity auditing.
- `swhid_tool/osv_client.py` — `OSVClient.query_vulnerabilities_hybrid` queries OSV.dev's batch API by **both** PURL and resolved commit SHA (dedup'd by vuln ID), so vulnerability matching isn't fooled by package renames/forks — this is the point of resolving to a SWHID in the first place.
- `swhid_tool/policy.py` — `PolicyEngine` loads `swhid-policy.toml` (`minimum_confidence_level`, `fail_on_mismatch`, `fail_on_vulnerability`, `max_severity`, `allowlist` with fnmatch globs, `ignored_vulnerabilities`) and evaluates both resolution findings and scanner results into a violation list; a non-empty violation list makes the `audit` CLI command exit non-zero, which is what breaks CI/CD.
- `swhid_tool/spdx_exporter.py` — serializes findings into SPDX 3.0 JSON-LD via `spdx_tools.spdx3` models (`Package.content_identifier` carries the SWHID, `ExternalIdentifier` carries the PURL). Compliance with RDF/SHACL is checked in `tests/test_validation.py`.
- `swhid_tool/cli.py` (Typer app, entry point `swhid-tool`) and `swhid_tool/api.py` (FastAPI) are thin wrappers over `SWHIDManager`/`BatchProcessor`/`ProjectDetector`/`OSVClient`/`PolicyEngine` — the `audit` command in `cli.py` is the fullest end-to-end pipeline (detect deps → resolve SWHIDs → OSV scan → local install scan → policy evaluation → optional Markdown report for `$GITHUB_STEP_SUMMARY`) and is the best place to read to see how the pieces compose.

## CI/CD

`.github/workflows/publish.yml` runs on every push/PR to `main`/`master`: `ruff check .` → `mypy swhid_tool/` → `pytest tests/` → `python -m swhid_tool.cli audit` (self-audit of this repo's own dependencies). On push to `main`/`master` only, it auto-bumps the patch version in `pyproject.toml`/`swhid_tool/__init__.py`, tags, creates a GitHub release, and publishes to PyPI.

## Code style

- License headers on source files: `# SPDX-FileCopyrightText: 2026 Odysseas Kalaitsidis` / `# SPDX-License-Identifier: MIT`.
- Mypy strict mode — public APIs need type annotations.
