from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]

META = """name: x
type: base
state: draft
description: test template
files:
  - source: base.tmpl
"""


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def write_template(tmp_path, content="events {}\n"):
    root = tmp_path / "templates" / "base" / "x"
    root.mkdir(parents=True)
    (root / "meta.yaml").write_text(META)
    (root / "base.tmpl").write_text(content)


def run_sync(mock_nim, tmp_path, *args):
    env = {
        **os.environ,
        "NIM_URL": mock_nim.base_url,
        "NIM_USER": "u",
        "NIM_PASSWORD": "p",
        "TEMPLATES_DIR": str(tmp_path / "templates"),
        "LOCK_FILE": str(tmp_path / "lock.json"),
    }
    return subprocess.run(
        ["python3", "scripts/sync_templates.py", *args],
        cwd=REPO, env=env, text=True, capture_output=True,
    )


def set_remote(mock_nim, content="events {}\n", extra=None):
    mock_nim.templates = [{
        "name": "x", "uid": "tpl-x", "description": "test template",
        "state": "draft", "analyzedState": "valid", "type": "base",
        "isFactory": False, "hasSubmissions": False,
        "createTime": "x", "updateTime": "y",
    }]
    files = {
        "base.tmpl": {
            "name": "base.tmpl", "type": "config",
            "content": b64(content), "uid": "file-1",
        }
    }
    if extra:
        files.update(extra)
    mock_nim.template_files["tpl-x"] = files


def test_check_in_sync(mock_nim, tmp_path):
    write_template(tmp_path)
    set_remote(mock_nim)
    result = run_sync(mock_nim, tmp_path, "--all", "--check")
    assert result.returncode == 0, result.stderr
    assert "in sync" in result.stdout


def test_check_reports_content_drift(mock_nim, tmp_path):
    write_template(tmp_path, "events { listen 80; }\n")
    set_remote(mock_nim, "events {}\n")
    result = run_sync(mock_nim, tmp_path, "--all", "--check")
    assert result.returncode == 2
    assert "content differs" in result.stderr


def test_create_missing_template(mock_nim, tmp_path):
    write_template(tmp_path)
    mock_nim.templates = []
    result = run_sync(mock_nim, tmp_path, "--all")
    assert result.returncode == 0, result.stderr
    assert any(r[0] == "POST" and r[1] == "/api/platform/v1/conf-templates"
               for r in mock_nim.requests)
    lock = json.loads((tmp_path / "lock.json").read_text())
    assert lock["x"]["uid"] == "new-1"


def test_update_changed_file(mock_nim, tmp_path):
    write_template(tmp_path, "events { listen 81; }\n")
    set_remote(mock_nim, "events {}\n")
    result = run_sync(mock_nim, tmp_path, "--all")
    assert result.returncode == 0, result.stderr
    assert any(r[0] == "PUT" and r[1].endswith("/conf-templates/tpl-x/files/file-1")
               for r in mock_nim.requests)


def test_add_missing_file(mock_nim, tmp_path):
    write_template(tmp_path)
    set_remote(mock_nim)
    mock_nim.template_files["tpl-x"] = {}
    result = run_sync(mock_nim, tmp_path, "--all")
    assert result.returncode == 0, result.stderr
    assert any(r[0] == "POST" and r[1].endswith("/conf-templates/tpl-x/files")
               for r in mock_nim.requests)


def test_delete_extra_file(mock_nim, tmp_path):
    write_template(tmp_path)
    set_remote(mock_nim, extra={
        "extra.conf": {
            "name": "extra.conf", "type": "aux",
            "content": b64("types {}\n"), "uid": "file-2",
        }
    })
    result = run_sync(mock_nim, tmp_path, "--all")
    assert result.returncode == 0, result.stderr
    assert any(r[0] == "DELETE" and r[1].endswith("/conf-templates/tpl-x/files/file-2")
               for r in mock_nim.requests)


def test_dry_run_makes_no_writes(mock_nim, tmp_path):
    write_template(tmp_path, "events { listen 81; }\n")
    set_remote(mock_nim, "events {}\n")
    result = run_sync(mock_nim, tmp_path, "--all", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert not [r for r in mock_nim.requests if r[0] in {"PUT", "POST", "DELETE"}]


def test_check_reports_a_recreated_template(mock_nim, tmp_path):
    write_template(tmp_path)
    set_remote(mock_nim)
    (tmp_path / "lock.json").write_text(json.dumps({"x": "tpl-old"}))
    result = run_sync(mock_nim, tmp_path, "--all", "--check")
    assert result.returncode == 2
    assert "recreated" in result.stderr
