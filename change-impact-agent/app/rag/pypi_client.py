from __future__ import annotations

import requests


def fetch_package_metadata(name: str, version: str | None = None) -> dict | None:
    """Fetch a package's metadata from PyPI's JSON API — either the latest version,
    or a specific one if given."""
    url = f"https://pypi.org/pypi/{name}/{version}/json" if version else f"https://pypi.org/pypi/{name}/json"

    try:
        resp = requests.get(url, timeout=10)
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None

    data = resp.json()
    info = data.get("info", {})

    return {
        "name": info.get("name", name),
        "version": info.get("version"),
        "summary": info.get("summary") or "",
        "description": info.get("description") or "",
        "requires_python": info.get("requires_python"),
        "project_url": info.get("project_url") or f"https://pypi.org/project/{name}/",
    }


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "numpy"
    version = sys.argv[2] if len(sys.argv) > 2 else None

    meta = fetch_package_metadata(name, version)
    if meta is None:
        print(f"Could not fetch metadata for {name} {version or '(latest)'}")
    else:
        print(f"{meta['name']} {meta['version']}")
        print(f"  requires_python: {meta['requires_python']}")
        print(f"  summary: {meta['summary']}")
        print(f"  description length: {len(meta['description'])} characters")