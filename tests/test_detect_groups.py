from __future__ import annotations

import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


def env_for(repo):
    return {**os.environ,
            "PATH": f"{REPO / 'scripts'}:{os.environ['PATH']}",
            "REPO_ROOT": str(repo)}


def test_renamed_group_is_not_a_phantom(tmp_path):
    repo = tmp_path
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    old = repo / "groups" / "old-cluster"
    old.mkdir(parents=True)
    (old / "group.yaml").write_text("name: old-cluster\ndeploy_mode: static\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "old")
    before = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    new = repo / "groups" / "new-cluster"
    new.mkdir(parents=True)
    (new / "group.yaml").write_text("name: new-cluster\ndeploy_mode: static\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "rename")
    after = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()

    result = subprocess.run(
        [str(REPO / "scripts" / "detect-groups.sh"), "static", before, after, "push"],
        cwd=repo, text=True, capture_output=True, env=env_for(repo),
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["new-cluster"]


def test_typo_mode_fails(tmp_path):
    repo = tmp_path
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    d = repo / "groups" / "g"
    d.mkdir(parents=True)
    (d / "group.yaml").write_text("name: g\ndeploy_mode: templates\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "g")
    result = subprocess.run(
        [str(REPO / "scripts" / "detect-groups.sh"), "static", "", "",
         "workflow_dispatch"],
        cwd=repo, text=True, capture_output=True, env=env_for(repo),
    )
    assert result.returncode != 0
    assert "must be 'static' or 'template'" in result.stderr
