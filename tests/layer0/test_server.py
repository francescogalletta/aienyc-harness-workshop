"""SPEC 2.7 and ARCHITECTURE.md 5: the server, its token, `GET /api/state` and `POST /api/act`."""
import http.client
import json
import threading

import pytest

from harness.core import NotNow
from harness.ui.server import MAX_BODY, TOKEN_PLACEHOLDER, make_server
from layer0_helpers import SETTLE, fake_layer


@pytest.fixture
def serve(open_session):
    """Serve a session with the given made-up layers; returns a `request(method, path, body, token)`."""
    servers = []

    def start(*layers, page_path=None):
        session = open_session(*layers)
        server = make_server(session, 0, page_path=page_path)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        servers.append(server)

        def request(method, path, body=None, token=True, raw=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=SETTLE)
            headers = {"X-Harness-Token": server.token} if token is True else (
                {"X-Harness-Token": token} if token else {})
            data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
            conn.request(method, path, body=data, headers=headers)
            response = conn.getresponse()
            text = response.read().decode("utf-8")
            conn.close()
            return response, text
        request.session, request.server = session, server
        return request

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def test_the_page_is_served_with_the_token_in_place(serve, tmp_path):
    page = tmp_path / "page.html"
    page.write_text(f"<html><script>const T = '{TOKEN_PLACEHOLDER}';</script></html>", encoding="utf-8")
    request = serve(page_path=page)
    response, text = request("GET", "/", token=False)
    assert response.status == 200 and response.getheader("Content-Type").startswith("text/html")
    assert response.getheader("Cache-Control") == "no-store"
    assert request.server.token in text and TOKEN_PLACEHOLDER not in text


def test_a_placeholder_page_is_served_while_there_is_no_page(serve, tmp_path):
    request = serve(page_path=tmp_path / "not_there.html")
    response, text = request("GET", "/", token=False)
    assert response.status == 200
    assert request.server.token in text and TOKEN_PLACEHOLDER not in text
    assert "http://" not in text and "https://" not in text        # it loads nothing from the network


@pytest.mark.parametrize("method, path", [("GET", "/api/state"), ("POST", "/api/act")])
def test_the_api_needs_the_token(serve, method, path):
    request = serve()
    assert request(method, path, {"action": "say", "text": "x"}, token=False)[0].status == 403
    assert request(method, path, {"action": "say", "text": "x"}, token="wrong")[0].status == 403
    assert request.session.state()["chat"] == []


def test_the_state_is_the_session_state(serve):
    request = serve()
    response, text = request("GET", "/api/state")
    assert response.status == 200 and response.getheader("Cache-Control") == "no-store"
    state = json.loads(text)
    assert state["product"] == "Financial Advisor Harness" and state["layers"] == [0]


def test_an_applied_action_gives_ok_and_the_version(serve):
    request = serve()
    response, text = request("POST", "/api/act", {"action": "say", "text": "hello"})
    body = json.loads(text)
    assert response.status == 200 and body["ok"] is True and isinstance(body["version"], int)
    assert request.session.settle(SETTLE)["chat"][0]["text"] == "hello"


def test_an_action_not_allowed_now_is_409_with_the_reason(serve):
    def refuse(core, payload):
        raise NotNow("not now")

    request = serve(fake_layer(1, actions={"poke": refuse}))
    response, text = request("POST", "/api/act", {"action": "poke"})
    assert response.status == 409 and json.loads(text) == {"ok": False, "error": "not now"}


@pytest.mark.parametrize("raw", [b"not json", b"[1, 2]", b'{"text": "no action"}', b'{"action": 7}',
                                 b'{"action": "no_such_action"}', b'{"action": "say", "text": ""}'])
def test_a_bad_body_or_an_unknown_action_is_400(serve, raw):
    request = serve()
    response, text = request("POST", "/api/act", raw=raw)
    assert response.status == 400 and json.loads(text)["ok"] is False


def test_a_body_over_one_megabyte_is_400(serve):
    request = serve()
    conn = http.client.HTTPConnection("127.0.0.1", request.server.server_address[1], timeout=SETTLE)
    conn.putrequest("POST", "/api/act")
    conn.putheader("X-Harness-Token", request.server.token)
    conn.putheader("Content-Length", str(MAX_BODY + 1))     # the server refuses before reading it
    conn.endheaders()
    assert conn.getresponse().status == 400
    conn.close()
    assert request.session.state()["chat"] == []


@pytest.mark.parametrize("method, path", [("GET", "/nothing"), ("GET", "/api/nothing"), ("POST", "/api/state"),
                                          ("GET", "/api/act"), ("POST", "/")])
def test_other_paths_are_404(serve, method, path):
    assert serve()(method, path, {})[0].status == 404
