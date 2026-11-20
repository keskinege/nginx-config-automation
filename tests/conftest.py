from __future__ import annotations

import base64
import json
import pathlib
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
        self.requests: list[tuple[str, str, dict | None]] = []
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
        self.config_files = [
            {"name": "/etc/nginx/nginx.conf", "contents": b64("events {}\n")},
            {"name": "/etc/nginx/conf.d/10-site.conf", "contents": b64("server { listen 80; }\n")},
            {"name": "/etc/nginx/conf.d/20-api.conf", "contents": b64("server { listen 9000; }\n")},
        ]
        self.aux_files = [
            {"name": "mime.types", "contents": b64("types {}\n")},
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

        def _send(self, code: int, obj: dict) -> None:
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict | None:
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return None
            return json.loads(self.rfile.read(length))

        def do_GET(self) -> None:
            state.requests.append(("GET", self.path, None))
            if self.path.startswith("/api/platform/v1/conf-templates"):
                self._send(200, {"items": state.templates, "count": len(state.templates)})
            elif self.path == "/api/platform/v1/instance-groups":
                self._send(200, {"items": [{"name": "test-group", "uid": "group-1"}]})
            elif self.path == "/api/platform/v1/instance-groups/group-1/config":
                self._send(200, {"updateTime": "2026-01-01T00:00:00Z"})
            else:
                self._send(404, {"message": "not found"})

        def do_PUT(self) -> None:
            body = self._body()
            state.requests.append(("PUT", self.path, body))
            self._send(200, state.compose_response())

        def do_POST(self) -> None:
            body = self._body()
            state.requests.append(("POST", self.path, body))
            self._send(202, {"deploymentUID": "dep-1", "result": "accepted"})

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
