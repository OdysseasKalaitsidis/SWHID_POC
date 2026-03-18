"""
analyze.py - Unified PURL -> SWHID Supply Chain Analyzer

Accepts a PURL (pkg:pypi/... or pkg:cargo/...) or explicit name/version/ecosystem,
runs deep analysis, and renders a rich terminal report with supply chain security
scoring. Findings are saved as JSON to the findings/ directory.

Usage:
    python analyze.py pkg:pypi/six@1.17.0
    python analyze.py pkg:cargo/serde@1.0.203
    python analyze.py pkg:pypi/certifi@2024.12.14 --format json
    python analyze.py --ecosystem pypi --name torch --version 2.6.0
"""

import argparse
import json
import os
import sys
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
except ImportError:
    sys.exit(
        "Missing dependency: pip install rich\n"
        "Or run: pip install -r requirements.txt"
    )

import pypi_analyzer
import crates_analyzer

console = Console(legacy_windows=False)


# ---------------------------------------------------------------------------
# PURL parsing
# ---------------------------------------------------------------------------

def parse_purl(purl):
    for prefix, ecosystem in [("pkg:pypi/", "pypi"), ("pkg:cargo/", "cargo")]:
        if purl.startswith(prefix):
            rest = purl[len(prefix):]
            if "@" not in rest:
                raise ValueError(f"PURL must include @version: {purl}")
            name, version = rest.split("@", 1)
            return ecosystem, name, version
    raise ValueError(f"Unsupported PURL ecosystem: {purl}")


# ---------------------------------------------------------------------------
# Score rendering helpers
# ---------------------------------------------------------------------------

def _score_color(score):
    if score >= 8:
        return "green"
    if score >= 5:
        return "yellow"
    return "red"


def _score_bar(score, width=10):
    filled = round(score / 10 * width)
    return "#" * filled + "." * (width - filled)


def _render_scores(scores):
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Dimension", style="bold")
    table.add_column("Bar")
    table.add_column("Score")
    table.add_column("Meaning", style="dim")

    dimensions = [
        ("reproducibility", "Can PURL -> SWHID be recomputed deterministically?"),
        ("provenance",      "Is the SWHID present in the SWH archive?"),
        ("normalization",   "Are the registry injection rules known and complete?"),
    ]
    for key, meaning in dimensions:
        s = scores.get(key, 0)
        c = _score_color(s)
        table.add_row(
            key.capitalize(),
            f"[{c}]{_score_bar(s)}[/]",
            f"[{c}]{s}/10[/]",
            meaning,
        )

    overall = scores.get("overall", 0)
    c = _score_color(overall)
    table.add_row(
        "[bold]Overall[/]",
        f"[{c}]{_score_bar(overall)}[/]",
        f"[bold {c}]{overall}/10[/]",
        "",
    )
    console.print(table)


# ---------------------------------------------------------------------------
# PyPI renderer
# ---------------------------------------------------------------------------

def _render_pypi(findings):
    m        = findings["metadata"]
    a        = findings["artifacts"]
    s        = findings.get("swhid", {})
    analysis = findings["analysis"]
    scores   = findings["scores"]

    console.print(Panel(
        f"[bold cyan]pkg:pypi/{findings['name']}@{findings['version']}[/]",
        expand=False, border_style="cyan",
    ))

    # Metadata
    meta = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    meta.add_column("Field", style="bold dim", min_width=14)
    meta.add_column("Value")
    if m.get("summary"):        meta.add_row("Summary",      m["summary"])
    if m.get("license"):        meta.add_row("License",      m["license"])
    if m.get("author"):         meta.add_row("Author",       m["author"])
    if m.get("requires_python"):meta.add_row("Python",       m["requires_python"])
    meta.add_row("Dependencies", str(m.get("dependency_count", 0)))
    if m.get("vcs_url"):        meta.add_row("Repository",   m["vcs_url"])
    console.print(meta)

    # Artifact inventory
    console.rule("[bold]Artifact Inventory[/]")
    art = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    art.add_column("Type")
    art.add_column("Count", justify="right")
    art.add_column("Total Size", justify="right")

    sdist_bytes = sum(f["size"] for f in a.get("sdists", []))
    wheel_bytes = sum(w["size"] for w in a.get("wheels", []))

    def _fmt_size(b):
        return f"{b / 1_048_576:.1f} MB" if b > 1_000_000 else f"{b // 1024:,} KB"

    art.add_row("sdist", str(a["sdist_count"]), _fmt_size(sdist_bytes) if sdist_bytes else "-")
    art.add_row("wheel", str(a["wheel_count"]), _fmt_size(wheel_bytes) if wheel_bytes else "-")
    console.print(art)

    if a.get("wheels"):
        wt = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
        wt.add_column("Filename")
        wt.add_column("Python")
        wt.add_column("ABI")
        wt.add_column("Platform")
        wt.add_column("Size", justify="right")
        for w in a["wheels"]:
            wt.add_row(
                w["filename"], w["python"], w["abi"], w["platform"],
                _fmt_size(w["size"]),
            )
        console.print(wt)

    # SWHID
    console.rule("[bold]SWHID Analysis[/]")
    if s:
        found  = s.get("found_in_swh", False)
        color  = "green" if found else "red"
        status = "FOUND [OK]" if found else "NOT FOUND [!!]"
        console.print(f"  [dim]SWHID:[/] [cyan]{s['value']}[/]")
        console.print(f"  [dim]SWH:  [/] [{color}]{status}[/]")
        if s.get("vcs_url"):
            console.print(f"  [dim]VCS:  [/] {s['vcs_url']}")
    else:
        console.print(f"  [red]No sdist - SWHID not computed.[/]")

    # Verdict
    console.rule("[bold]Verdict[/]")
    if analysis.get("reproducible"):
        border = "green"
    elif analysis.get("has_sdist"):
        border = "yellow"
    else:
        border = "red"
    console.print(Panel(
        f"[bold]{analysis['verdict']}[/]\n\n[dim]{analysis['explanation']}[/]",
        border_style=border, expand=False,
    ))

    # Scores
    console.rule("[bold]Supply Chain Security Scores[/]")
    _render_scores(scores)


# ---------------------------------------------------------------------------
# Cargo renderer
# ---------------------------------------------------------------------------

def _render_cargo(findings):
    m        = findings["metadata"]
    inj      = findings.get("injected_files", {})
    norm     = findings.get("normalization", {})
    s        = findings.get("swhid", {})
    analysis = findings["analysis"]
    scores   = findings["scores"]

    console.print(Panel(
        f"[bold cyan]pkg:cargo/{findings['name']}@{findings['version']}[/]",
        expand=False, border_style="cyan",
    ))

    # Metadata
    meta = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    meta.add_column("Field", style="bold dim", min_width=14)
    meta.add_column("Value")
    if m.get("description"):  meta.add_row("Description", m["description"])
    if m.get("license"):      meta.add_row("License",     m["license"])
    if m.get("repository"):   meta.add_row("Repository",  m["repository"])
    if m.get("rust_version"): meta.add_row("MSRV",        m["rust_version"])
    if m.get("keywords"):     meta.add_row("Keywords",    ", ".join(m["keywords"]))
    if m.get("categories"):   meta.add_row("Categories",  ", ".join(m["categories"]))
    if m.get("crate_size"):
        sz = m["crate_size"]
        meta.add_row("Crate size", f"{sz / 1024:.1f} KB" if sz < 1_000_000 else f"{sz / 1_048_576:.1f} MB")
    console.print(meta)

    # Injected files
    console.rule("[bold]Registry-Injected Files[/]")
    _INJECTED = [".cargo_vcs_info.json", "Cargo.toml", "Cargo.toml.orig"]
    if not inj:
        console.print("  [dim](none detected)[/]")
    for filename in _INJECTED:
        if filename not in inj:
            continue
        lines = inj[filename].splitlines()
        console.print(f"\n  [bold yellow]{filename}[/]  [dim]({len(lines)} lines)[/]")
        for line in lines[:8]:
            console.print(f"    [dim]{line}[/]")
        if len(lines) > 8:
            console.print(f"    [dim]... ({len(lines) - 8} more lines)[/]")

    # Normalization
    console.rule("[bold]Normalization[/]")
    stripped = norm.get("files_stripped", [])
    before   = norm.get("file_count_before", "?")
    after    = norm.get("file_count_after", "?")
    console.print(f"  Files stripped : [yellow]{', '.join(stripped) if stripped else 'none'}[/]")
    console.print(f"  File count     : {before} -> {after}")
    if norm.get("git_sha1"):
        console.print(f"  git sha1       : [dim]{norm['git_sha1']}[/]")
    if norm.get("is_monorepo"):
        console.print(f"  [yellow]Monorepo[/] path_in_vcs = '{norm['path_in_vcs']}'")

    # SWHID comparison
    console.rule("[bold]SWHID Verification[/]")
    computed = s.get("computed")
    from_swh = s.get("from_swh")
    match    = s.get("match")

    if computed:
        console.print(f"  [dim]Computed (stripped .crate):[/] [cyan]{computed}[/]")
    if from_swh:
        console.print(f"  [dim]SWH     (git commit root): [/] [cyan]swh:1:dir:{from_swh}[/]")

    if match is True:
        console.print("\n  [bold green]MATCH [OK][/] - Normalization confirmed.")
    elif match is False:
        console.print("\n  [bold red]MISMATCH [!!][/] - Hashes differ.")
    elif norm.get("is_monorepo"):
        console.print("\n  [yellow]SKIPPED[/] - Monorepo crate.")
    else:
        console.print("\n  [yellow]UNVERIFIED[/] - Revision not yet archived by Software Heritage.")

    # Verdict
    console.rule("[bold]Verdict[/]")
    if match is True:
        border = "green"
    elif match is False:
        border = "red"
    else:
        border = "yellow"
    console.print(Panel(
        f"[bold]{analysis['verdict']}[/]\n\n[dim]{analysis['explanation']}[/]",
        border_style=border, expand=False,
    ))

    # Scores
    console.rule("[bold]Supply Chain Security Scores[/]")
    _render_scores(scores)


# ---------------------------------------------------------------------------
# Findings persistence
# ---------------------------------------------------------------------------

def _save_findings(findings, name, version, ecosystem):
    os.makedirs("findings", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"findings/{ecosystem}-{name}-{version}-{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2, default=str)
    return path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="PURL -> SWHID Supply Chain Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python analyze.py pkg:pypi/six@1.17.0
  python analyze.py pkg:cargo/serde@1.0.203
  python analyze.py pkg:pypi/torch@2.6.0
  python analyze.py pkg:pypi/certifi@2024.12.14 --format json
  python analyze.py --ecosystem pypi --name six --version 1.17.0
        """,
    )
    ap.add_argument("purl", nargs="?", help="Package URL, e.g. pkg:pypi/six@1.17.0")
    ap.add_argument("--ecosystem", choices=["pypi", "cargo"])
    ap.add_argument("--name")
    ap.add_argument("--version")
    ap.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )
    ap.add_argument(
        "--no-save", action="store_true",
        help="Skip saving JSON findings to findings/",
    )
    args = ap.parse_args()

    # Resolve ecosystem / name / version
    if args.purl:
        ecosystem, name, version = parse_purl(args.purl)
        purl = args.purl
    elif args.ecosystem and args.name and args.version:
        ecosystem = args.ecosystem
        name      = args.name
        version   = args.version
        purl      = f"pkg:{ecosystem}/{name}@{version}"
    else:
        ap.print_help()
        sys.exit(1)

    # Run analysis behind a spinner
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(f"Analyzing {purl} …", total=None)

        if ecosystem == "pypi":
            findings = pypi_analyzer.analyze(name, version, purl)
        elif ecosystem == "cargo":
            findings = crates_analyzer.analyze(name, version, purl)
        else:
            console.print(f"[red]Unsupported ecosystem: {ecosystem}[/]")
            sys.exit(1)

    # Output
    if args.format == "json":
        console.print_json(json.dumps(findings, default=str))
    else:
        console.print()
        if ecosystem == "pypi":
            _render_pypi(findings)
        else:
            _render_cargo(findings)
        console.print()

    # Persist
    if not args.no_save:
        path = _save_findings(findings, name, version, ecosystem)
        console.print(f"[dim]Findings saved -> {path}[/]\n")


if __name__ == "__main__":
    main()
