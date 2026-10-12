from __future__ import annotations

import os
from pathlib import Path

import git

IGNORE_DIRS = {"node_modules", "__pycache__", "$RECYCLE.BIN", "System Volume Information"}


def find_git_repos(roots: list[str]) -> list[dict]:
    found = []
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            if ".git" in dirnames:
                info = _inspect_repo(dirpath)
                if info:
                    found.append(info)
                dirnames[:] = [d for d in dirnames if d != ".git"]
    return found


def _inspect_repo(path: str) -> dict | None:
    try:
        repo = git.Repo(path)
        remote_url = repo.remotes[0].url if repo.remotes else None
        try:
            branch = repo.active_branch.name
        except TypeError:
            branch = None  # detached HEAD
        commit = repo.head.commit
        return {
            "path": path,
            "remote_url": remote_url,
            "branch": branch,
            "last_commit_hash": commit.hexsha,
            "last_commit_at": commit.committed_datetime,
        }
    except Exception:
        return None


if __name__ == "__main__":
    import sys

    default_roots = [str(Path.home() / "Desktop"), str(Path.home() / "Documents")]
    roots = sys.argv[1:] or default_roots

    repos = find_git_repos(roots)
    print(f"Found {len(repos)} git repo(s)\n")
    for r in repos:
        print(r["path"])
        print(f"  branch: {r['branch']}   remote: {r['remote_url']}")
        print(f"  last commit: {r['last_commit_hash'][:8]}  at {r['last_commit_at'].isoformat()}")
        print()