from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
CI = (REPO / ".github/workflows/ci.yml").read_text()
STATIC = (REPO / ".github/workflows/nginx-static.yml").read_text()
TEMPLATE = (REPO / ".github/workflows/nginx-template.yml").read_text()


def test_static_detection_is_not_hard_coded_to_one_group():
    assert "groups/static-cluster/" not in CI
    assert "detect-groups.sh static" in CI
