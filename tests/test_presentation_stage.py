"""HTTP-level checks for the presentation stage routes.

The stage frontend itself (stage.js/stage.css) stays untested like the console
frontend; these tests pin the server contract the stage depends on: the static
allowlist entries, their content types, and the CSP that forbids external
assets and inline code.
"""

from __future__ import annotations

import http.client
import json
import threading

import pytest

import robot.apps.presentation_ui as ui

CSP = (
    "default-src 'self'; style-src 'self'; script-src 'self'; "
    "img-src 'self' data:; connect-src 'self'"
)


@pytest.fixture()
def stage_port():
    controller = ui.PresentationController()
    server = ui.PresentationHTTPServer(("127.0.0.1", 0), ui.PresentationRequestHandler)
    server.controller = controller
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        controller.close()
        thread.join(timeout=5)


def fetch(port: int, path: str):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_stage_routes_serve_the_new_assets(stage_port):
    expected = {
        "/stage": "text/html; charset=utf-8",
        "/stage.html": "text/html; charset=utf-8",
        "/stage.css": "text/css; charset=utf-8",
        "/stage.js": "text/javascript; charset=utf-8",
    }
    for path, content_type in expected.items():
        status, headers, body = fetch(stage_port, path)
        assert status == 200, path
        assert headers["Content-Type"] == content_type, path
        assert headers["Content-Security-Policy"] == CSP, path
        assert body


def test_stage_alias_serves_the_same_document_as_stage_html(stage_port):
    _, _, alias_body = fetch(stage_port, "/stage")
    _, _, file_body = fetch(stage_port, "/stage.html")
    assert alias_body == file_body


def test_existing_routes_survive_the_allowlist_extension(stage_port):
    for path in ("/", "/index.html", "/styles.css", "/app.js"):
        status, _, _ = fetch(stage_port, path)
        assert status == 200, path
    status, _, body = fetch(stage_port, "/api/health")
    assert status == 200
    assert json.loads(body) == {"ok": True}
    for path in ("/stage/../secret", "/stage.css.bak", "/stage2"):
        status, _, _ = fetch(stage_port, path)
        assert status == 404, path


def test_stage_document_stays_csp_compliant():
    html = (ui.UI_DIR / "stage.html").read_text(encoding="utf-8")
    assert 'href="/stage.css"' in html
    assert 'src="/stage.js"' in html
    assert "http://" not in html and "https://" not in html
    assert "style=" not in html
    assert "onclick=" not in html
