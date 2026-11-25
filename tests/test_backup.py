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
        result = run_backup(mock_nim, tmp_path / "backup", NIM_MGMT_ENDPOINT="")
        assert result.returncode != 0
        assert "set NIM_MGMT_ENDPOINT" in result.stderr
    finally:
        shutil.rmtree(group, ignore_errors=True)


def test_backup_redacts_an_endpoint_that_differs_from_the_secret(mock_nim, tmp_path):
    group = REPO / "groups" / "test-group"
    group.mkdir(parents=True, exist_ok=True)
    try:
        out = tmp_path / "backup"
        # The live config holds real.example; the secret now holds a different value.
        result = run_backup(mock_nim, out, NIM_MGMT_ENDPOINT="rotated.example")
        assert result.returncode == 0, result.stderr
        config = (out / "etc/nginx/nginx.conf").read_text()
        assert "real.example" not in config
        assert "rotated.example" not in config
        assert "nim-mgmt-endpoint.invalid" in config
    finally:
        shutil.rmtree(group, ignore_errors=True)


def test_backup_does_not_upload_the_group_document(mock_nim, tmp_path):
    group = REPO / "groups" / "test-group"
    group.mkdir(parents=True, exist_ok=True)
    try:
        out = tmp_path / "backup"
        result = run_backup(mock_nim, out, NIM_MGMT_ENDPOINT="real.example")
        assert result.returncode == 0, result.stderr
        assert not (out / "group.json").exists()
        assert "members=" in (out / "manifest.txt").read_text()
    finally:
        shutil.rmtree(group, ignore_errors=True)


def test_backup_redacts_the_endpoint_anywhere_in_the_config(mock_nim, tmp_path):
    group = REPO / "groups" / "test-group"
    group.mkdir(parents=True, exist_ok=True)
    try:
        import base64 as b64mod

        mock_nim.group_config_files = [{
            "name": "/etc/nginx/nginx.conf",
            "contents": b64mod.b64encode(
            b"events {}\n"
            b"http {\n"
            b"  proxy_pass https://real.example;\n"
            b"  # upstream real.example\n"
            b"  mgmt { usage_report endpoint=real.example; }\n"
            b"}\n"
            ).decode(),
        }]
        out = tmp_path / "backup"
        result = run_backup(mock_nim, out, NIM_MGMT_ENDPOINT="real.example")
        assert result.returncode == 0, result.stderr
        config = (out / "etc/nginx/nginx.conf").read_text()
        assert "real.example" not in config, config
        assert "nim-mgmt-endpoint.invalid" in config
    finally:
        shutil.rmtree(group, ignore_errors=True)


def test_backup_keeps_aux_as_name_and_digest_only(mock_nim, tmp_path):
    group = REPO / "groups" / "test-group"
    group.mkdir(parents=True, exist_ok=True)
    try:
        out = tmp_path / "backup"
        result = run_backup(mock_nim, out, NIM_MGMT_ENDPOINT="real.example")
        assert result.returncode == 0, result.stderr
        assert not (out / "etc/nginx/tls/tls.crt").exists()
        payload = json.loads((out / "group-config.json").read_text())
        aux = payload["auxFiles"]["files"][0]
        assert aux["name"] == "/etc/nginx/tls/tls.crt"
        assert "contents" not in aux
        assert len(aux["sha256"]) == 64
        assert "aux=/etc/nginx/tls/tls.crt sha256=" in (out / "manifest.txt").read_text()
    finally:
        shutil.rmtree(group, ignore_errors=True)
