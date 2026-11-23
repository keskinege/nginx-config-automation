from __future__ import annotations

import base64
import json
import pathlib
import re
import shutil
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class MockNIM:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, object | None]] = []
        self.templates = [
            {
                "name": "nginx-base",
                "uid": "tpl-base",
                "description": "",
                "state": "draft",
                "analyzedState": "valid",
                "type": "base",
                "isFactory": False,
                "hasSubmissions": False,
                "createTime": "x",
                "updateTime": "y",
            }
        ]
        self.template_files: dict[str, dict[str, dict]] = {}
        self.next_template = 1
        self.next_file = 1
        self.config_files = [
            {"name": "/etc/nginx/nginx.conf", "contents": b64("events {}\n")},
            {"name": "/etc/nginx/conf.d/10-site.conf", "contents": b64("server { listen 80; }\n")},
            {"name": "/etc/nginx/conf.d/20-api.conf", "contents": b64("server { listen 9000; }\n")},
        ]
        self.aux_files = [
            {"name": "mime.types", "contents": b64("types {}\n")},
        ]
        self.systems = [
            {"hostname": "plus-k8s-1", "status": {"state": "online"}},
            {"hostname": "plus-k8s-2", "status": {"state": "online"}},
        ]

    def compose_response(self) -> dict:
        return {
            "config": {
                "configFiles": {"rootDir": "/etc/nginx", "files": self.config_files},
                "auxFiles": {"rootDir": "/etc/nginx", "files": self.aux_files},
            },
            "message": "",
        }


def make_handler(state: MockNIM):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def _send(self, code: int, obj: dict | None = None) -> None:
            if obj is None:
                self.send_response(code)
                self.end_headers()
                return
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return None
            return json.loads(self.rfile.read(length))

        def do_GET(self) -> None:
            state.requests.append(("GET", self.path, None))
            files_match = re.fullmatch(r"/api/platform/v1/conf-templates/([^/]+)/files", self.path)
            if files_match:
                uid = files_match.group(1)
                self._send(200, {"items": list(state.template_files.get(uid, {}).values())})
            elif self.path.startswith("/api/platform/v1/conf-templates"):
                self._send(200, {"items": state.templates, "count": len(state.templates)})
            elif self.path == "/api/platform/v1/instance-groups":
                self._send(200, {"items": [{"name": "test-group", "uid": "group-1"}]})
            elif self.path == "/api/platform/v1/systems":
                self._send(200, {"items": state.systems})
            elif self.path == "/api/platform/v1/instance-groups/group-1/config":
                self._send(200, {
                    "updateTime": "2026-01-01T00:00:00Z",
                    "configFiles": {
                        "rootDir": "/etc/nginx",
                        "files": [{
                            "name": "/etc/nginx/nginx.conf",
                            "contents": b64(
                                "events {}\n"
                                "http { include /etc/nginx/conf.d/*.conf; }\n"
                                "mgmt { usage_report endpoint=real.example; }\n"
                            ),
                        }],
                    },
                    "auxFiles": {
                        "rootDir": "/etc/nginx",
                        "files": [{
                            "name": "/etc/nginx/tls/tls.crt",
                            "contents": b64("cert"),
                        }],
                    },
                })
            else:
                self._send(404, {"message": "not found"})

        def do_PUT(self) -> None:
            body = self._body()
            state.requests.append(("PUT", self.path, body))
            file_match = re.fullmatch(
                r"/api/platform/v1/conf-templates/([^/]+)/files/([^/]+)", self.path
            )
            if file_match:
                uid, file_uid = file_match.groups()
                files = state.template_files.setdefault(uid, {})
                current = next((f for f in files.values() if f.get("uid") == file_uid), None)
                if current is None:
                    self._send(404, {"message": "file not found"})
                    return
                old_name = current["name"]
                current.update(body or {})
                if current["name"] != old_name:
                    files[current["name"]] = files.pop(old_name)
                self._send(200, current)
                return
            self._send(200, state.compose_response())

        def do_POST(self) -> None:
            body = self._body()
            state.requests.append(("POST", self.path, body))
            if self.path == "/api/platform/v1/conf-templates":
                uid = f"new-{state.next_template}"
                state.next_template += 1
                files = {}
                for item in (body or {}).get("files", []):
                    file_uid = f"file-{state.next_file}"
                    state.next_file += 1
                    files[item["name"]] = {
                        "name": item["name"],
                        "type": item["type"],
                        "content": item["content"],
                        "uid": file_uid,
                    }
                state.template_files[uid] = files
                created = {
                    "name": body["name"],
                    "uid": uid,
                    "description": body.get("description", ""),
                    "state": body.get("state", "draft"),
                    "analyzedState": "valid",
                    "analysisErrors": [],
                    "type": body.get("type", "base"),
                    "isFactory": False,
                    "hasSubmissions": False,
                    "createTime": "x",
                    "updateTime": "y",
                    "files": list(files.values()),
                }
                state.templates.append(created)
                self._send(201, created)
                return
            files_match = re.fullmatch(r"/api/platform/v1/conf-templates/([^/]+)/files", self.path)
            if files_match:
                uid = files_match.group(1)
                files = state.template_files.setdefault(uid, {})
                added = []
                for item in body or []:
                    file_uid = f"file-{state.next_file}"
                    state.next_file += 1
                    entry = {
                        "name": item["name"],
                        "type": item["type"],
                        "content": item["content"],
                        "uid": file_uid,
                    }
                    files[item["name"]] = entry
                    added.append(entry)
                self._send(201, {"items": added, "failures": []})
                return
            self._send(202, {"deploymentUID": "dep-1", "result": "accepted"})

        def do_DELETE(self) -> None:
            state.requests.append(("DELETE", self.path, None))
            file_match = re.fullmatch(
                r"/api/platform/v1/conf-templates/([^/]+)/files/([^/]+)", self.path
            )
            if file_match:
                uid, file_uid = file_match.groups()
                files = state.template_files.get(uid, {})
                for name, item in list(files.items()):
                    if item.get("uid") == file_uid:
                        del files[name]
                        break
                self._send(204)
                return
            self._send(404, {"message": "not found"})

    return Handler


@pytest.fixture
def mock_nim():
    state = MockNIM()
    server = HTTPServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.base_url = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def repo_group():
    name = f"test-{uuid.uuid4().hex[:8]}"
    group_dir = REPO / "groups" / name
    group_dir.mkdir(parents=True)
    (group_dir / "inputs.json").write_text(json.dumps({
        "baseData": {
            "templateName": "nginx-base",
            "main": {"templateInput": {"worker_connections": "2048"}},
        },
        "augmentData": [],
    }))
    yield name
    shutil.rmtree(group_dir, ignore_errors=True)
