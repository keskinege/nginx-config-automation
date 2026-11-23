from __future__ import annotations

import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def mode(tmp_path, text):
    d = tmp_path / "g"
    d.mkdir(exist_ok=True)
    (d / "group.yaml").write_text(text)
    return subprocess.run(
        [str(REPO / "scripts" / "group-mode.sh"), str(d)],
        cwd=REPO, text=True, capture_output=True, env={**os.environ},
    )


def test_reads_static_and_template(tmp_path):
    assert mode(tmp_path, "name: g\ndeploy_mode: static\n").stdout.strip() == "static"
    assert mode(tmp_path, "name: g\ndeploy_mode: template\n").stdout.strip() == "template"


def test_default_is_static(tmp_path):
    assert mode(tmp_path, "name: g\n").stdout.strip() == "static"


def test_typo_fails_closed(tmp_path):
    result = mode(tmp_path, "name: g\ndeploy_mode: templates\n")
    assert result.returncode == 2
    assert "must be 'static' or 'template'" in result.stderr


def test_missing_group_yaml_fails_closed(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    result = subprocess.run(
        [str(REPO / "scripts" / "group-mode.sh"), str(d)],
        cwd=REPO, text=True, capture_output=True,
    )
    assert result.returncode == 2
    assert "missing group.yaml" in result.stderr
