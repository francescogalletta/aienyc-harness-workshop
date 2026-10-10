"""B2: the real page is served with the token and loads nothing from outside; the sample plan state
documents have the shape ARCHITECTURE.md section 3 states; the state and the actions round trip
through the real server."""
import json
import re
from pathlib import Path

import pytest

from harness.ui.server import PAGE, TOKEN_PLACEHOLDER
from layer0_helpers import SETTLE
from state_shape import problems
from test_server import serve        # noqa: F401  (the fixture)

STATES = Path(__file__).parent / "states"
SAMPLES = sorted(STATES.glob("*.json"))
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def test_the_real_page_is_served_with_the_token_in_place(serve):                # noqa: F811
    request = serve(page_path=PAGE)
    response, text = request("GET", "/", token=False)
    assert response.status == 200 and response.getheader("Content-Type").startswith("text/html")
    assert request.server.token in text and TOKEN_PLACEHOLDER not in text
    assert "<title>" in text and "page is not built yet" not in text           # not the placeholder


def test_the_page_loads_nothing_from_outside():
    page = PAGE.read_text(encoding="utf-8")
    assert [url for url in re.findall(r"https?://[^\s\"'<>)]+", page) if url != SVG_NAMESPACE] == []
    assert re.findall(r"<(?:script|img|iframe|link|source|video|audio|embed|object)\b[^>]*\b(?:src|href|data)\s*=",
                      page, re.IGNORECASE) == []
    assert not re.search(r"@import|url\(\s*[\"']?(?!data:|#)|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts",
                         page)
    assert TOKEN_PLACEHOLDER in page and page.count(TOKEN_PLACEHOLDER) == 1
    assert re.findall(r"fetch\(([^,)]*)", page) == ["path"]                       # every request goes through api()
    assert set(re.findall(r"['\"](/[a-z/]*api/[a-z]+)['\"]", page)) == {"/api/state", "/api/act"}


def test_there_are_five_sample_states():
    assert [path.stem for path in SAMPLES] == ["answer_with_mark", "built_one_not_built", "call_waiting",
                                               "plan_proposed", "review_challenges"]


@pytest.mark.parametrize("path", SAMPLES, ids=lambda path: path.stem)
def test_each_sample_state_has_the_documented_shape(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    assert problems(state) == []


def test_the_validator_notices_a_wrong_document():
    state = json.loads((STATES / "review_challenges.json").read_text(encoding="utf-8"))
    state["threads"][0]["after"] = "m999"
    state["chat"][-1]["figures"] = [{"start": 0, "end": 3, "text": "zzz", "step": None, "run": None, "input": None}]
    found = problems(state)
    assert any("not in the chat" in line for line in found)
    assert any("offsets" in line for line in found)
    state["activity"] = [{"lane": "side", "what": "side", "step": None, "text": "x", "since": "t"}]
    assert any("activity[0]: missing thread" in line for line in problems(state))


def test_the_state_and_an_action_round_trip_through_the_real_server(serve):     # noqa: F811
    request = serve(page_path=PAGE)
    before = json.loads(request("GET", "/api/state")[1])
    assert problems(before) == [] and before["chat"] == []
    response, text = request("POST", "/api/act", {"action": "say", "text": "hello there"})
    assert response.status == 200 and json.loads(text)["ok"] is True
    request.session.settle(SETTLE)
    after = json.loads(request("GET", "/api/state")[1])
    assert after["version"] > before["version"] and problems(after) == []
    assert [(m["who"], m["text"]) for m in after["chat"]][0] == ("you", "hello there")
