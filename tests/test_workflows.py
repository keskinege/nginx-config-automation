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


def test_drift_uses_the_read_only_validator():
    import yaml

    doc = yaml.safe_load(TEMPLATE)
    steps = doc["jobs"]["drift"]["steps"]
    env = {}
    for step in steps:
        env.update(step.get("env") or {})
    assert env.get("NIM_USER") == "${{ secrets.NIM_VALIDATOR_USER }}"


def test_pr_validation_uses_a_throwaway_template_namespace():
    assert "pr-${{ github.event.pull_request.number }}-${{ github.run_id }}-" in CI
    assert "TEMPLATE_PREFIX" in CI
    assert "--delete-prefix" in CI
    assert "NIM_TEMPLATE_WRITER_USER" in CI


def test_deploy_syncs_templates_before_rendering():
    sync = TEMPLATE.index("sync_templates.py --all")
    render = TEMPLATE.index("name: render from templates")
    assert sync < render


def test_the_render_lock_is_checked_in_every_namespace():
    assert "CHECK_HASH=1" in CI
    assert "outputs.hash" not in CI
