#!/usr/bin/env python3
"""Sync local `templates/` to NIM config templates.

Usage:
  python3 scripts/sync_templates.py --all
  python3 scripts/sync_templates.py --template nginx-base
  python3 scripts/sync_templates.py --all --check
  python3 scripts/sync_templates.py --all --dry-run

Env:
  NIM_URL, NIM_USER, NIM_PASSWORD
  TEMPLATES_DIR   default: templates
  LOCK_FILE       default: .nim/templates.lock.json
"""
from __future__ import annotations

from typing import NoReturn

import argparse
import base64
import hashlib
import json
import os
import pathlib
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def fail(message: str, code: int = 1) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(code)


def load_meta(path: pathlib.Path) -> dict:
    try:
        raw = subprocess.check_output(["yq", "-o=json", ".", str(path)], text=True)
    except FileNotFoundError:
        fail("sync_templates: yq is required to read meta.yaml")
    except subprocess.CalledProcessError as exc:
        fail(f"sync_templates: invalid {path}: {exc}")
    return json.loads(raw)


def local_templates(templates_dir: pathlib.Path) -> list[dict]:
    entries = []
    seen: set[str] = set()
    for meta_path in sorted(templates_dir.rglob("meta.yaml")):
        meta = load_meta(meta_path)
        name = meta["name"]
        if name in seen:
            fail(f"sync_templates: duplicate template name {name!r}")
        seen.add(name)
        files = {}
        for item in meta["files"]:
            source = meta_path.parent / item["source"]
            target = item.get("target") or source.name
            kind = "aux" if "target" in item else (
                "docs" if source.name == "README.md" else
                "schema" if source.suffix == ".json" else "config"
            )
            files[target] = {"type": kind, "content": source.read_bytes()}
        entries.append({"meta": meta, "root": meta_path.parent, "files": files})
    return entries


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class NIM:
    def __init__(self) -> None:
        self.base = (self.env("NIM_URL").rstrip("/") + "/api/platform/v1")
        user = self.env("NIM_USER")
        password = self.env("NIM_PASSWORD")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.auth = f"Basic {token}"
        self.context = ssl.create_default_context(
            cafile=os.environ.get("NIM_CA", "certs/nim-ca.pem")
        )
        # The internal apigw-svc CA predates the CA/B forum extensions. Python
        # 3.13+ enables VERIFY_X509_STRICT, which rejects it; curl accepts it.
        # Keep chain and hostname verification, drop only the extension check.
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            self.context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    @staticmethod
    def env(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            fail(f"sync_templates: set {name}")
        return value

    def request(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": self.auth, "Content-Type": "application/json"}
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.context, timeout=30) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            fail(f"sync_templates: {method} {path} -> HTTP {exc.code}: {raw[:1200]}")
        except urllib.error.URLError as exc:
            fail(f"sync_templates: {method} {path} -> {exc.reason}")

    def list_templates(self) -> dict[str, dict]:
        items: list[dict] = []
        offset = 0
        while True:
            _, page = self.request("GET", f"/conf-templates?limit=100&offset={offset}")
            page_items = page.get("items", [])
            items.extend(page_items)
            if len(page_items) < 100:
                break
            offset += 100
        return {item["name"]: item for item in items}

    def files(self, uid: str) -> dict[str, dict]:
        _, data = self.request("GET", f"/conf-templates/{uid}/files")
        return {item["name"]: item for item in data.get("items", [])}

    def create(self, entry: dict) -> dict:
        body = {
            "name": entry["meta"]["name"],
            "description": entry["meta"]["description"],
            "state": entry["meta"]["state"],
            "type": entry["meta"]["type"],
            "files": [
                {
                    "name": name,
                    "type": file["type"],
                    "content": base64.b64encode(file["content"]).decode(),
                }
                for name, file in entry["files"].items()
            ],
        }
        _, data = self.request("POST", "/conf-templates", body)
        if data.get("analyzedState") == "malformed":
            fail(
                f"sync_templates: {entry['meta']['name']} is malformed: "
                f"{data.get('analysisErrors')}"
            )
        return data

    def add_files(self, uid: str, files: dict[str, dict]) -> None:
        body = [
            {
                "name": name,
                "type": file["type"],
                "content": base64.b64encode(file["content"]).decode(),
            }
            for name, file in files.items()
        ]
        _, data = self.request("POST", f"/conf-templates/{uid}/files", body)
        if data.get("failures"):
            fail(f"sync_templates: add files failed: {data['failures']}")

    def update_file(self, uid: str, file_uid: str, name: str, file: dict) -> None:
        body = {
            "name": name,
            "type": file["type"],
            "content": base64.b64encode(file["content"]).decode(),
        }
        self.request("PUT", f"/conf-templates/{uid}/files/{file_uid}", body)

    def delete_file(self, uid: str, file_uid: str) -> None:
        self.request("DELETE", f"/conf-templates/{uid}/files/{file_uid}")


def load_lock(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(f"sync_templates: invalid lock {path}: {exc}")
    return data if isinstance(data, dict) else {}


def write_lock(path: pathlib.Path, lock: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")


def check(nim: NIM, local: list[dict], remote: dict[str, dict],
          lock: dict | None = None) -> int:
    lock = lock or {}
    drift: list[str] = []
    for entry in local:
        name = entry["meta"]["name"]
        item = remote.get(name)
        if not item:
            drift.append(f"{name}: missing in NIM")
            continue
        recorded = lock.get(name)
        if isinstance(recorded, dict):
            recorded = recorded.get("uid")
        if recorded and item.get("uid") and recorded != item["uid"]:
            drift.append(
                f"{name}: NIM UID {item['uid']} != lock {recorded} (recreated?)"
            )
        if item.get("type") != entry["meta"]["type"]:
            drift.append(f"{name}: type {item.get('type')} != {entry['meta']['type']}")
        remote_files = nim.files(item["uid"])
        for file_name, file in entry["files"].items():
            current = remote_files.get(file_name)
            if not current:
                drift.append(f"{name}: missing file {file_name}")
                continue
            if current.get("type") != file["type"]:
                drift.append(f"{name}: file {file_name} type differs")
            if base64.b64decode(current.get("content") or "") != file["content"]:
                drift.append(f"{name}: file {file_name} content differs")
        for file_name in sorted(set(remote_files) - set(entry["files"])):
            drift.append(f"{name}: extra file {file_name}")
    if drift:
        for line in drift:
            print(f"drift: {line}", file=sys.stderr)
        return 2
    print(f"sync: {len(local)} template(s) in sync")
    return 0


def apply(nim: NIM, local: list[dict], remote: dict[str, dict], lock_path: pathlib.Path,
          dry_run: bool, no_prune: bool) -> int:
    lock = load_lock(lock_path)
    for entry in local:
        name = entry["meta"]["name"]
        item = remote.get(name)
        if not item:
            print(f"sync: create {name}")
            if dry_run:
                continue
            created = nim.create(entry)
            uid = created["uid"]
            lock[name] = {"uid": uid, "files": {
                file_name: file_hash(file["content"])
                for file_name, file in entry["files"].items()
            }}
            print(f"sync: created {name} ({uid})")
            continue

        uid = item["uid"]
        remote_files = nim.files(uid)
        changed = False
        to_add = {
            file_name: file for file_name, file in entry["files"].items()
            if file_name not in remote_files
        }
        if to_add:
            print(f"sync: add {name}: {', '.join(sorted(to_add))}")
            if not dry_run:
                nim.add_files(uid, to_add)
            changed = True
        for file_name, file in entry["files"].items():
            current = remote_files.get(file_name)
            if not current:
                continue
            if base64.b64decode(current.get("content") or "") != file["content"] \
                    or current.get("type") != file["type"]:
                print(f"sync: update {name}: {file_name}")
                if not dry_run:
                    nim.update_file(uid, current["uid"], file_name, file)
                changed = True
        if not no_prune:
            for file_name in sorted(set(remote_files) - set(entry["files"])):
                print(f"sync: delete {name}: {file_name}")
                if not dry_run:
                    nim.delete_file(uid, remote_files[file_name]["uid"])
                changed = True
        if not changed:
            print(f"sync: unchanged {name}")
        lock[name] = {"uid": uid, "files": {
            file_name: file_hash(file["content"])
            for file_name, file in entry["files"].items()
        }}
    if not dry_run:
        write_lock(lock_path, lock)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync local templates to NIM.")
    parser.add_argument("--all", action="store_true", help="Sync every local template.")
    parser.add_argument("--template", help="Sync one template by name.")
    parser.add_argument("--check", action="store_true", help="Report drift; write nothing.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions; write nothing.")
    parser.add_argument("--no-prune", action="store_true", help="Do not delete extra remote files.")
    args = parser.parse_args()

    templates_dir = pathlib.Path(os.environ.get("TEMPLATES_DIR", ROOT / "templates"))
    lock_path = pathlib.Path(os.environ.get("LOCK_FILE", ROOT / ".nim" / "templates.lock.json"))
    if not templates_dir.is_dir():
        fail(f"sync_templates: no such templates directory: {templates_dir}")

    local = local_templates(templates_dir)
    if args.template:
        local = [entry for entry in local if entry["meta"]["name"] == args.template]
        if not local:
            fail(f"sync_templates: no local template named {args.template!r}")
    elif not args.all:
        args.all = True

    nim = NIM()
    remote = nim.list_templates()
    if args.check:
        return check(nim, local, remote, load_lock(lock_path))
    return apply(nim, local, remote, lock_path, args.dry_run, args.no_prune)


if __name__ == "__main__":
    sys.exit(main())
