from __future__ import annotations

import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]


def run(tree):
    return subprocess.run(
        [str(REPO / "scripts" / "check-includes.sh"), str(tree)],
        cwd=REPO, text=True, capture_output=True,
    )


def test_a_typo_include_is_rejected(tmp_path):
    (tmp_path / "nginx.conf").write_text(
        "events {}\nhttp {\n  include /etc/ngnix/x.conf;\n}\n"
    )
    result = run(tmp_path)
    assert result.returncode == 1
    assert "/etc/ngnix/x.conf" in result.stderr


def test_managed_includes_are_allowed(tmp_path):
    (tmp_path / "conf.d").mkdir()
    (tmp_path / "conf.d" / "a.conf").write_text("server {}\n")
    (tmp_path / "nginx.conf").write_text(
        "events {}\nhttp {\n"
        "  include /etc/nginx/conf.d/*.conf;\n"
        "  include /etc/nginx/conf.d/a.conf;\n"
        "}\n"
    )
    assert run(tmp_path).returncode == 0


def test_the_per_member_tls_include_is_an_allowed_stub(tmp_path):
    (tmp_path / "nginx.conf").write_text(
        "events {}\nhttp { include /etc/nginx-tls/server.conf; }\n"
    )
    assert run(tmp_path).returncode == 0


def test_a_relative_include_is_valid(tmp_path):
    (tmp_path / "mime.types").write_text("types {}\n")
    (tmp_path / "nginx.conf").write_text(
        "events {}\nhttp {\n  include mime.types;\n}\n"
    )
    assert run(tmp_path).returncode == 0
