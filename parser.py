import requests

CRATES_IO_HEADERS = {"User-Agent": "swhid-poc/0.1 (gsoc research)"}

def fetch_crate(name, version):
    url = f"https://crates.io/api/v1/crates/{name}/{version}"
    resp = requests.get(url, headers=CRATES_IO_HEADERS)
    resp.raise_for_status()
    data = resp.json()
    if data["version"]["yanked"]:
        raise ValueError(f"Crate {name} {version} is yanked")
    return f"https://static.crates.io/crates/{name}/{name}-{version}.crate"

def list_wheels(package_name, version):
    URL = f"https://pypi.org/pypi/{package_name}/{version}/json"
    resp = requests.get(URL)
    resp.raise_for_status()
    data = resp.json()

    wheels = []
    for file_info in data['urls']:
        if file_info['packagetype'] == 'bdist_wheel':
            # filename: name-ver-pythontag-abitag-platformtag.whl
            parts = file_info['filename'][:-4].split("-")  # strip .whl
            python_tag  = parts[2] if len(parts) > 2 else "?"
            abi_tag     = parts[3] if len(parts) > 3 else "?"
            platform_tag = parts[4] if len(parts) > 4 else "?"
            wheels.append({
                "filename": file_info['filename'],
                "url":      file_info['url'],
                "size":     file_info['size'],
                "python":   python_tag,
                "abi":      abi_tag,
                "platform": platform_tag,
            })
    return wheels

def fetch_package(package_name, version):

    URL = f"https://pypi.org/pypi/{package_name}/{version}/json"

    resp = requests.get(URL)
    resp.raise_for_status()
    data = resp.json()
    for file_info in data['urls']:
        if file_info['packagetype'] == 'sdist':
            return file_info['url']
    raise ValueError(f"No sdist found for {package_name} {version} on PyPI (wheels only?)")









