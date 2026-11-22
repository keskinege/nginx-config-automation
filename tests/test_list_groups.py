import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_filters_by_mode(tmp_path):
    for name, mode in [("a", "static"), ("b", "template"), ("c", None)]:
        d = tmp_path / name
        d.mkdir()
        text = f"name: {name}\n" + (f"deploy_mode: {mode}\n" if mode else "")
        (d / "group.yaml").write_text(text)
    env = {**os.environ, "GROUPS_DIR": str(tmp_path)}
    result = subprocess.run(
        [str(REPO / "scripts" / "list-groups.sh"), "static"],
        env=env, text=True, capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout.split() == ["a", "c"]
