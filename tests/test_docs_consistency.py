from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
DOCS = {p.relative_to(REPO).as_posix(): p.read_text()
        for p in (REPO / "docs").rglob("*.md")}

STALE = {
    "docs/workflow.md": [
        "validator identity is not available yet",
        "OSS image, Plus block neutralised",
        "90-day artifact",
        "`scripts/list-groups.sh static|template` supplies the mode list",
    ],
    "docs/runbooks/static-vs-template.md": [
        "list-groups.sh static|template` is the source of truth",
        "`analyze` + compose",
        "`externalId` on compose + publish",
    ],
    "docs/runbooks/troubleshooting.md": ["CI keeps the pinned OSS image"],
    "docs/reference/prerequisites.md": ["nginx -t` in the pinned OSS image"],
    "docs/runbooks/naming-and-display-names.md": [
        "-sk",
        "lint + nginx -t",
        "validate template groups",
    ],
    "docs/runbooks/adding-configs-sites-and-clusters.md": ["-sk"],
}


def test_no_stale_doc_claims():
    hits = []
    for rel, phrases in STALE.items():
        for phrase in phrases:
            if phrase in DOCS[rel]:
                hits.append(f"{rel}: {phrase}")
    assert not hits, "\n".join(hits)


def test_public_files_page_is_merged():
    assert "docs/reference/public-files.md" not in DOCS
    assert "public-files.md" not in DOCS["docs/README.md"]
    settings = DOCS["docs/reference/repo-settings.md"]
    assert ".github/CODEOWNERS" in settings
    assert "No NIM address" in settings


def test_exit_codes_match_the_scripts():
    text = DOCS["docs/reference/exit-codes.md"]
    assert "| | 2 | drift with `--check`" in text
    assert "| | 2 | a group or rendered tree does not exist" in text


def test_nginx_test_script_header_names_the_plus_image():
    header = (REPO / "scripts/nginx-test.sh").read_text().splitlines()[1]
    assert "OSS image" not in header
    assert "Plus" in header
