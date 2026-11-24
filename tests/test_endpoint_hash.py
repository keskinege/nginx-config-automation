from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def render(mock_nim, group, out, endpoint, lock):
    mock_nim.config_files[0]["contents"] = base64.b64encode(
        b"events {}\nmgmt { usage_report endpoint=nim-mgmt-endpoint.invalid; }\n"
    ).decode()
    env = {
        **os.environ, "GROUP": group, "NIM_URL": mock_nim.base_url,
        "NIM_USER": "u", "NIM_PASSWORD": "p", "OUT_DIR": str(out),
        "WRITE_HASH": "1", "HASH_FILE": str(lock),
    }
    if endpoint:
        env["NIM_MGMT_ENDPOINT"] = endpoint
    else:
        env.pop("NIM_MGMT_ENDPOINT", None)
    return subprocess.run(
        [str(REPO / "scripts" / "render.sh")],
        cwd=REPO, env=env, text=True, capture_output=True,
    )


def test_lock_is_independent_of_the_endpoint(mock_nim, repo_group, tmp_path):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    one = render(mock_nim, repo_group, tmp_path / "a", "one.example", first)
    two = render(mock_nim, repo_group, tmp_path / "b", "two.example", second)
    assert one.returncode == 0, one.stderr
    assert two.returncode == 0, two.stderr
    assert json.loads(first.read_text())[repo_group]["sha256"] == \
           json.loads(second.read_text())[repo_group]["sha256"]
    assert "two.example" in (tmp_path / "b" / "nginx.conf").read_text()


def test_refuses_to_publish_the_placeholder(mock_nim, repo_group, tmp_path):
    result = render(mock_nim, repo_group, tmp_path / "c", "", tmp_path / "c.json")
    assert result.returncode == 4
    assert "nim-mgmt-endpoint.invalid" in result.stderr


def test_normalization_leaves_other_occurrences_alone():
    from scripts.tree_hash import normalize_endpoint

    body = (
        b"http {\n"
        b"  proxy_pass http://10.0.0.5:9000;\n"
        b"  mgmt { usage_report    endpoint=10.0.0.5; }\n"
        b"}\n"
    )
    out = normalize_endpoint({"nginx.conf": body}, "10.0.0.5")["nginx.conf"]
    assert b"proxy_pass http://10.0.0.5:9000;" in out
    assert b"endpoint=nim-mgmt-endpoint.invalid;" in out


def test_normalization_is_a_noop_without_the_endpoint():
    from scripts.tree_hash import normalize_endpoint

    body = b"mgmt { usage_report endpoint=other.example; }\n"
    assert normalize_endpoint({"nginx.conf": body}, "")["nginx.conf"] == body
