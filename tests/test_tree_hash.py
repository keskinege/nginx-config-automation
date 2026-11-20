from scripts.tree_hash import hash_files, hash_tree


def test_multiple_conf_d_files_are_all_hashed(tmp_path):
    (tmp_path / "conf.d").mkdir()
    (tmp_path / "nginx.conf").write_text("events {}\n")
    (tmp_path / "conf.d" / "10-site.conf").write_text("server { listen 80; }\n")
    (tmp_path / "conf.d" / "20-api.conf").write_text("server { listen 9000; }\n")

    info = hash_tree(tmp_path)
    assert info["files"] == 3
    assert info["bytes"] == sum(
        len(p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file()
    )


def test_path_or_content_change_changes_hash():
    base = {"nginx.conf": b"events {}\n", "conf.d/a.conf": b"server {}\n"}
    assert hash_files(base)["sha256"] == hash_files(dict(reversed(list(base.items()))))["sha256"]
    changed = dict(base)
    changed["conf.d/a.conf"] = b"server { listen 81; }\n"
    assert hash_files(base)["sha256"] != hash_files(changed)["sha256"]
    added = dict(base)
    added["conf.d/b.conf"] = b"server {}\n"
    assert hash_files(base)["sha256"] != hash_files(added)["sha256"]


def test_exclude_skips_manifest(tmp_path):
    (tmp_path / "nginx.conf").write_text("events {}\n")
    (tmp_path / "render-manifest.txt").write_text("ignored\n")
    info = hash_tree(tmp_path)
    assert info["files"] == 1
