"""The local web server behind the pages (SPEC 4.7 and 7.5).

It listens on this machine only. Every `/api/` request must carry a token
that only the served page knows, so another site open in the same browser
cannot drive the interview or read the evidence. Standard library only.
"""
import json
import re
import secrets
import sqlite3
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import db
from ..calc.gate import NOT_REGISTERED
from . import evidence

TOKEN_HEADER = "X-Harness-Token"
TOKEN_PLACEHOLDER = "__HARNESS_TOKEN__"
PAGE = Path(__file__).with_name("grounding.html")
WORK_PAGE = Path(__file__).with_name("evidence.html")
WHOLE = re.compile(r"^[0-9]+$")
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
        path, _, query = self.path.partition("?")
        if path == "/":
            if self.server.session is None:
                return self._redirect("/work")
            return self._page(self.server.page_path)
        if path == "/work":
            return self._page(self.server.work_page_path)
        if not self._allowed(path):
            return None
        if path == "/api/state" and self.server.session is not None:
            return self._json(200, self.server.session.snapshot())
        if path in WORK_GETS:
            return self._work(WORK_GETS[path], {key: values[0] for key, values in parse_qs(query).items()})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.partition("?")[0]
        if not self._allowed(path):
            return None
        if path == "/api/work/test":
            field, action = "module", None
        elif path in ACTIONS and self.server.session is not None:
            field, action = ACTIONS[path]
        else:
            return self._json(404, {"error": "not found"})
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
        if action is None:
            return self._work(lambda conn, server, params: _test(conn, server, text), {})
        applied = action(self.server.session, text)
        return self._json(200 if applied else 409, self.server.session.snapshot())

    def _work(self, read, params: dict):
        """Answer an evidence request from a connection of its own, closed before the answer goes out."""
        conn = db.connect()
        try:
            status, body = read(conn, self.server, params)
        except sqlite3.Error as error:
            status, body = 500, {"error": " ".join(str(error).split())}
        finally:
            conn.close()
        return self._json(status, body)

    def _allowed(self, path: str) -> bool:
        """Answer 404 outside /api/, and 403 for an /api/ request without the token."""
        if not path.startswith("/api/"):
            self._json(404, {"error": "not found"})
            return False
        if not secrets.compare_digest(self.headers.get(TOKEN_HEADER) or "", self.server.token):
            self._json(403, {"error": f"missing or wrong {TOKEN_HEADER} header"})
            return False
        return True

    def _page(self, page_path: Path):
        try:
            page = page_path.read_text(encoding="utf-8")
        except OSError:
            return self._json(500, {"error": f"the page is missing: {page_path.name}"})
        self._send(200, "text/html; charset=utf-8", page.replace(TOKEN_PLACEHOLDER, self.server.token))

    def _redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

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


# --- The evidence API (SPEC 7.4): each reads one request and returns (status, body) ---

def _summary(conn, server, params):
    return 200, evidence.summary(conn, interview=server.session is not None)


def _conversation(conn, server, params):
    session = params.get("session")
    if not session:
        return 400, {"error": "session is required"}
    found = evidence.conversation(conn, session)
    return (200, found) if found is not None else (404, {"error": f"there is no conversation '{session}'"})


def _run(conn, server, params):
    if not WHOLE.match(params.get("id", "")):
        return 400, {"error": "id must be a whole number"}
    found = evidence.run(conn, int(params["id"]))
    return (200, found) if found is not None else (404, {"error": f"there is no run {int(params['id'])}"})


def _module(conn, server, params):
    name = params.get("name")
    if not name:
        return 400, {"error": "name is required"}
    found = evidence.module(conn, name)
    return (200, found) if found is not None else (404, {"error": NOT_REGISTERED.format(name=name)})


def _events(conn, server, params):
    before, limit = params.get("before"), params.get("limit", "200")
    if before is not None and not WHOLE.match(before):
        return 400, {"error": "before must be a whole number"}
    if not WHOLE.match(limit) or not 1 <= int(limit) <= 1000:
        return 400, {"error": "limit must be a whole number from 1 to 1000"}
    return 200, evidence.events_page(conn, kind=params.get("kind"), session=params.get("session"),
                                     before=int(before) if before is not None else None, limit=int(limit))


def _test(conn, server, name):
    found = evidence.test_now(conn, name, session_id=server.work_session_id)
    return (200, found) if found is not None else (404, {"error": NOT_REGISTERED.format(name=name)})


WORK_GETS = {"/api/work/summary": _summary, "/api/work/conversation": _conversation,
             "/api/work/run": _run, "/api/work/module": _module, "/api/work/events": _events}


def make_server(session, port: int = 8765, page_path=None, work_page_path=None) -> ThreadingHTTPServer:
    """A server for `session` on 127.0.0.1. Call `serve_forever()` on it to run.

    `session` may be None: then only the evidence page is served (SPEC 7.5). `page_path` is the
    interview page and `work_page_path` the evidence page; by default the given files next to this
    one. A new random token is made for every server, and a new evidence session id, which the
    test runs of `POST /api/work/test` carry.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.session = session
    server.token = secrets.token_urlsafe(32)
    server.page_path = Path(page_path) if page_path is not None else PAGE
    server.work_page_path = Path(work_page_path) if work_page_path is not None else WORK_PAGE
    server.work_session_id = uuid.uuid4().hex
    return server
