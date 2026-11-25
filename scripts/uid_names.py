"""Make a rendered tree hash independent of NIM template UIDs.

NIM names composed augment files after the augment template's UID
(`augments/http/<uid>.conf`). A template in a throwaway namespace therefore has
a different UID and a different filename, even though the config is identical.
Hashing the tree as-is would tie the lock to one namespace; renaming each UID to
its template name first makes the digest stable everywhere.
"""
from __future__ import annotations


def invert(resolved: dict) -> dict[str, str]:
    """{name: uid} (as render.sh writes it) -> {uid: name}."""
    return {
        str(uid): str(name)
        for name, uid in resolved.items()
        if uid
    }


def rename(rel: str, uid_to_name: dict[str, str]) -> str:
    if not uid_to_name:
        return rel
    parts = rel.split("/")
    for index, part in enumerate(parts):
        stem, dot, ext = part.rpartition(".")
        if dot and stem in uid_to_name:
            parts[index] = f"{uid_to_name[stem]}.{ext}"
    return "/".join(parts)


def rename_paths(files: dict[str, bytes], uid_to_name: dict[str, str]) -> dict[str, bytes]:
    if not uid_to_name:
        return files
    return {rename(rel, uid_to_name): data for rel, data in files.items()}
