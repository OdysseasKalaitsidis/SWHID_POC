import requests
import xml.etree.ElementTree as ET
from rich.table import Table
from rich.console import Console

MAVEN_CENTRAL = "https://repo1.maven.org/maven2"

PACKAGES = [
    "com.google.guava:guava:33.0.0-jre",
    "junit:junit:4.13.2",
    "org.springframework:spring-core:6.1.4",
    "com.fasterxml.jackson.core:jackson-databind:2.17.0",
    "org.slf4j:slf4j-api:2.0.12",
    "org.apache.commons:commons-lang3:3.14.0",
    "commons-io:commons-io:2.15.1",
    "org.apache.httpcomponents:httpclient:4.5.14",
    "com.google.code.gson:gson:2.10.1",
    "org.mockito:mockito-core:5.10.0",
    "log4j:log4j:1.2.17",
    "org.projectlombok:lombok:1.18.30",
    "io.netty:netty-all:4.1.107.Final",
]

# The standard Maven POM namespace
NS = "http://maven.apache.org/POM/4.0.0"


def coords_to_base_url(coords):
    group_id, artifact_id, version = coords.split(":")
    group_path = group_id.replace(".", "/")
    return f"{MAVEN_CENTRAL}/{group_path}/{artifact_id}/{version}/{artifact_id}-{version}"


def fetch_pom(base_url):
    try:
        resp = requests.get(base_url + ".pom", timeout=10)
        if resp.status_code == 200:
            return resp.text
    except requests.RequestException:
        pass
    return None


def parse_scm(pom_text):
    root = ET.fromstring(pom_text)

    # Some POMs use the namespace, some don't — try both
    def find(element, tag):
        node = element.find(f"{{{NS}}}{tag}")
        if node is None:
            node = element.find(tag)
        return node

    scm = find(root, "scm")
    if scm is None:
        return {"has_scm": False, "url": False, "connection": False, "tag": False}

    def has_field(tag):
        node = find(scm, tag)
        return node is not None and (node.text or "").strip() != ""

    return {
        "has_scm": True,
        "url": has_field("url"),
        "connection": has_field("connection"),
        "tag": has_field("tag"),
    }


def check_sources_jar(base_url):
    try:
        resp = requests.head(base_url + "-sources.jar", timeout=10)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def analyze_package(coords):
    base_url = coords_to_base_url(coords)

    pom_text = fetch_pom(base_url)
    if pom_text is None:
        return {
            "coords": coords,
            "pom_ok": False,
            "has_scm": False,
            "scm_url": False,
            "scm_connection": False,
            "scm_tag": False,
            "sources_jar": False,
        }

    scm = parse_scm(pom_text)
    sources = check_sources_jar(base_url)

    return {
        "coords": coords,
        "pom_ok": True,
        "has_scm": scm["has_scm"],
        "scm_url": scm["url"],
        "scm_connection": scm["connection"],
        "scm_tag": scm["tag"],
        "sources_jar": sources,
    }


def print_results(results):
    console = Console()
    table = Table(title="Maven Package SCM + Sources Analysis")

    table.add_column("Package", style="cyan", no_wrap=True)
    table.add_column("POM", justify="center")
    table.add_column("SCM block", justify="center")
    table.add_column("scm.url", justify="center")
    table.add_column("scm.connection", justify="center")
    table.add_column("scm.tag", justify="center")
    table.add_column("-sources.jar", justify="center")

    def yes(val):
        return "[green]yes[/green]" if val else "[red]no[/red]"

    for r in results:
        table.add_row(
            r["coords"],
            yes(r["pom_ok"]),
            yes(r["has_scm"]) if r["pom_ok"] else "[dim]-[/dim]",
            yes(r["scm_url"]) if r["has_scm"] else "[dim]-[/dim]",
            yes(r["scm_connection"]) if r["has_scm"] else "[dim]-[/dim]",
            yes(r["scm_tag"]) if r["has_scm"] else "[dim]-[/dim]",
            yes(r["sources_jar"]) if r["pom_ok"] else "[dim]-[/dim]",
        )

    console.print(table)


def main():
    print(f"Analyzing {len(PACKAGES)} Maven packages...\n")
    results = []
    for coords in PACKAGES:
        print(f"  checking {coords} ...")
        results.append(analyze_package(coords))
    print()
    print_results(results)

    has_scm_count = sum(1 for r in results if r["has_scm"])
    has_sources_count = sum(1 for r in results if r["sources_jar"])

    return {
        "packages_surveyed": len(results),
        "packages_with_scm_block": has_scm_count,
        "packages_with_sources_jar": has_sources_count,
        "results": results,
        "finding": (
            f"{has_scm_count}/{len(results)} packages have an <scm> block; "
            f"{has_sources_count}/{len(results)} have a -sources.jar"
        ),
    }


if __name__ == "__main__":
    main()
