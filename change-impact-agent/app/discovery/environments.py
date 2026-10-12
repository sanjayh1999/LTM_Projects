from __future__ import annotations

import os
from pathlib import Path

IGNORE_DIRS = {"node_modules", ".git", "__pycache__", "$RECYCLE.BIN", "System Volume Information"}


def find_virtualenvs(roots: list[str]) -> list[dict]:
    """Walk each root looking for pyvenv.cfg — the marker file every venv has."""
    found = []
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            if "pyvenv.cfg" in filenames:
                cfg = _parse_pyvenv_cfg(Path(dirpath) / "pyvenv.cfg")
                found.append({
                    "path": dirpath,
                    "python_version": cfg.get("version", ""),
                    "base_executable": cfg.get("home", ""),
                })
                dirnames[:] = []  # a venv's internals aren't worth descending into
    return found


def _parse_pyvenv_cfg(path: Path) -> dict:
    data = {}
    for line in path.read_text(errors="ignore").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()
    return data


def venv_python_exe(venv_path: str) -> str:
    exe = Path(venv_path) / "Scripts" / "python.exe"
    return str(exe) if exe.exists() else ""


if __name__ == "__main__":
    import sys
    from app.discovery.interpreters import get_installed_packages

    default_roots = [str(Path.home() / "Desktop"), str(Path.home() / "Documents")]
    roots = sys.argv[1:] or default_roots

    venvs = find_virtualenvs(roots)
    print(f"Found {len(venvs)} virtualenv(s) under {roots}\n")
    for v in venvs:
        exe = venv_python_exe(v["path"])
        packages = get_installed_packages(exe) if exe else []
        print(f"{v['path']}")
        print(f"  python {v['python_version']}  (built from: {v['base_executable']})")
        print(f"  {len(packages)} packages installed")
        for pkg in packages[:5]:
            print(f"   - {pkg['name']} {pkg['version']}")
        if len(packages) > 5:
            print(f"   ... and {len(packages) - 5} more")
        print()