"""SPEC 7.5 and 7.6: the given pages, served by the real server, and the link between them.

Only what the SPEC states about the pages is checked: where they live, the placeholder, no network resources, the
paths they may call, the words it names, and the link in each direction. How they look is not tested.
"""
import re
from pathlib import Path

import pytest

import harness.ui.server as server_module

UI = Path(server_module.__file__).parent
ALLOWED_API = {"/api/work/summary", "/api/work/conversation", "/api/work/run", "/api/work/module", "/api/work/events",
               "/api/work/test", "/api/work/data_summary"}                 # (step 5) one more path (SPEC 7.4)


@pytest.fixture(scope="module")
def evidence_text():
    path = server_module.WORK_PAGE
    assert path.is_file(), f"{path} is not there"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def grounding_text():
    return (UI / "grounding.html").read_text(encoding="utf-8")


# ---- where the page is ---------------------------------------------------------------------------------------------------

def test_the_evidence_page_is_a_file_next_to_the_server_named_evidence_html():
    assert Path(server_module.WORK_PAGE) == UI / "evidence.html"
    assert (UI / "evidence.html").is_file()


def test_the_default_page_of_make_server_is_served_at_work(served, evidence_text):
    send = served(work_page=False)                                     # no work_page_path given: the default is used
    reply = send("GET", "/work", token=None)
    assert reply.status == 200 and reply.content_type.startswith("text/html")
    assert reply.text == evidence_text.replace("__HARNESS_TOKEN__", send.server.token)


def test_the_page_served_has_no_placeholder_left_and_holds_the_token_once(served):
    send = served(work_page=False)
    text = send("GET", "/work", token=None).text
    assert "__HARNESS_TOKEN__" not in text and text.count(send.server.token) >= 1


# ---- what the given file holds --------------------------------------------------------------------------------------------

def test_the_placeholder_is_there_exactly_once(evidence_text):
    assert evidence_text.count("__HARNESS_TOKEN__") == 1


def test_it_is_a_single_self_contained_file(evidence_text):
    assert "http://" not in evidence_text and "https://" not in evidence_text
    assert not re.search(r"<script[^>]*\ssrc\s*=", evidence_text, re.I)
    assert not re.search(r"<link[^>]*\shref\s*=", evidence_text, re.I)
    assert "@import" not in evidence_text and not re.search(r"url\(\s*['\"]?(?:https?:)?//", evidence_text, re.I)


def test_it_sends_the_token_in_the_named_header(evidence_text):
    assert "X-Harness-Token" in evidence_text


def test_it_calls_only_the_paths_of_the_api(evidence_text):
    called = set(re.findall(r"/api/[A-Za-z0-9_/]*", evidence_text))
    assert called and called <= ALLOWED_API | {"/api/work/"}, called
    assert "/api/work/summary" in called and "/api/work/test" in called
    assert "/api/state" not in called and "/api/start" not in called


def test_it_names_the_six_views_and_the_one_action(evidence_text):
    # (step 4) a fifth view, Decisions; (step 5) a sixth, Data (SPEC 7.6 item 2)
    for name in ("Conversations", "Runs", "Decisions", "Data", "Modules", "Everything"):
        assert name in evidence_text
    assert "Run the tests now" in evidence_text


def test_it_reads_the_decisions_from_the_events_and_draws_the_side_conversations(evidence_text):
    # (step 4) SPEC 7.6 items 15 to 17: the kinds it draws, the label of a side conversation
    for kind in ("ask.gate", "ask.decision_asked", "ask.decision_refused", "ask.decision", "aside.opened", "aside.closed"):
        assert kind in evidence_text, kind
    assert "Side conversation" in evidence_text
    assert "/api/work/events" in evidence_text


def test_it_indexes_texts_by_code_points(evidence_text):
    assert "Array.from" in evidence_text


def test_it_links_to_the_interview(evidence_text):
    assert re.search(r"""["']/["']""", evidence_text)


def test_it_names_the_nine_labels(evidence_text):
    # (step 5) SPEC 7.6 item 6: `data` is the ninth
    for label in ("run", "data", "input", "note", "brief", "person", "today", "small", "none"):
        assert re.search(rf"""['">\s]{label}['"<\s:]""", evidence_text), label


def test_it_has_a_title(evidence_text):
    assert re.search(r"<title>[^<]+</title>", evidence_text)


# ---- the interview page and the link to the evidence page ------------------------------------------------------------------

def test_the_interview_page_keeps_one_placeholder(grounding_text):
    assert grounding_text.count("__HARNESS_TOKEN__") == 1


def test_the_interview_page_links_to_work_with_the_words_show_your_work(grounding_text):
    assert re.search(r"""<a\b[^>]*\bhref\s*=\s*["']/work["'][^>]*>\s*Show your work\s*</a>""", grounding_text, re.I | re.S)


def test_the_interview_page_is_still_served_at_the_root(served, tmp_path, monkeypatch):
    from harness import db
    from harness.config import load_config
    from harness.model import ScriptedModel
    from harness.ui.session import GroundingSession
    config = load_config()
    session = GroundingSession(config, db.connect(config.db_path), model_factory=lambda: ScriptedModel([]))
    send = served(session)
    reply = send("GET", "/", token=None)
    assert reply.status == 200 and "Show your work" in reply.text
    assert "__HARNESS_TOKEN__" not in reply.text and send.server.token in reply.text
    assert re.search(r"""href\s*=\s*["']/work["']""", reply.text)


def test_the_two_pages_are_two_different_files():
    assert (UI / "grounding.html").read_text(encoding="utf-8") != (UI / "evidence.html").read_text(encoding="utf-8")
