from __future__ import annotations

import json
import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def run_publish(mock_nim, group, config_dir, **extra):
    env = {
        **os.environ,
        "GROUP": group,
        "CONFIG_DIR": str(config_dir),
        "NIM_URL": mock_nim.base_url,
        "NIM_USER": "u",
        "NIM_PASSWORD": "p",
        "EXTERNAL_ID": "abc123",
        **{k: str(v) for k, v in extra.items()},
    }
    return subprocess.run(
        [str(REPO / "scripts" / "publish.sh")],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
    )


def test_dry_run_lists_files_and_never_posts(mock_nim, tmp_path):
    tree = tmp_path / "tree"
    (tree / "conf.d").mkdir(parents=True)
    (tree / "nginx.conf").write_text("events {}\n")
    (tree / "conf.d" / "a.conf").write_text("server {}\n")
    (tree / "render-manifest.txt").write_text("ignored\n")

    result = run_publish(mock_nim, "test-group", tree, DRY_RUN=1)
    assert result.returncode == 0, result.stderr
    assert "/etc/nginx/nginx.conf" in result.stdout
    assert "/etc/nginx/conf.d/a.conf" in result.stdout
    assert "render-manifest.txt" not in result.stdout
    assert not [r for r in mock_nim.requests if r[0] == "POST"]


def test_preserve_aux_keeps_current_aux_files(mock_nim, tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "nginx.conf").write_text("events {}\n")

    result = run_publish(mock_nim, "test-group", tree, DRY_RUN=1, PRESERVE_AUX=1)
    assert result.returncode == 0, result.stderr
    payload_path = next(
        line.split("=", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("payload=")
    )
    payload = json.loads(pathlib.Path(payload_path).read_text())
    assert any(
        item["name"] == "/etc/nginx/tls/tls.crt"
        for item in payload["auxFiles"]["files"]
    )


def test_dot_directories_are_not_published(mock_nim, tmp_path):
    tree = tmp_path / "tree"
    (tree / ".vscode").mkdir(parents=True)
    (tree / ".vscode" / "settings.json").write_text("{}\n")
    (tree / "nginx.conf").write_text("events {}\n")
    result = run_publish(mock_nim, "test-group", tree, DRY_RUN=1)
    assert result.returncode == 0, result.stderr
    assert ".vscode" not in result.stdout


def test_post_is_not_retried_and_a_lost_response_is_recovered(mock_nim, tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "nginx.conf").write_text("events {}\n")
    mock_nim.drop_next_post = True

    result = run_publish(mock_nim, "test-group", tree)
    posts = [r for r in mock_nim.requests if r[0] == "POST" and r[1].endswith("/config")]
    assert len(posts) == 1, f"POST retried {len(posts)} times"
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_silent_member_fails_the_publish(mock_nim, tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "nginx.conf").write_text("events {}\n")
    mock_nim.group_instances = [{"name": "m1"}, {"name": "m2"}]  # deployment reports 1

    result = run_publish(mock_nim, "test-group", tree)
    assert result.returncode == 1
    assert "did not report" in (result.stdout + result.stderr)


def test_allow_partial_accepts_a_silent_member(mock_nim, tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "nginx.conf").write_text("events {}\n")
    mock_nim.group_instances = [{"name": "m1"}, {"name": "m2"}]

    result = run_publish(mock_nim, "test-group", tree, ALLOW_PARTIAL=1)
    assert result.returncode == 0, result.stdout + result.stderr


def test_member_count_falls_back_to_the_group_document(mock_nim, tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "nginx.conf").write_text("events {}\n")
    mock_nim.list_includes_instances = False
    mock_nim.group_instances = [{"name": "m1"}, {"name": "m2"}]  # deployment reports 1

    result = run_publish(mock_nim, "test-group", tree)
    assert result.returncode == 1
    assert "did not report" in (result.stdout + result.stderr)
