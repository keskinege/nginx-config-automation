from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
CI = (REPO / ".github/workflows/ci.yml").read_text()
STATIC = (REPO / ".github/workflows/nginx-static.yml").read_text()
TEMPLATE = (REPO / ".github/workflows/nginx-template.yml").read_text()


def test_static_detection_is_not_hard_coded_to_one_group():
    assert "groups/static-cluster/" not in CI
    assert "detect-groups.sh static" in CI


def test_static_publish_validates_before_publishing():
    before_publish = STATIC.split("publish group tree", 1)[0]
    assert "./scripts/lint.sh" in before_publish
    assert "nginx-test-dir.sh" in before_publish


def _steps(text):
    import yaml

    doc = yaml.safe_load(text)
    for job in doc["jobs"].values():
        for step in job.get("steps", []) or []:
            yield step


def test_f5_secrets_live_in_an_environment():
    assert "NGINX_REPO_CRT" in CI
    assert "environment: validate" in CI


def test_secrets_are_not_interpolated_inside_run_blocks():
    for name, text in (("ci", CI), ("static", STATIC), ("template", TEMPLATE)):
        for step in _steps(text):
            run = step.get("run") or ""
            assert "${{ secrets." not in run, f"{name}: secret inside run: block"
