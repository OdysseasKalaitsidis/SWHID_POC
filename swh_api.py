import requests

SWH_API = "https://archive.softwareheritage.org/api/1"

def fetch_directory_hash_for_revision(sha1):
    """Return the SWH directory hash for a git commit sha1, or None if not archived."""
    resp = requests.get(f"{SWH_API}/revision/{sha1}/")
    if resp.status_code == 404:
        return None
    if resp.status_code == 429:
        raise RuntimeError("SWH API rate limit reached — try again later")
    resp.raise_for_status()
    return resp.json()["directory"]

def verify_directory(dir_hash):
    """Return True if the directory hash exists in the SWH archive."""
    resp = requests.get(f"{SWH_API}/directory/{dir_hash}/")
    return resp.status_code == 200
