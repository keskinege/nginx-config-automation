from __future__ import annotations

import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]

FORBIDDEN = [
    "ovh-fr",
    "tail7fa79",
    "ts.net",
    "/home/debian",
    "f5c7fef825a8",
    "apr1",
    ".htpasswd",
    "admin_password.txt",
    "plus-docker-1",
    "plus-docker-2",
    "plus-k8s-1",
    "plus-k8s-2",
    "k3s-gh",
    "0.0.0.0:443",
    "nim_nim-data",
]

SUFFIXES = (".md", ".yaml", ".yml", ".conf", ".tmpl", ".json", ".sh", ".py")


def tracked_text_files():
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True
    )
    for raw in out.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode()
        if rel.startswith(("tests/", ".opencode/")):
            continue
        if rel.endswith(SUFFIXES) or rel in {"README.md", "SECURITY.md"}:
            yield rel, (REPO / rel).read_text(errors="replace")


def test_no_infrastructure_identifiers_in_tracked_files():
    hits = []
    for rel, text in tracked_text_files():
        for token in FORBIDDEN:
            if token in text:
                hits.append(f"{rel}: {token}")
    assert not hits, "infrastructure identifiers in a public repo:\n" + "\n".join(hits)


def test_environments_page_holds_no_host_details():
    text = (REPO / "docs/reference/environments.md").read_text()
    for line in text.splitlines():
        assert "Compose directory" not in line, line
        assert "Container |" not in line, line
        assert "Bootstrap secret" not in line, line
