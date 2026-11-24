from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
STATIC = (REPO / "groups/static-cluster/nginx.conf").read_text()
TMPL = (REPO / "templates/base/nginx-base/base.tmpl").read_text()
META = (REPO / "templates/base/nginx-base/meta.yaml").read_text()


def test_static_mgmt_block_verifies_the_nim_certificate():
    assert "ssl_verify on;" in STATIC
    assert "ssl_verify off" not in STATIC
    assert "ssl_name manager-server;" in STATIC
    assert "ssl_trusted_certificate /etc/nginx/certs/nim-ca.pem;" in STATIC
    assert (REPO / "groups/static-cluster/certs/nim-ca.pem").is_file()


def test_template_mgmt_block_verifies_the_nim_certificate():
    assert "ssl_verify on;" in TMPL
    assert "ssl_verify off" not in TMPL
    assert "ssl_name manager-server;" in TMPL
    assert "ssl_trusted_certificate /etc/nginx/certs/nim-ca.pem;" in TMPL
    assert "source: aux/etc/nginx/certs/nim-ca.pem" in META
    assert (REPO / "templates/base/nginx-base/aux/etc/nginx/certs/nim-ca.pem").is_file()
