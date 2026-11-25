from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_restore_substitutes_the_endpoint(mock_nim, tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    config = (
        "events {}\n"
        "http { include /etc/nginx/conf.d/*.conf; }\n"
        "mgmt { usage_report endpoint=nim-mgmt-endpoint.invalid; }\n"
    )
    (backup / "group-config.json").write_text(json.dumps({
        "updateTime": "2026-01-01T00:00:00Z",
        "configFiles": {
            "rootDir": "/etc/nginx",
            "files": [{
                "name": "/etc/nginx/nginx.conf",
                "contents": base64.b64encode(config.encode()).decode(),
            }],
        },
        "auxFiles": {"rootDir": "/", "files": []},
    }))

    env = {
        **os.environ,
        "GROUP": "test-group",
        "BACKUP_DIR": str(backup),
        "NIM_URL": mock_nim.base_url,
        "NIM_USER": "u",
        "NIM_PASSWORD": "p",
        "NIM_MGMT_ENDPOINT": "real.example",
    }
    env.pop("NIM_HOST", None)
    result = subprocess.run(
        [str(REPO / "scripts" / "restore.sh")],
        cwd=REPO, env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    post = next(
        body for method, path, body in mock_nim.requests
        if method == "POST" and path.endswith("/instance-groups/group-1/config")
    )
    contents = base64.b64decode(
        post["configFiles"]["files"][0]["contents"]
    ).decode()
    assert "real.example" in contents
    assert "nim-mgmt-endpoint.invalid" not in contents


def test_restore_takes_aux_from_the_live_group(mock_nim, tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "group-config.json").write_text(json.dumps({
        "updateTime": "2026-01-01T00:00:00Z",
        "configFiles": {"rootDir": "/etc/nginx", "files": []},
        # The artifact records aux by name and digest only.
        "auxFiles": {"rootDir": "/", "files": [{
            "name": "/etc/nginx/tls/tls.crt",
            "sha256": __import__("hashlib").sha256(b"cert").hexdigest(),
        }]},
    }))
    env = {
        **os.environ,
        "GROUP": "test-group",
        "BACKUP_DIR": str(backup),
        "NIM_URL": mock_nim.base_url,
        "NIM_USER": "u",
        "NIM_PASSWORD": "p",
        "NIM_MGMT_ENDPOINT": "real.example",
    }
    env.pop("NIM_HOST", None)
    result = subprocess.run(
        [str(REPO / "scripts" / "restore.sh")],
        cwd=REPO, env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    post = next(
        body for method, path, body in mock_nim.requests
        if method == "POST" and path.endswith("/instance-groups/group-1/config")
    )
    aux = post["auxFiles"]["files"]
    assert aux and aux[0]["contents"], aux
