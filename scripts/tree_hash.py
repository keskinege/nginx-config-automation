#!/usr/bin/env python3
"""Canonical SHA-256 / CRC32 for an nginx config tree.

The digest covers every file recursively (including multiple conf.d/*.conf files),
so it changes when a file is added, removed, renamed, or edited.

Recipe (stable across runs and platforms):
  version prefix
  for each path sorted by POSIX relative path:
    len(path) as 8-byte big-endian | path UTF-8
    len(bytes) as 8-byte big-endian | file bytes

Usage:
  python3 scripts/tree_hash.py rendered/static-cluster
  python3 scripts/tree_hash.py groups/static-cluster --exclude group.yaml
  python3 scripts/tree_hash.py rendered/static-cluster --json
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import pathlib
import sys
import zlib

PREFIX = b"nginx-config-tree-v1\0"
EXCLUDED = {"render-manifest.txt", "render-lock.json", ".DS_Store"}


def _is_excluded(rel: str, name: str, patterns: tuple[str, ...]) -> bool:
    if name in EXCLUDED:
        return True
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def _strip_template_tags(data: bytes) -> bytes:
    if b"__templateTag=" not in data:
        return data
    return b"".join(
        line for line in data.splitlines(keepends=True)
        if b"__templateTag=" not in line
    )


def hash_files(files: dict[str, bytes], strip_template_tags: bool = False) -> dict[str, object]:
    """Hash a mapping of POSIX relative path -> bytes."""
    sha = hashlib.sha256()
    sha.update(PREFIX)
    crc = zlib.crc32(PREFIX)
    total = 0

    for name in sorted(files):
        data = files[name]
        if strip_template_tags:
            data = _strip_template_tags(data)
        encoded = name.encode("utf-8")
        for chunk in (
            len(encoded).to_bytes(8, "big"),
            encoded,
            len(data).to_bytes(8, "big"),
            data,
        ):
            sha.update(chunk)
            crc = zlib.crc32(chunk, crc)
        total += len(data)

    return {
        "sha256": sha.hexdigest(),
        "crc32": f"{crc & 0xFFFFFFFF:08x}",
        "files": len(files),
        "bytes": total,
    }


def hash_tree(
    root: str | pathlib.Path,
    excludes: tuple[str, ...] = (),
    strip_template_tags: bool = False,
) -> dict[str, object]:
    base = pathlib.Path(root)
    if not base.exists():
        raise SystemExit(f"no such path: {base}")

    if base.is_file():
        return hash_files({base.name: base.read_bytes()}, strip_template_tags)

    files: dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for filename in sorted(filenames):
            path = pathlib.Path(dirpath) / filename
            rel = path.relative_to(base).as_posix()
            if _is_excluded(rel, filename, excludes):
                continue
            if not path.is_file():
                continue
            files[rel] = path.read_bytes()

    return hash_files(files, strip_template_tags)


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonical hash of an nginx config tree.")
    parser.add_argument("path", help="Directory (or single file) to hash.")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob or exact name to skip; repeatable (e.g. group.yaml).",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON object.")
    parser.add_argument(
        "--strip-template-tags",
        action="store_true",
        help="Ignore generated `# __templateTag=...` comments when hashing.",
    )
    args = parser.parse_args()

    info = hash_tree(args.path, tuple(args.exclude), args.strip_template_tags)
    if args.json:
        print(json.dumps(info, sort_keys=True))
    else:
        for key in ("sha256", "crc32", "files", "bytes"):
            print(f"{key}={info[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
