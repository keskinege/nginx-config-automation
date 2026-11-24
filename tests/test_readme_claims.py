from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text()

STALE = [
    "90-day artifact",
    "or by a future sync script",
    "keep the repo private",
    "call curl with `-k`",
    "this NIM exposes no scoped\nservice account",
    "NIM_URL=https://<nim-host>",
]


def test_readme_has_no_stale_claims():
    for phrase in STALE:
        assert phrase not in README, f"stale README claim: {phrase!r}"


def test_readme_describes_the_current_security_model():
    assert "ci-validator" in README
    assert "certs/nim-ca.pem" in README
    assert "https://manager-server" in README
    assert "7-day artifact" in README
