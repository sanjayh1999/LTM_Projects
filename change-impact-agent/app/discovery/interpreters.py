from __future__ import annotations

import json
import re
import subprocess


def discover_interpreters() -> list[dict]:
    """Ask the `py` launcher what CPython installs it knows about."""
    result = subprocess.run(["py", "-0p"], capture_output=True, text=True)
    pattern = re.compile(r"-V:(?P<tag>[\d.]+)(?P<active>\s*\*)?\s+(?P<path>[A-Za-z]:\\.+?\.exe)\s*$")

    interpreters = []
    for line in result.stdout.splitlines():
        m = pattern.search(line.strip())
        if not m:
            continue
        path = m.group("path").strip()
        interpreters.append({
            "tag": m.group("tag"),
            "path": path,
            "version": _exact_version(path),
            "active_default": bool(m.group("active")),
        })
    return interpreters


def _exact_version(python_exe: str) -> str:
    result = subprocess.run([python_exe, "--version"], capture_output=True, text=True)
    text = (result.stdout or result.stderr).strip()
    return text.replace("Python ", "")


def get_installed_packages(python_exe: str) -> list[dict]:
    """Run a tiny script *inside* that interpreter to list what it has installed,
    including each package's own declared Requires-Python."""
    script = (
        "import importlib.metadata, json\n"
        "out = []\n"
        "for dist in importlib.metadata.distributions():\n"
        "    meta = dist.metadata\n"
        "    out.append({\n"
        "        'name': meta.get('Name'),\n"
        "        'version': dist.version,\n"
        "        'requires_python': meta.get('Requires-Python'),\n"
        "    })\n"
        "print(json.dumps(out))\n"
    )
    result = subprocess.run([python_exe, "-c", script], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return []
    return json.loads(result.stdout)


if __name__ == "__main__":
    for interp in discover_interpreters():
        print(f"\n{interp['version']}  ({'default' if interp['active_default'] else 'available'})  {interp['path']}")
        packages = get_installed_packages(interp["path"])
        print(f"  {len(packages)} packages installed")
        for pkg in packages[:5]:
            print(f"   - {pkg['name']} {pkg['version']}")
        if len(packages) > 5:
            print(f"   ... and {len(packages) - 5} more")