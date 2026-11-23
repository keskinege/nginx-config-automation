from __future__ import annotations

import base64
import json
import os
import pathlib
import shutil
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def run_backup(mock_nim, out_dir, **extra):
    env = {
        **os.environ,
        "GROUP": "test-group",
        "NIM_URL": mock_nim.base_url,
        "NIM_USER": "u",
        "NIM_PASSWORD": "p",
        "OUT_DIR": str(out_dir),
        "EXTERNAL_ID": "abc123",
        **{k: str(v) for k, v in extra.items()},
    }
    return subprocess.run(
        [str(REPO / "scripts" / "backup-config.sh")],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
    )


def test_backup_redacts_endpoint_and_omits_url(mock_nim, tmp_path):
    group = REPO / "groups" / "test-group"
    group.mkdir(parents=True, exist_ok=True)
    try:
        out = tmp_path / "backup"
        result = run_backup(mock_nim, out, NIM_MGMT_ENDPOINT="real.example")
        assert result.returncode == 0, result.stderr

        manifest = (out / "manifest.txt").read_text()
        assert "nim_url" not in manifest
        assert "real.example" not in manifest
        assert "instance_group=test-group" in manifest

        config = (out / "etc/nginx/nginx.conf").read_text()
        assert "nim-mgmt-endpoint.invalid" in config
        assert "real.example" not in config

        payload = json.loads((out / "group-config.json").read_text())
        contents = base64.b64decode(
            payload["configFiles"]["files"][0]["contents"]
        ).decode()
        assert "nim-mgmt-endpoint.invalid" in contents
        assert "real.example" not in contents
    finally:
        shutil.rmtree(group, ignore_errors=True)


def test_backup_requires_the_endpoint(mock_nim, tmp_path):
    group = REPO / "groups" / "test-group"
    group.mkdir(parents=True, exist_ok=True)
    try:
        result = run_backup(mock_nim, tmp_path / "backup")
        assert result.returncode != 0
        assert "set NIM_MGMT_ENDPOINT" in result.stderr
    finally:
        shutil.rmtree(group, ignore_errors=True)
