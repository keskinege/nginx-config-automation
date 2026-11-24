from __future__ import annotations

import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]

FORBIDDEN = [
    "REDACTED-HOST",
    "REDACTED-HOST",
    "ts.net",
    "REDACTED-PATH",
    "REDACTED",
    "REDACTED-HASH",
    "REDACTED-FILE",
    "REDACTED-FILE",
    "REDACTED-MEMBER",
    "REDACTED-MEMBER",
    "REDACTED-MEMBER",
    "REDACTED-MEMBER",
    "REDACTED-REPO",
    "REDACTED-LISTENER",
    "REDACTED-VOLUME",
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
