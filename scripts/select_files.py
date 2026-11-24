"""One definition of "the files NIM manages" for publish and tree_hash.

Kept in one place so the payload and the drift hash cannot diverge: a file the
publisher skips must also be skipped by the hash, or drift is permanent.
"""
from __future__ import annotations

import pathlib

# Repository metadata, never sent to NIM.
NON_MANAGED = {"group.yaml", "inputs.yaml", "render-manifest.txt", ".DS_Store"}


def managed(rel: str) -> bool:
    """True when a POSIX relative path belongs in the payload and in the hash."""
    parts = rel.split("/")
    if any(part.startswith(".") for part in parts):
        return False
    name = parts[-1]
    if name in NON_MANAGED or name.endswith(".lock.json"):
        return False
    return True


def iter_managed(root: str | pathlib.Path):
    """Yield (relative posix path, bytes) for every managed file under root."""
    base = pathlib.Path(root)
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base).as_posix()
        if not managed(rel):
            continue
        yield rel, path.read_bytes()
