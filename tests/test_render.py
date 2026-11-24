from __future__ import annotations

import json
import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def run_render(mock_nim, group, out_dir, **extra):
    env = {
        **os.environ,
        "GROUP": group,
        "NIM_URL": mock_nim.base_url,
        "NIM_USER": "u",
        "NIM_PASSWORD": "p",
        "OUT_DIR": str(out_dir),
        **{k: str(v) for k, v in extra.items()},
    }
    return subprocess.run(
        [str(REPO / "scripts" / "render.sh")],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
    )


def test_render_writes_every_conf_d_file(mock_nim, repo_group, tmp_path):
    out = tmp_path / "out"
    result = run_render(mock_nim, repo_group, out, WRITE_HASH=1, HASH_FILE=tmp_path / "hash.json")
    assert result.returncode == 0, result.stderr
    assert (out / "nginx.conf").read_text() == "events {}\n"
    assert (out / "conf.d" / "10-site.conf").exists()
    assert (out / "conf.d" / "20-api.conf").exists()
    assert (out / "mime.types").exists()

    manifest = (out / "render-manifest.txt").read_text()
    assert "render_sha256=" in manifest
    assert "conf.d/20-api.conf" in manifest


def test_hash_only_writes_nothing(mock_nim, repo_group, tmp_path):
    out = tmp_path / "out"
    result = run_render(mock_nim, repo_group, out, HASH_ONLY=1)
    assert result.returncode == 0
    assert "sha256=" in result.stdout
    assert not out.exists()


def test_check_hash_detects_change(mock_nim, repo_group, tmp_path):
    out = tmp_path / "out"
    lock = tmp_path / "hash.json"
    assert run_render(mock_nim, repo_group, out, WRITE_HASH=1, HASH_FILE=lock).returncode == 0
    entry = json.loads(lock.read_text())[repo_group]
    entry["sha256"] = "0" * 64
    lock.write_text(json.dumps({repo_group: entry}))
    result = run_render(mock_nim, repo_group, out, CHECK_HASH=1, HASH_FILE=lock)
    assert result.returncode == 2
    assert "changed" in result.stderr


def test_render_refuses_a_repository_directory(mock_nim, repo_group):
    result = run_render(mock_nim, repo_group, "groups")
    assert result.returncode == 1
    assert "refusing" in (result.stdout + result.stderr)


def test_render_refuses_an_existing_directory_without_a_manifest(mock_nim, repo_group, tmp_path):
    out = tmp_path / "precious"
    out.mkdir()
    (out / "keep.txt").write_text("x")
    result = run_render(mock_nim, repo_group, out)
    assert result.returncode == 1
    assert "render-manifest" in (result.stdout + result.stderr)
    assert (out / "keep.txt").exists()
