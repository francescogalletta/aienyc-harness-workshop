"""SPEC 4.7: the interview behind the web page. A scripted model asks, the test plays the page."""
import json
import queue
import threading

import pytest

from harness import db
from harness.config import load_config
from harness.grounding import Lookup, ResearchDesk, save_brief
from harness.grounding.interview import CONFIRM, ONE_QUESTION, WRAP_UP
from harness.model import ScriptedModel
from harness.ui.session import GroundingSession

from step1_helpers import LOOK_UP, PLAN, SOURCE, lookups_made, make_brief, write

OPENING = "I want to stay on top of my cash flow."
QUESTION = {"text": "Do you want a forecast, or today's balance?"}
NO_PLAN = {"text": "Nothing to read up on."}


@pytest.fixture
def make(tmp_path, reference_file, monkeypatch):
    """Returns a function that makes a session whose model replays `script`."""
    monkeypatch.setenv("HARNESS_REFERENCE", str(reference_file))
    config = load_config()
    conn = db.connect(config.db_path)

    def make(script, **options):
        make.model = ScriptedModel(script)
        return GroundingSession(config, conn, model_factory=lambda: make.model, **options)

    make.conn, make.config = conn, config
    make.state_path = tmp_path / "grounding_state.json"
    return make


def waited(session):
    """The snapshot once the harness has stopped being busy. It must always be plain JSON."""
    snapshot = session.wait(5)
    assert snapshot["phase"] != "working", "the interview did not come back in time"
    assert json.loads(json.dumps(snapshot)) == snapshot
    return snapshot


def test_a_whole_interview_through_the_page(make):
    session = make([PLAN,
                    {"tool_calls": [{"name": "look_up", "arguments": {"query": "something unknown"}}]},
                    QUESTION, write(), write(make_brief(mode="one_off"))])
    assert session.snapshot() == {
        "phase": "start", "note": "", "transcript": [], "pending": None, "research": [], "brief": None,
        "brief_status": None, "saved": None, "questions": 0, "max_questions": 12, "error": None,
        "session_id": ""}
    # Nothing is waiting yet, so nothing but a start applies.
    assert [session.answer("Hello."), session.accept(), session.request_changes("More."),
            session.wrap(), session.stop(), session.start("   ")] == [False] * 6

    assert session.start(f"  {OPENING} ") is True
    assert session.snapshot()["transcript"] == [{"who": "you", "text": OPENING}]
    asked = waited(session)
    assert asked["phase"] == "question" and asked["pending"] == QUESTION["text"]
    assert asked["transcript"] == [{"who": "you", "text": OPENING}, {"who": "harness", "text": QUESTION["text"]}]
    assert [(e["query"], e["status"], e["planned"]) for e in asked["research"]] == [
        ("cash flow forecast", "found", True), ("something unknown", "not_found", False)]
    assert asked["research"][0]["sources"] == [{"title": "Example: cash flow forecast", "url": SOURCE}]
    assert (asked["questions"], asked["max_questions"], asked["note"]) == (0, 12, "")
    assert len(asked["session_id"]) == 32 and asked["brief"] is None and asked["error"] is None
    assert make.state_path.exists()
    assert [session.start("Another."), session.accept(), session.request_changes("More.")] == [False] * 3

    assert session.answer(" A forecast. ") is True
    assert session.answer("Twice.") is False                       # the question is answered already
    proposed = waited(session)
    assert proposed["phase"] == "confirm" and proposed["pending"] is None
    assert proposed["brief"] == make_brief() and proposed["brief_status"] == "proposed"
    assert proposed["questions"] == 1 and proposed["saved"] is None
    # Neither the confirm question nor the terminal summary is part of the conversation.
    assert proposed["transcript"][2:] == [{"who": "you", "text": "A forecast."}]
    assert [session.answer("Hello."), session.wrap(), session.start("Another.")] == [False] * 3

    assert session.request_changes("Make it a one-off.") is True
    changed = waited(session)
    assert changed["phase"] == "confirm" and changed["brief"]["mode"] == "one_off"
    assert changed["transcript"][-1] == {"who": "you", "text": "Make it a one-off."}

    assert session.accept() is True
    saved = waited(session)
    assert saved["phase"] == "saved" and saved["brief_status"] == "confirmed"
    assert saved["brief"] == make_brief(mode="one_off")             # the brief itself, without its meta
    assert saved["saved"] == {"status": "confirmed",
                              "json": str(make.config.brief_dir / "domain_brief.json"),
                              "page": str(make.config.brief_dir / "domain_brief.md")}
    assert len(saved["transcript"]) == 4 and len(saved["research"]) == 2
    assert not make.state_path.exists()
    assert not any(CONFIRM in line["text"] or "PROPOSED BRIEF" in line["text"] or "[harness]" in line["text"]
                   for line in saved["transcript"])

    # Everything said is in the database, under the interview's session id.
    events = db.list_events(make.conn, session_id=saved["session_id"])
    assert [row["kind"] for row in events] == [
        "grounding.answer", "grounding.research_plan", "grounding.lookup", "grounding.question",
        "grounding.answer", "grounding.brief_changes", "grounding.brief_written"]
    assert json.loads(events[0]["payload"]) == {"text": OPENING}
    # The interviewer was told what the plan had read.
    assert make.model.calls[1]["messages"][0]["content"].endswith("ready for look_up: cash flow forecast.")


def test_a_failing_model_ends_in_failed_and_can_be_resumed(make):
    session = make([])                                              # every model call fails
    session.start(OPENING)
    failed = waited(session)
    assert failed["phase"] == "failed" and "ScriptExhausted" in failed["error"]
    assert "\n" not in failed["error"] and failed["pending"] is None
    assert failed["transcript"] == [{"who": "you", "text": OPENING}]
    assert make.state_path.exists()                                 # nothing is lost
    assert [session.answer("Hello."), session.accept(), session.stop()] == [False] * 3

    # The next session picks the interview up where it was.
    resumed = make([NO_PLAN, QUESTION])
    asked = waited(resumed)
    assert asked["phase"] == "question" and asked["session_id"] == failed["session_id"]
    assert asked["transcript"] == [{"who": "you", "text": OPENING}, {"who": "harness", "text": QUESTION["text"]}]
    assert len(db.list_events(make.conn, kind="grounding.answer")) == 1     # the opening, recorded once
    resumed.stop()
    waited(resumed)


def test_resuming_rebuilds_the_conversation(make):
    state = {
        "session_id": "session-7", "questions": 2, "rejections": 0, "proposed": None,
        "lookups": lookups_made(),
        "research": [{"query": "cash flow forecast", "status": "found", "name": "cash flow forecast",
                      "definition": "A plan.", "sources": [{"title": "t", "url": SOURCE}],
                      "origin": "reference", "planned": True, "cached": False}],
        "messages": [
            {"role": "user", "content": OPENING + "\n\n[harness] Already read up on, ready for look_up: "
                                                  "cash flow forecast."},
            {"role": "assistant", "content": "Checking.", "tool_calls": [
                {"id": "call_1", "name": "look_up", "arguments": {"query": "cash flow forecast"}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "{}"},
            {"role": "assistant", "content": "How often? And which accounts?"},
            {"role": "user", "content": ONE_QUESTION},
            {"role": "assistant", "content": "How often do you want to check in?"},
            {"role": "user", "content": "Monthly."},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "call_2", "name": "write_brief", "arguments": make_brief()}]},
            {"role": "tool", "tool_call_id": "call_2",
             "content": "The person did not confirm the brief. They said: Add my savings account."},
            {"role": "assistant", "content": "Which savings account do you mean?"},
            {"role": "user", "content": "/wrap is not what I typed.\n\n[harness] You have reached the limit."},
            {"role": "user", "content": WRAP_UP},
            {"role": "assistant", "content": "One last thing: is the forecast monthly?"},
        ]}
    make.state_path.write_text(json.dumps(state), encoding="utf-8")

    session = make([write()])                                       # resumes at once: no start needed
    asked = waited(session)
    assert asked["phase"] == "question" and asked["pending"] == "One last thing: is the forecast monthly?"
    assert asked["transcript"] == [
        {"who": "you", "text": OPENING},
        {"who": "harness", "text": "How often do you want to check in?"},
        {"who": "you", "text": "Monthly."},
        {"who": "you", "text": "Add my savings account."},
        {"who": "harness", "text": "Which savings account do you mean?"},
        {"who": "you", "text": "/wrap is not what I typed."},
        {"who": "harness", "text": "One last thing: is the forecast monthly?"},      # there once, not twice
    ]
    assert (asked["session_id"], asked["questions"]) == ("session-7", 2)
    assert asked["research"] == state["research"]
    assert session.start("A new one.") is False                     # an interview is under way

    assert session.answer("Yes, monthly.")
    assert waited(session)["phase"] == "confirm"
    assert len(make.model.calls) == 1                               # no plan: the interview was under way
    assert session.accept() and waited(session)["phase"] == "saved"
