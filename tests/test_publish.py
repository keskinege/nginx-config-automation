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
    payload = json.loads(pathlib.Path("/tmp/payload.json").read_text())
    assert any(
        item["name"] == "/etc/nginx/tls/tls.crt"
        for item in payload["auxFiles"]["files"]
    )
