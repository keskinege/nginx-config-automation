import pathlib

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_every_template_file_exists():
    for meta_path in (REPO / "templates").rglob("meta.yaml"):
        meta = yaml.safe_load(meta_path.read_text())
        assert meta["type"] in {"base", "augment"}
        for item in meta["files"]:
            assert (meta_path.parent / item["source"]).is_file(), item
            if "target" in item:
                assert item["target"].startswith("/etc/nginx/"), item
