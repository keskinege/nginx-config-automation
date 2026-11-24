from __future__ import annotations

import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def make_group(tmp_path, require_mgmt="true      # keep usage reporting"):
    group = tmp_path / "groups" / "g"
    group.mkdir(parents=True)
    (group / "group.yaml").write_text(
        f"name: g\ndeploy_mode: static\nrequire_mgmt: {require_mgmt}\n"
    )
    (group / "nginx.conf").write_text(
        "events {}\n"
        "http {\n"
        "    include /etc/nginx/conf.d/*.conf;\n"
        "}\n"
    )
    (group / "conf.d").mkdir()
    (group / "conf.d" / "site.conf").write_text(
        "server { listen 80 default_server; }\n"
    )
    return group


def run_lint(repo, *args):
    return subprocess.run(
        [str(REPO / "scripts" / "lint.sh"), *args],
        cwd=repo, text=True, capture_output=True,
        env={**os.environ, "REPO_ROOT": str(repo)},
    )


def test_commented_require_mgmt_still_enforced(tmp_path):
    group = make_group(tmp_path)
    result = run_lint(tmp_path)
    assert result.returncode != 0
    assert "mgmt" in result.stdout

    (group / "nginx.conf").write_text(
        "events {}\n"
        "http {\n"
        "    include /etc/nginx/conf.d/*.conf;\n"
        "}\n"
        "mgmt { usage_report endpoint=nim-mgmt-endpoint.invalid; }\n"
    )
    result = run_lint(tmp_path)
    assert result.returncode == 0, result.stdout


def test_rendered_require_mgmt_mismatch_fails(tmp_path):
    group = make_group(tmp_path)
    (group / "inputs.yaml").write_text(
        "baseData:\n"
        "  templateName: nginx-base\n"
        "  main:\n"
        "    templateInput:\n"
        "      require_mgmt: false\n"
    )
    rendered = tmp_path / "rendered" / "g"
    rendered.mkdir(parents=True)
    (rendered / "nginx.conf").write_text(
        "events {}\n"
        "http {\n"
        "    include /etc/nginx/conf.d/*.conf;\n"
        "}\n"
        "mgmt { usage_report endpoint=nim-mgmt-endpoint.invalid; }\n"
    )
    (rendered / "conf.d").mkdir()
    (rendered / "conf.d" / "site.conf").write_text(
        "server { listen 80 default_server; }\n"
    )
    result = run_lint(tmp_path, "--rendered", "g")
    assert result.returncode != 0
    assert "does not match group.yaml" in result.stdout


def test_failing_group_is_not_reported_ok(tmp_path):
    group = make_group(tmp_path)
    (group / "nginx.conf").write_text(
        "events {}\nhttp {\n    include /etc/nginx/conf.d/*.conf;\n}\n"
    )
    result = run_lint(tmp_path)
    assert result.returncode == 1
    assert "lint: g ok" not in result.stdout
    assert "mgmt" in result.stdout


def test_lint_group_limits_the_scope(tmp_path):
    good = make_group(tmp_path)
    (good / "nginx.conf").write_text(
        "events {}\nhttp {\n    include /etc/nginx/conf.d/*.conf;\n}\n"
        "mgmt { usage_report endpoint=nim-mgmt-endpoint.invalid; }\n"
    )
    bad = tmp_path / "groups" / "broken"
    bad.mkdir(parents=True)
    (bad / "group.yaml").write_text("name: broken\ndeploy_mode: static\n")
    (bad / "nginx.conf").write_text("events {}\n")  # no include, no mgmt

    result = run_lint(tmp_path, "--group", "g")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "broken" not in result.stdout
