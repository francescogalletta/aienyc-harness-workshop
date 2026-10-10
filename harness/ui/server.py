"""The local web server (SPEC 2.7, ARCHITECTURE.md 4.2 and 5).

It listens on this machine only. `GET /` serves the page with a token put in
place; `GET /api/state` and `POST /api/act` need that token in the
`X-Harness-Token` header, so another site open in the same browser cannot
drive the harness or read the plan. The page polls `GET /api/state` (every
second while a lane works, every five seconds otherwise) and redraws when
`version` changed. Standard library only.
"""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..core import BadAction
from ..core.session import one_line

TOKEN_HEADER = "X-Harness-Token"
TOKEN_PLACEHOLDER = "__HARNESS_TOKEN__"
PAGE = Path(__file__).with_name("page.html")
MAX_BODY = 1_000_000        # bytes

# Served while page.html is not in the tree: the state as text, and a box to say something.
PLACEHOLDER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Financial Advisor Harness</title>
<style>body{font:15px/1.5 system-ui,sans-serif;margin:2rem;color:#0f2440;background:#eef2f7}
pre{background:#fff;padding:1rem;overflow:auto;max-height:60vh}#chat p{margin:.25rem 0}</style></head>
<body><h1>Financial Advisor Harness</h1>
<p>The page is not built yet. This placeholder shows the plan state and lets you send a message.</p>
<div id="chat"></div>
<form id="say"><input id="text" size="60" autocomplete="off"> <button>Send</button></form>
<p id="error"></p><pre id="state"></pre>
<script>
const TOKEN = "__HARNESS_TOKEN__";
let version = null, busy = false, timer = null;
async function api(path, body) {
  const options = {headers: {"X-Harness-Token": TOKEN}};
  if (body) { options.method = "POST"; options.body = JSON.stringify(body); }
  return (await fetch(path, options)).json();
}
async function poll() {
  const state = await api("/api/state");
  busy = Object.values(state.lanes).some(lane => lane === "working");
  if (state.version !== version) {
    version = state.version;
    const chat = document.getElementById("chat");
    chat.replaceChildren(...state.chat.map(m => {
      const p = document.createElement("p"); p.textContent = m.who + ": " + m.text; return p;
    }));
    document.getElementById("error").textContent = state.error || "";
    document.getElementById("state").textContent = JSON.stringify(state, null, 2);
  }
  timer = setTimeout(poll, busy ? 1000 : 5000);
}
document.getElementById("say").addEventListener("submit", async event => {
  event.preventDefault();
  const box = document.getElementById("text");
  const answer = await api("/api/act", {action: "say", text: box.value});
  document.getElementById("error").textContent = answer.ok ? "" : answer.error;
  if (answer.ok) box.value = "";
  version = null; clearTimeout(timer); poll();
});
poll();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.partition("?")[0]
        if path == "/":
            return self._page()
        if not self._allowed(path):
            return None
        if path == "/api/state":
            try:
                return self._json(200, self.server.session.state())
            except Exception as error:
                return self._json(500, {"ok": False, "error": one_line(error)})
        return self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.partition("?")[0]
        if not self._allowed(path):
            return None
        if path != "/api/act":
            return self._json(404, {"ok": False, "error": "not found"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 <= length <= MAX_BODY:
                raise ValueError("the body is too large")
            body = json.loads(self.rfile.read(length) or b"null")
            if not isinstance(body, dict) or not isinstance(body.get("action"), str):
                raise ValueError('the body must be a JSON object with "action"')
            payload = {key: value for key, value in body.items() if key != "action"}
            applied, reason = self.server.session.act(body["action"], payload)
        except (ValueError, BadAction) as error:
            return self._json(400, {"ok": False, "error": " ".join(str(error).split())})
        except Exception as error:      # a fault in the harness, not in the request
            return self._json(500, {"ok": False, "error": one_line(error)})
        if not applied:
            return self._json(409, {"ok": False, "error": reason})
        return self._json(200, {"ok": True, "version": self.server.session.version})

    def _allowed(self, path: str) -> bool:
        """404 outside /api/; 403 for an /api/ request without the token."""
        if not path.startswith("/api/"):
            self._json(404, {"ok": False, "error": "not found"})
            return False
        if not secrets.compare_digest(self.headers.get(TOKEN_HEADER) or "", self.server.token):
            self._json(403, {"ok": False, "error": f"missing or wrong {TOKEN_HEADER} header"})
            return False
        return True

    def _page(self):
        try:
            page = self.server.page_path.read_text(encoding="utf-8")
        except OSError:
            page = PLACEHOLDER
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
    """A server for `session` on 127.0.0.1 (port 0 picks a free one). Call `serve_forever()` to run.

    `page_path` is the page; by default `page.html` next to this file, or a placeholder while that
    file is not there. Every server makes a new random token.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.session = session
    server.token = secrets.token_urlsafe(32)
    server.page_path = Path(page_path) if page_path is not None else PAGE
    return server
