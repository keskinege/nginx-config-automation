from __future__ import annotations

import os
import pathlib
import subprocess

from scripts.select_files import managed
from scripts.tree_hash import hash_tree

REPO = pathlib.Path(__file__).resolve().parents[1]


def make_tree(tmp_path):
    tree = tmp_path / "tree"
    (tree / "conf.d").mkdir(parents=True)
    (tree / "nginx.conf").write_text("events {}\n")
    (tree / "conf.d" / "a.conf").write_text("server {}\n")
    (tree / "group.yaml").write_text("name: t\n")
    (tree / "inputs.yaml").write_text("baseData: {}\n")
    (tree / ".gitkeep").write_text("")
    (tree / "render-manifest.txt").write_text("x\n")
    return tree


def test_non_managed_names_are_excluded():
    for rel in (
        "group.yaml",
        "inputs.yaml",
        "render-manifest.txt",
        ".DS_Store",
        ".gitkeep",
        "conf.d/.keep",
        "a.lock.json",
    ):
        assert not managed(rel), rel


def test_config_files_are_managed():
    for rel in ("nginx.conf", "conf.d/site.conf", "certs/nim-ca.pem", "mime.types"):
        assert managed(rel), rel


def test_tree_hash_skips_the_same_files_as_publish(tmp_path):
    tree = make_tree(tmp_path)
    assert hash_tree(tree)["files"] == 2


def test_publish_lists_exactly_the_managed_files(mock_nim, tmp_path):
    tree = make_tree(tmp_path)
    env = {
        **os.environ,
        "GROUP": "test-group",
        "CONFIG_DIR": str(tree),
        "NIM_URL": mock_nim.base_url,
        "NIM_USER": "u",
        "NIM_PASSWORD": "p",
        "EXTERNAL_ID": "abc123",
        "DRY_RUN": "1",
    }
    result = subprocess.run(
        [str(REPO / "scripts" / "publish.sh")],
        cwd=REPO, env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    listed = sorted({
        line.strip() for line in result.stdout.splitlines()
        if line.strip().startswith("/etc/nginx/")
    })
    assert listed == ["/etc/nginx/conf.d/a.conf", "/etc/nginx/nginx.conf"]
