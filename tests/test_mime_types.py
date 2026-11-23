from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_template_and_static_mime_types_match():
    template = (REPO / "templates/base/nginx-base/aux/etc/nginx/mime.types").read_bytes()
    static = (REPO / "groups/static-cluster/mime.types").read_bytes()
    assert template == static
