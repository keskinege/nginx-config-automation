#!/usr/bin/env python3
"""Validate repo-level template inputs before rendering."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_yaml(path: pathlib.Path) -> dict:
    return json.loads(subprocess.check_output(["yq", "-o=json", ".", str(path)]))


def template_names() -> set[str]:
    names = set()
    for meta in (ROOT / "templates").rglob("meta.yaml"):
        names.add(load_yaml(meta)["name"])
    return names


def walk_dirs(value, out: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "include_dirs" and isinstance(child, list):
                out.extend(str(v) for v in child)
            else:
                walk_dirs(child, out)
    elif isinstance(value, list):
        for child in value:
            walk_dirs(child, out)


def main() -> int:
    paths = [pathlib.Path(p) for p in sys.argv[1:]] or sorted(
        (ROOT / "groups").glob("*/inputs.yaml")
    )
    known = template_names()
    rc = 0
    for path in paths:
        body = load_yaml(path)
        base = (body.get("baseData") or {}).get("templateName")
        if base and base not in known:
            print(f"::error file={path}::unknown base template {base!r}", file=sys.stderr)
            rc = 1
        for aug in body.get("augmentData") or []:
            name = aug.get("templateName")
            if name and name not in known:
                print(f"::error file={path}::unknown augment template {name!r}", file=sys.stderr)
                rc = 1
        dirs: list[str] = []
        walk_dirs(body, dirs)
        for directory in dirs:
            if not directory.startswith("/etc/nginx/"):
                print(
                    f"::error file={path}::include dir {directory!r} must be under /etc/nginx",
                    file=sys.stderr,
                )
                rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
