import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def run(path):
    return subprocess.run(
        ["python3", "scripts/lint-inputs.py", str(path)],
        cwd=REPO, text=True, capture_output=True,
    )


def test_valid_inputs_pass(tmp_path):
    (tmp_path / "inputs.yaml").write_text(
        "baseData:\n  templateName: nginx-base\n  main:\n    templateInput:\n"
        "      include_dirs: [/etc/nginx/conf.d]\naugmentData: []\n"
    )
    result = run(tmp_path / "inputs.yaml")
    assert result.returncode == 0, result.stderr


def test_unknown_template_fails(tmp_path):
    (tmp_path / "inputs.yaml").write_text(
        "baseData:\n  templateName: no-such-template\naugmentData: []\n"
    )
    result = run(tmp_path / "inputs.yaml")
    assert result.returncode == 1
    assert "no-such-template" in result.stderr


def test_unsafe_include_dir_fails(tmp_path):
    (tmp_path / "inputs.yaml").write_text(
        "baseData:\n  templateName: nginx-base\n  main:\n    templateInput:\n"
        "      include_dirs: [/etc/passwd]\naugmentData: []\n"
    )
    result = run(tmp_path / "inputs.yaml")
    assert result.returncode == 1
    assert "/etc/nginx" in result.stderr
