from __future__ import annotations

import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def run(mock_nim):
    env = {
        **os.environ,
        "NIM_URL": mock_nim.base_url,
        "NIM_USER": "u",
        "NIM_PASSWORD": "p",
    }
    return subprocess.run(
        ["bash", "scripts/check-nim-agents.sh"],
        cwd=REPO, env=env, text=True, capture_output=True,
    )


def test_all_online(mock_nim):
    result = run(mock_nim)
    assert result.returncode == 0, result.stderr
    assert "all 2 online" in result.stdout


def test_offline_fails(mock_nim):
    mock_nim.systems[0]["status"]["state"] = "offline"
    result = run(mock_nim)
    assert result.returncode == 2
    assert "1 of 2" in (result.stdout + result.stderr)
