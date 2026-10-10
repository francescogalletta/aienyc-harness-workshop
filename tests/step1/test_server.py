"""SPEC 4.7: the local web server. It runs on a free port; the page is a small stand-in."""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import harness.ui.server as server_module
from harness import db
from harness.config import load_config
from harness.model import ScriptedModel
from harness.ui.server import TOKEN_HEADER, make_server
from harness.ui.session import GroundingSession

from step1_helpers import PLAN, make_brief, write

PAGE = "<!doctype html><title>Stand-in</title><script>const token = '__HARNESS_TOKEN__';</script>"
QUESTION = "Do you want a forecast, or today's balance?"
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # never through a proxy


@pytest.fixture
def served(tmp_path, reference_file, monkeypatch):
    """A running server on a real session. Returns a function that sends one request."""
    monkeypatch.setenv("HARNESS_REFERENCE", str(reference_file))
    config = load_config()
    session = GroundingSession(config, db.connect(config.db_path),
                               model_factory=lambda: ScriptedModel([PLAN, {"text": QUESTION}, write()]))
    page_path = tmp_path / "page.html"
    page_path.write_text(PAGE, encoding="utf-8")
    server = make_server(session, port=0, page_path=page_path)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()

    def send(method, path, body=None, token=server.token, raw=None):
        """Returns (status, content type, body text)."""
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}{path}",
                                         data=data, method=method)
        if token is not None:
            request.add_header(TOKEN_HEADER, token)
        try:
            with DIRECT.open(request, timeout=5) as reply:
                return reply.status, reply.headers["Content-Type"], reply.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.headers["Content-Type"], error.read().decode("utf-8")

    send.server, send.session = server, session
    yield send
    server.shutdown()
    server.server_close()
    thread.join(5)


def post(send, path, body=None, **options):
    status, content_type, text = send("POST", path, {} if body is None else body, **options)
    assert content_type.startswith("application/json")
    return status, json.loads(text)


def test_the_page_is_served_with_the_token_in_place(served):
    status, content_type, text = served("GET", "/", token=None)     # the page itself needs no token
    assert status == 200 and content_type.startswith("text/html")
    assert text == PAGE.replace("__HARNESS_TOKEN__", served.server.token)
    assert "__HARNESS_TOKEN__" not in text


def test_every_api_request_needs_the_token(served):
    for method, path in [("GET", "/api/state"), ("POST", "/api/start"), ("POST", "/api/answer"),
                         ("POST", "/api/accept"), ("POST", "/api/changes"), ("POST", "/api/wrap"),
                         ("POST", "/api/stop"), ("GET", "/api/nothing"), ("POST", "/api/nothing")]:
        body = {"opening": "Hello.", "text": "Hello."} if method == "POST" else None
        for token in (None, "", "not-the-token"):
            status, content_type, text = served(method, path, body, token=token)
            assert status == 403, (method, path, token)
            assert content_type.startswith("application/json") and "error" in json.loads(text)
    assert served.session.snapshot()["phase"] == "start"            # none of them did anything


def test_a_post_that_does_not_apply_is_409_with_the_snapshot(served):
    for path, body in [("/api/answer", {"text": "Hello."}), ("/api/accept", {}),
                       ("/api/changes", {"text": "More."}), ("/api/wrap", {}), ("/api/stop", {})]:
        status, snapshot = post(served, path, body)
        assert status == 409 and snapshot["phase"] == "start", path


def test_an_interview_through_the_api(served):
    status, snapshot = post(served, "/api/start", {"opening": "I want to stay on top of my cash flow."})
    assert status == 200 and snapshot["phase"] in ("working", "question")
    assert snapshot["transcript"][0] == {"who": "you", "text": "I want to stay on top of my cash flow."}
    assert served.session.wait(5)["pending"] == QUESTION

    assert post(served, "/api/start", {"opening": "Again."})[0] == 409
    status, snapshot = post(served, "/api/answer", {"text": "A forecast."})
    assert status == 200 and snapshot["transcript"][-1] == {"who": "you", "text": "A forecast."}
    assert served.session.wait(5)["phase"] == "confirm"

    state = json.loads(served("GET", "/api/state")[2])
    assert state["brief"] == make_brief() and state["brief_status"] == "proposed"
    assert post(served, "/api/accept")[0] == 200
    assert served.session.wait(5)["phase"] == "saved"
    assert json.loads(served("GET", "/api/state")[2])["saved"]["status"] == "confirmed"
