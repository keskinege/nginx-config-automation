from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
TEXT = (REPO / "docs/runbooks/rollback.md").read_text()


def test_static_rollback_uses_current_code():
    assert "git switch --detach" not in TEXT
    assert "git restore --source=<good-sha>" in TEXT
    assert "groups/static-cluster" in TEXT


def test_template_rollback_reverts_the_commit():
    assert "revert" in TEXT.lower()
    assert "drift" in TEXT.lower()
