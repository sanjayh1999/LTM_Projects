from __future__ import annotations

import re
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement

FROM_RE = re.compile(r"^FROM\s+(?P<image>\S+)(?:\s+AS\s+(?P<alias>\S+))?", re.IGNORECASE)
PIP_INSTALL_RE = re.compile(r"pip3?\s+install\s+(.+)", re.IGNORECASE)

FLAGS_WITH_VALUE = {
    "-r", "--requirement", "-c", "--constraint", "-i", "--index-url",
    "--extra-index-url", "-e", "--editable", "-f", "--find-links",
}


def parse_dockerfile(path: str) -> dict:
    text = Path(path).read_text(errors="ignore")
    text = text.replace("\\\r\n", " ").replace("\\\n", " ")  # join line continuations

    stages = []
    pip_requirements = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        m = FROM_RE.match(line)
        if m:
            stages.append({"image": m.group("image"), "alias": m.group("alias")})
            continue

        if line.upper().startswith("RUN"):
            for sub in line[3:].split("&&"):
                pip_match = PIP_INSTALL_RE.search(sub.strip())
                if pip_match:
                    pip_requirements.extend(_parse_pip_install_args(pip_match.group(1)))

    # A stage that's just an alias for an earlier stage isn't a real base image;
    # dedupe while preserving order, since the same real image can appear in multiple stages.
    aliases = {s["alias"] for s in stages if s["alias"]}
    base_images = list(dict.fromkeys(s["image"] for s in stages if s["image"] not in aliases))

    return {"stages": stages, "base_images": base_images, "pip_requirements": pip_requirements}


def _parse_pip_install_args(args_str: str) -> list[dict]:
    tokens = args_str.split()
    results = []
    skip_next = False

    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in FLAGS_WITH_VALUE:
            skip_next = True
            continue
        if tok.startswith("-"):
            continue

        try:
            req = Requirement(tok.strip("\"'"))
        except InvalidRequirement:
            continue

        results.append({
            "package_name": req.name,
            "version_spec": str(req.specifier) if req.specifier else None,
            "extras": ",".join(sorted(req.extras)) if req.extras else None,
            "marker": None,
        })

    return results


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "Dockerfile"
    result = parse_dockerfile(path)

    print(f"Base image(s): {result['base_images']}\n")
    print("All FROM stages:")
    for s in result["stages"]:
        alias = f"  (as {s['alias']})" if s["alias"] else ""
        print(f"  {s['image']}{alias}")

    print(f"\nPackages pinned via RUN pip install: {len(result['pip_requirements'])}")
    for r in result["pip_requirements"]:
        extras = f"[{r['extras']}]" if r["extras"] else ""
        spec = r["version_spec"] or "(any version)"
        print(f"  {r['package_name']}{extras} {spec}")