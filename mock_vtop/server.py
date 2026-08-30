"""Mock VTOP HTTP server for local development and tests.

Simulates the discovered VTOP behaviour:

* pre-login chain:  ``GET /vtop/open/page`` → ``POST /vtop/prelogin/setup`` →
                    ``GET /vtop/init/page`` → ``GET /vtop/login``
* login with a *known* manual CAPTCHA value (see :data:`MOCK_CAPTCHA`)
* session cookies and per-session CSRF state
* authenticated data endpoints returning the saved sanitized fixtures
* session expiry (redirect to the login page), flip-switchable at runtime

Run standalone::

    python -m mock_vtop.server           # http://127.0.0.1:8734

The well-known mock credentials/captcha are only for local testing — VTOP
itself is never bypassed by this server.
"""

from __future__ import annotations

import base64
import json
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

MOCK_CAPTCHA = "K7M2P9"
MOCK_USERNAME = "student"
MOCK_PASSWORD = "s3cr3t"
MOCK_AUTHORIZED_ID = "25BCE0001"

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

_DATA_ENDPOINTS = {
    "/vtop/get/dashboard/current/cgpa/credits": "cgpa.html",
    "/vtop/get/dashboard/current/semester/course/details": "courses.html",
    "/vtop/get/upcoming/digital/assignments": "assignments.html",
    "/vtop/get/scheduled/events": "events.html",
    "/vtop/get/last/five/feedbacks": "feedback.html",
    "/vtop/get/dashboard/proctor/message": "proctor.html",
}


def _open_page_html(csrf: str) -> str:
    return (
        "<!DOCTYPE html><html><head><title>VIT Vellore - VTOP</title></head><body>"
        '<form class="text-center" id="stdForm" action="/vtop/prelogin/setup" method="post">'
        f'<input type="hidden" name="_csrf" value="{csrf}"/>'
        '<input type="hidden" name="flag" value="VTOP"/>'
        '<button type="submit">Student</button></form>'
        "</body></html>"
    )


def _login_page_html(csrf: str) -> str:
    img = "data:image/png;base64," + base64.b64encode(_PNG_1PX).decode()
    return (
        "<!DOCTYPE html><html><head><title>VIT Vellore - VTOP</title></head><body>"
        '<form action="/vtop/login" method="post">'
        f'<input type="hidden" name="_csrf" value="{csrf}"/>'
        '<input type="text" id="username" name="username"/>'
        '<input type="password" id="password" name="password"/>'
        f'<img src="{img}" id="captchaImg"/>'
        '<input type="text" id="captchaStr" name="captchaStr"/>'
        '<script>var captchaType=1;</script>'
        "</form></body></html>"
    )


def _content_html(csrf: str, authorized_id: str) -> str:
    return (
        "<!DOCTYPE html><html><head><title>VIT Vellore - VTOP</title></head><body>"
        f'<input type="hidden" name="authorizedIDX" id="authorizedIDX" value="{authorized_id}"/>'
        "<script>"
        'var csrfName = "_csrf";'
        f'var csrfValue = "{csrf}";'
        f'var id = "{authorized_id}";'
        "</script>"
        f'<input type="hidden" name="_csrf" value="{csrf}"/>'
        f'<input type="hidden" name="authorizedID" id="authorizedID" value="{authorized_id}"/>'
        "</body></html>"
    )


class MockVTOPServer:
    """In-process mock VTOP service (thread-based HTTP server)."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        captcha: str = MOCK_CAPTCHA,
        username: str = MOCK_USERNAME,
        password: str = MOCK_PASSWORD,
        authorized_id: str = MOCK_AUTHORIZED_ID,
        fixture_dir: Path = _FIXTURE_DIR,
    ) -> None:
        self.host = host
        self.port = port
        self.captcha = captcha
        self.username = username
        self.password = password
        self.authorized_id = authorized_id
        self.fixture_dir = Path(fixture_dir)

        # session token -> {"csrf", "authenticated", "authorized_id"}
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.expire_sessions = False
        self.malformed = False
        self.reject_status = 200
        self.request_log: list[tuple[str, str]] = []

        handler = self._build_handler()
        self._httpd = ThreadingHTTPServer((host, port), handler)
        if port == 0:
            self.port = self._httpd.server_address[1]

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def __enter__(self) -> "MockVTOPServer":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    # ------------------------------------------------------------- internals
    def _token(self, request: BaseHTTPRequestHandler) -> Optional[str]:
        cookie = request.headers.get("Cookie", "")
        for part in cookie.split(";"):
            key, _, value = part.strip().partition("=")
            if key == "VTOP_SESSION":
                return value
        return None

    def _get_or_create_session(self, request) -> str:
        token = self._token(request)
        with self._lock:
            if token is None or token not in self._sessions:
                token = uuid.uuid4().hex
                self._sessions[token] = {
                    "csrf": uuid.uuid4().hex,
                    "authenticated": False,
                    "authorized_id": "",
                }
        return token

    def _fixture(self, name: str) -> str:
        return (self.fixture_dir / name).read_text(encoding="utf-8")

    def _build_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # silence default stderr logging
                pass

            def _send(self, status: int, body: bytes, content_type: str = "text/html;charset=UTF-8", headers=None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                path = urlparse(self.path).path
                server.request_log.append(("GET", path))
                self._route("GET", path)

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(length).decode("utf-8", "replace")
                path = urlparse(self.path).path
                server.request_log.append(("POST", path))
                form = parse_qs(raw, keep_blank_values=True)
                self._route("POST", path, form)

            def _route(self, method: str, path: str, form: Optional[dict] = None) -> None:
                token = server._get_or_create_session(self)
                session = server._sessions[token]
                body = b""

                if path == "/vtop/open/page":
                    body = _open_page_html(session["csrf"]).encode()
                    self._send(200, body, headers={"Set-Cookie": f"VTOP_SESSION={token}; Path=/; HttpOnly"})
                    return

                if path == "/vtop/prelogin/setup" and method == "POST":
                    if (form or {}).get("_csrf", [""])[0] == session["csrf"] and (form or {}).get("flag") == ["VTOP"]:
                        self._send(302, b"", headers={"Location": "/vtop/init/page"})
                    else:
                        self._send(403, b"bad csrf")
                    return

                if path == "/vtop/init/page":
                    target = "/vtop/main/page" if session["authenticated"] else "/vtop/login"
                    self._send(302, b"", headers={"Location": target})
                    return

                if path == "/vtop/login" and method == "GET":
                    body = _login_page_html(session["csrf"]).encode()
                    self._send(200, body)
                    return

                if path == "/vtop/login" and method == "POST":
                    form = form or {}
                    ok = (
                        form.get("_csrf", [""])[0] == session["csrf"]
                        and form.get("username", [""])[0] == server.username
                        and form.get("password", [""])[0] == server.password
                        and form.get("captchaStr", [""])[0].upper() == server.captcha
                    )
                    if ok:
                        session["authenticated"] = True
                        session["authorized_id"] = server.authorized_id
                        self._send(302, b"", headers={"Location": "/vtop/init/page"})
                    else:
                        # VTOP returns a redirect back to the login page on failure.
                        self._send(302, b"", headers={"Location": "/vtop/login"})
                    return

                if path in ("/vtop/main/page", "/vtop/open"):
                    target = "/vtop/open" if path == "/vtop/main/page" else "/vtop/content"
                    if session["authenticated"]:
                        self._send(302, b"", headers={"Location": target})
                    else:
                        self._send(302, b"", headers={"Location": "/vtop/login"})
                    return

                if path == "/vtop/content":
                    if not session["authenticated"]:
                        self._send(302, b"", headers={"Location": "/vtop/login"})
                        return
                    body = _content_html(session["csrf"], session["authorized_id"]).encode()
                    self._send(200, body)
                    return

                if path in _DATA_ENDPOINTS and method == "POST":
                    if not session["authenticated"]:
                        self._send(302, b"", headers={"Location": "/vtop/login"})
                        return
                    csrf_ok = (form or {}).get("_csrf", [""])[0] == session["csrf"]
                    auth_ok = (form or {}).get("authorizedID", [""])[0] == session["authorized_id"]
                    if server.expire_sessions:
                        self._send(302, b"", headers={"Location": "/vtop/login"})
                        return
                    if server.reject_status >= 500:
                        self._send(server.reject_status, b"<html>Server Error</html>")
                        return
                    if csrf_ok and auth_ok:
                        if server.malformed:
                            self._send(200, b"<html><body>  <<<### not a real table ###</body></html>")
                            return
                        body = server._fixture(_DATA_ENDPOINTS[path]).encode()
                        self._send(200, body)
                        return
                    self._send(403, b"forbidden token/id mismatch")
                    return

                self._send(404, b"not found")

        return Handler


class MockApp:
    """Small facade so tests can construct a server and read its state."""

    def __init__(self, **kwargs) -> None:
        self.server = MockVTOPServer(**kwargs)


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the mock VTOP server.")
    parser.add_argument("--port", type=int, default=8734)
    args = parser.parse_args(argv)
    server = MockVTOPServer(port=args.port)
    server.start()
    print(f"Mock VTOP listening on {server.base_url}  (captcha={server.captcha})", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()