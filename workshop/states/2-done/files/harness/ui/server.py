"""The local web server behind the page (SPEC 4.7).

It listens on this machine only. Every `/api/` request must carry a token
that only the served page knows, so another site open in the same browser
cannot drive the interview. Standard library only.
"""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN_HEADER = "X-Harness-Token"
TOKEN_PLACEHOLDER = "__HARNESS_TOKEN__"
PAGE = Path(__file__).with_name("grounding.html")
MAX_BODY = 1_000_000        # bytes; far more than any answer needs

# path -> (the field that must not be empty, or None; what to do with the session and that text)
ACTIONS = {
    "/api/start": ("opening", lambda session, text: session.start(text)),
    "/api/answer": ("text", lambda session, text: session.answer(text)),
    "/api/accept": (None, lambda session, text: session.accept()),
    "/api/changes": ("text", lambda session, text: session.request_changes(text)),
    "/api/wrap": (None, lambda session, text: session.wrap()),
    "/api/stop": (None, lambda session, text: session.stop()),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            return self._page()
        if not self._allowed():
            return None
        if self.path == "/api/state":
            return self._json(200, self.server.session.snapshot())
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._allowed():
            return None
        if self.path not in ACTIONS:
            return self._json(404, {"error": "not found"})
        field, action = ACTIONS[self.path]
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 <= length <= MAX_BODY:
                raise ValueError("body too large")
            body = json.loads(self.rfile.read(length) or b"{}")
            text = str(body.get(field) or "").strip() if field else ""
        except (ValueError, AttributeError):
            return self._json(400, {"error": "the body must be a JSON object"})
        if field and not text:
            return self._json(400, {"error": f"{field} must not be empty"})
        applied = action(self.server.session, text)
        return self._json(200 if applied else 409, self.server.session.snapshot())

    def _allowed(self) -> bool:
        """Answer 404 outside /api/, and 403 for an /api/ request without the token."""
        if not self.path.startswith("/api/"):
            self._json(404, {"error": "not found"})
            return False
        if not secrets.compare_digest(self.headers.get(TOKEN_HEADER) or "", self.server.token):
            self._json(403, {"error": f"missing or wrong {TOKEN_HEADER} header"})
            return False
        return True

    def _page(self):
        try:
            page = self.server.page_path.read_text(encoding="utf-8")
        except OSError:
            return self._json(500, {"error": f"the page is missing: {self.server.page_path.name}"})
        self._send(200, "text/html; charset=utf-8", page.replace(TOKEN_PLACEHOLDER, self.server.token))

    def _json(self, status: int, body: dict):
        self._send(status, "application/json; charset=utf-8", json.dumps(body))

    def _send(self, status: int, content_type: str, text: str):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        """No request log in the terminal."""


def make_server(session, port: int = 8765, page_path=None) -> ThreadingHTTPServer:
    """A server for `session` on 127.0.0.1. Call `serve_forever()` on it to run.

    `page_path` is the page to serve; by default the given `grounding.html`
    next to this file. A new random token is made for every server.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.session = session
    server.token = secrets.token_urlsafe(32)
    server.page_path = Path(page_path) if page_path is not None else PAGE
    return server
