from __future__ import annotations

import pathlib

from scripts.tree_hash import hash_tree
from scripts.uid_names import invert, rename_paths


def test_invert_turns_name_to_uid_into_uid_to_name():
    assert invert({"nginx-base": "uid-a", "site-k8s": "uid-b"}) == {
        "uid-a": "nginx-base",
        "uid-b": "site-k8s",
    }


def test_rename_maps_augment_uids_to_template_names():
    files = {
        "augments/http/18d90853-ea70-4636-9e94-daa8ce73a2b3.conf": b"x\n",
        "nginx.conf": b"events {}\n",
    }
    mapping = {"18d90853-ea70-4636-9e94-daa8ce73a2b3": "site-k8s"}
    assert sorted(rename_paths(files, mapping)) == [
        "augments/http/site-k8s.conf",
        "nginx.conf",
    ]


def test_two_namespaces_hash_the_same(tmp_path):
    mapping = {"uid-one": "site-k8s", "uid-two": "site-k8s"}
    trees = []
    for uid in ("uid-one", "uid-two"):
        tree = tmp_path / uid
        (tree / "augments" / "http").mkdir(parents=True)
        (tree / "nginx.conf").write_text("events {}\n")
        (tree / "augments" / "http" / f"{uid}.conf").write_text("server {}\n")
        trees.append(tree)

    first = hash_tree(trees[0], uid_map={"uid-one": "site-k8s"})
    second = hash_tree(trees[1], uid_map={"uid-two": "site-k8s"})
    assert first["sha256"] == second["sha256"]


def test_content_still_changes_the_hash(tmp_path):
    tree = tmp_path / "tree"
    (tree / "augments" / "http").mkdir(parents=True)
    (tree / "nginx.conf").write_text("events {}\n")
    (tree / "augments" / "http" / "uid-one.conf").write_text("server {}\n")
    before = hash_tree(tree, uid_map={"uid-one": "site-k8s"})
    (tree / "augments" / "http" / "uid-one.conf").write_text("server { listen 80; }\n")
    after = hash_tree(tree, uid_map={"uid-one": "site-k8s"})
    assert before["sha256"] != after["sha256"]
