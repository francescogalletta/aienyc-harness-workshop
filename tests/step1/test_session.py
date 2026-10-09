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


def test_notes_and_lookups_in_progress(make):
    started, gate = queue.Queue(), threading.Semaphore(0)

    class Slow:
        def look_up(self, query):
            started.put(query)
            assert gate.acquire(timeout=5)
            return Lookup(query, False, origin="slow")

    session = make([PLAN, {"tool_calls": [{"name": "look_up", "arguments": {"query": "sinking fund"}}]},
                    QUESTION], desk_factory=lambda conn: ResearchDesk(Slow(), conn))
    assert session.start(OPENING)

    assert started.get(timeout=5) == "cash flow forecast"           # the plan is reading
    reading = session.snapshot()
    assert reading["phase"] == "working" and reading["note"] == "reading up on: cash flow forecast"
    assert reading["research"] == [{"query": "cash flow forecast", "status": "looking", "name": "",
                                    "definition": "", "sources": [], "origin": "", "planned": True,
                                    "cached": False}]
    assert [session.answer("Hello."), session.stop(), session.start("Again.")] == [False] * 3
    gate.release()

    assert started.get(timeout=5) == "sinking fund"                 # the interviewer's own lookup
    looking = session.snapshot()
    assert looking["note"] == "looking up: sinking fund"
    assert [(e["query"], e["status"], e["planned"]) for e in looking["research"]] == [
        ("cash flow forecast", "not_found", True), ("sinking fund", "looking", False)]
    gate.release()

    asked = waited(session)
    assert asked["note"] == "" and [e["status"] for e in asked["research"]] == ["not_found", "not_found"]


def test_wrap_and_stop(make):
    session = make([NO_PLAN, QUESTION, LOOK_UP, write()])
    session.start(OPENING)
    assert waited(session)["phase"] == "question"
    assert session.wrap() is True
    assert waited(session)["phase"] == "confirm"
    assert make.model.calls[2]["messages"][-1] == {"role": "user", "content": WRAP_UP}
    assert session.snapshot()["transcript"][-1]["who"] == "harness"     # /wrap is not something they said

    assert session.stop() is True                                   # stopping works at the confirm question too
    stopped = waited(session)
    assert stopped["phase"] == "stopped" and stopped["brief"] is None and stopped["pending"] is None
    assert make.state_path.exists() and session.stop() is False
    assert json.loads(make.state_path.read_text(encoding="utf-8"))["proposed"] is None

    # A stopped interview can be replaced by a new one.
    make.model = ScriptedModel([NO_PLAN, {"text": "A new first question?"}])
    assert session.start("Something else.") is True
    fresh = waited(session)
    assert fresh["transcript"] == [{"who": "you", "text": "Something else."},
                                   {"who": "harness", "text": "A new first question?"}]
    assert fresh["session_id"] != stopped["session_id"] and fresh["questions"] == 0
    assert session.stop() is True and waited(session)["phase"] == "stopped"


def test_the_interview_runs_on_a_daemon_thread(make):
    session = make([NO_PLAN, QUESTION])
    session.start(OPENING)
    waited(session)
    threads = [thread for thread in threading.enumerate() if thread.name == "grounding-interview"]
    assert threads and all(thread.daemon for thread in threads)
    session.stop()
    waited(session)


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


def test_a_model_or_desk_that_cannot_be_made_ends_in_failed(make):
    def no_model():
        raise ValueError("unknown model provider: 'nobody'")

    def no_desk(conn):
        raise RuntimeError("no researcher\ntoday")

    session = GroundingSession(make.config, make.conn, model_factory=no_model)
    session.start(OPENING)
    assert waited(session)["error"] == "ValueError: unknown model provider: 'nobody'"

    session = make([QUESTION], desk_factory=no_desk)                # resumes the interview above
    failed = waited(session)
    assert failed["phase"] == "failed" and failed["error"] == "RuntimeError: no researcher today"
    assert make.state_path.exists()
    assert session.start("Start over.") is True                     # allowed after a failure
    waited(session)


def test_a_researcher_that_fails_does_not_end_the_interview(make):
    class Broken:
        def look_up(self, query):
            raise RuntimeError("no network")

    session = make([NO_PLAN, LOOK_UP, QUESTION], desk_factory=lambda conn: ResearchDesk(Broken(), conn))
    session.start(OPENING)
    asked = waited(session)
    assert asked["phase"] == "question"
    assert [(e["status"], e["error"]) for e in asked["research"]] == [("failed", "no network")]
    session.stop()
    waited(session)


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


def test_a_state_file_that_cannot_be_read_is_a_failure_not_a_crash(make):
    make.state_path.write_text("{ not json", encoding="utf-8")
    session = make([NO_PLAN, QUESTION])
    broken = session.snapshot()
    assert broken["phase"] == "failed" and "cannot be read" in broken["error"]
    assert session.start(OPENING) and waited(session)["phase"] == "question"
    session.stop()
    waited(session)


def test_a_saved_brief_is_shown_when_no_interview_is_under_way(make):
    save_brief(make_brief(), make.config.brief_dir,
               {"session_id": "session-9", "lookups": lookups_made(), "status": "confirmed"})
    session = make([NO_PLAN, QUESTION])
    shown = session.snapshot()
    assert shown["phase"] == "saved" and shown["brief"] == make_brief()
    assert shown["brief_status"] == "confirmed" and shown["session_id"] == "session-9"
    assert shown["saved"] == {"status": "confirmed", "json": str(make.config.brief_dir / "domain_brief.json"),
                              "page": str(make.config.brief_dir / "domain_brief.md")}
    assert [(e["query"], e["status"], e["sources"][0]["url"]) for e in shown["research"]] == [
        ("cash flow forecast", "found", SOURCE)]
    assert shown["transcript"] == [] and make.model.calls == []
    assert [session.answer("Hello."), session.accept(), session.stop()] == [False] * 3

    # A new interview can start from here; the old brief is no longer shown.
    assert session.start(OPENING) is True
    asked = waited(session)
    assert asked["phase"] == "question" and asked["brief"] is None and asked["research"] == []
    session.stop()
    waited(session)


def test_a_draft_is_shown_as_a_draft(make):
    bad = make_brief(definition_of_done=[])
    session = make([NO_PLAN, write(bad), write(bad), write(bad)])
    session.start(OPENING)
    saved = waited(session)
    assert saved["phase"] == "saved" and saved["brief_status"] == "draft" and saved["saved"]["status"] == "draft"
    assert saved["brief"] == bad
    assert saved["transcript"][-1]["who"] == "harness" and "draft" in saved["transcript"][-1]["text"]


def test_the_snapshot_can_be_read_while_the_interview_runs(make):
    session = make([PLAN, LOOK_UP, QUESTION, write()])
    stop, problems = threading.Event(), []

    def read():
        while not stop.is_set():
            try:
                json.dumps(session.snapshot())
            except Exception as error:      # pragma: no cover - only on a bug
                problems.append(error)

    reader = threading.Thread(target=read)
    reader.start()
    try:
        session.start(OPENING)
        waited(session)
        session.answer("A forecast.")
        waited(session)
        session.accept()
        assert waited(session)["phase"] == "saved"
    finally:
        stop.set()
        reader.join(5)
    assert problems == []
