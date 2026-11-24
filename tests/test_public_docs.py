from __future__ import annotations

import pathlib
import re
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]

# Shapes, not values. This file is itself public, so it must not contain the
# identifiers it forbids — otherwise the guard re-publishes what it guards.
PATTERNS = {
    "tailnet MagicDNS name": r"[A-Za-z0-9-]+\.tail[0-9a-f]+\.ts\.net",
    "tailnet domain": r"\bts\.net\b",
    "host alias": r"\bovh-[a-z]{2}\b",
    "install path": r"/home/[a-z][a-z0-9_-]*/(nim|nginx)",
    "container id": r"\b[0-9a-f]{12}_nim-",
    "htpasswd hash": r"\bapr1\b",
    "bootstrap file": r"admin[_ -]?passw",
    "data volume": r"\bnim[n_-]nim-",
    "gitops repo": r"\bk3s-[a-z]{2}\b",
    "public listener": r"\b0\.0\.0\.0:(80|443)\b",
    "member hostname": r"\bplus-(docker|k8s)-[0-9]+\b",
}
COMPILED = {name: re.compile(pattern) for name, pattern in PATTERNS.items()}

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
        for name, rx in COMPILED.items():
            for match in rx.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{rel}:{line}: {name}")
    assert not hits, "infrastructure identifiers in a public repo:\n" + "\n".join(hits)


def test_environments_page_holds_no_host_details():
    text = (REPO / "docs/reference/environments.md").read_text()
    for line in text.splitlines():
        assert "Compose directory" not in line, line
        assert "Container |" not in line, line
        assert "Bootstrap secret" not in line, line
