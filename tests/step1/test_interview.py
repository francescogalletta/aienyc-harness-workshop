"""SPEC 4.4: the grounding interview. A scripted model asks, a scripted person answers."""
import json

import pytest

from harness import db
from harness.grounding import ReferenceResearcher, new_state, run_interview
from harness.grounding.interview import LIMIT_REACHED, ONE_QUESTION, WRAP_UP
from harness.model import ScriptedModel

from step1_helpers import SOURCE, make_brief

LOOK_UP = {"tool_calls": [{"name": "look_up", "arguments": {"query": "cash flow forecast"}}]}


def write(brief=None):
    return {"tool_calls": [{"name": "write_brief", "arguments": brief or make_brief()}]}


class Person:
    """Answers in order, and remembers everything shown to them."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked, self.told = [], []

    def ask(self, text):
        self.asked.append(text)
        return self.answers.pop(0)

    def say(self, text):
        self.told.append(text)


@pytest.fixture
def setup(tmp_path, reference_file):
    conn = db.connect(tmp_path / "harness.db")
    db.migrate(conn)

    def run(script, person, *, state=None, researcher=None, **options):
        model = ScriptedModel(script)
        state = state or new_state("session-1", "I want to stay on top of my cash flow.")
        saved = run_interview(model=model, researcher=researcher or ReferenceResearcher(reference_file),
                              ask=person.ask, say=person.say, conn=conn, state=state,
                              brief_dir=tmp_path / "brief", state_path=tmp_path / "state.json", **options)
        return saved, model, state

    run.conn, run.folder = conn, tmp_path
    return run


def kinds(conn):
    return [(row["kind"], row["actor"]) for row in db.list_events(conn)]


def test_a_whole_interview(setup):
    person = Person("The forecast one.", "A bank export.", "yes")
    saved, model, state = setup([
        LOOK_UP,
        {"text": "Do you mean a forecast of your balance, or what you have today?"},
        {"text": "What data do you have?"},
        write(),
    ], person)

    assert saved == {"status": "confirmed", "json": str(setup.folder / "brief" / "domain_brief.json"),
                     "page": str(setup.folder / "brief" / "domain_brief.md")}
    assert person.asked[:2] == ["Do you mean a forecast of your balance, or what you have today?",
                                "What data do you have?"]
    assert person.asked[2].startswith("Is this right?")
    assert any("PROPOSED BRIEF" in text for text in person.told)
    assert "  (looking up: cash flow forecast)" in person.told

    # The model was given the interviewer's instructions and exactly two tools.
    first = model.calls[0]
    assert "grounding interview" in first["system"] and "about 12 questions" in first["system"]
    assert "{max_questions}" not in first["system"]
    assert [tool.name for tool in first["tools"]] == ["look_up", "write_brief"]
    assert first["messages"] == [{"role": "user", "content": "I want to stay on top of my cash flow."}]

    # The lookup came back to the model as a tool result, with its source.
    after_lookup = model.calls[1]["messages"]
    assert after_lookup[1]["role"] == "assistant" and after_lookup[1]["tool_calls"][0]["name"] == "look_up"
    result = json.loads(after_lookup[2]["content"])
    assert after_lookup[2]["role"] == "tool" and result["found"] and result["sources"][0]["url"] == SOURCE

    saved_brief = json.loads((setup.folder / "brief" / "domain_brief.json").read_text(encoding="utf-8"))
    assert saved_brief["meta"]["status"] == "confirmed" and saved_brief["meta"]["session_id"] == "session-1"
    assert saved_brief["meta"]["lookups"][0]["query"] == "cash flow forecast"
    assert not (setup.folder / "state.json").exists()        # nothing left to resume

    # Everything said is in the database.
    assert kinds(setup.conn) == [
        ("grounding.lookup", "agent"),
        ("grounding.question", "agent"), ("grounding.answer", "person"),
        ("grounding.question", "agent"), ("grounding.answer", "person"),
        ("grounding.brief_written", "harness"),
    ]
    events = db.list_events(setup.conn, session_id="session-1")
    assert json.loads(events[2]["payload"]) == {"text": "The forecast one."}
    assert json.loads(events[-1]["payload"])["status"] == "confirmed"


def test_one_question_at_a_time_is_enforced_by_the_harness(setup):
    person = Person("Monthly.", "yes")
    saved, model, _ = setup([
        {"text": "How often? And which accounts? Also, what data do you have?"},
        {"text": "How often do you want to check in?"},
        LOOK_UP,
        write(),
    ], person)
    assert saved["status"] == "confirmed"
    assert person.asked[0] == "How often do you want to check in?"      # the person never saw the first try
    sent_back = model.calls[1]["messages"]
    assert sent_back[-2] == {"role": "assistant",
                             "content": "How often? And which accounts? Also, what data do you have?"}
    assert sent_back[-1] == {"role": "user", "content": ONE_QUESTION}
    assert ("grounding.correction", "harness") in kinds(setup.conn)


def test_text_sent_with_a_tool_call_is_not_shown(setup):
    person = Person("yes")
    setup([{"text": "Let me check. Which account is it?", **LOOK_UP}, write()], person)
    assert not any("Which account" in text for text in person.told + person.asked)


def test_a_brief_that_fails_the_checks_goes_back_to_the_model(setup):
    bad = make_brief()
    bad["process"][2]["method"] = "my own trick"
    person = Person("yes")
    saved, model, state = setup([LOOK_UP, write(bad), write()], person)
    assert saved["status"] == "confirmed" and state["rejections"] == 1
    refusal = model.calls[2]["messages"][-1]
    assert refusal["role"] == "tool" and refusal["is_error"] is True
    assert "not accepted" in refusal["content"] and "'s3'" in refusal["content"]
    assert len(person.asked) == 1                                       # only the valid brief was shown
    assert ("grounding.brief_rejected", "harness") in kinds(setup.conn)


def test_a_source_that_was_never_looked_up_is_refused(setup):
    person = Person("yes")
    saved, model, _ = setup([write(), LOOK_UP, write()], person)       # first try: no lookup made yet
    assert saved["status"] == "confirmed"
    assert SOURCE in model.calls[1]["messages"][-1]["content"]


def test_three_failed_briefs_are_saved_as_a_draft(setup):
    bad = make_brief(definition_of_done=[])
    person = Person()
    saved, _, _ = setup([write(bad), write(bad), write(bad)], person)
    assert saved["status"] == "draft"
    page = (setup.folder / "brief" / "domain_brief.md").read_text(encoding="utf-8")
    assert "Draft, not confirmed" in page and "definition_of_done" in page
    assert person.asked == []                                           # a failing brief is never shown for approval


def test_the_person_can_ask_for_changes(setup):
    person = Person("Make it weekly, not monthly.", "yes")
    saved, model, _ = setup([LOOK_UP, write(), write()], person)
    assert saved["status"] == "confirmed"
    reply = model.calls[2]["messages"][-1]
    assert reply["role"] == "tool" and not reply.get("is_error")
    assert "did not confirm" in reply["content"] and "Make it weekly, not monthly." in reply["content"]
    assert ("grounding.brief_changes", "person") in kinds(setup.conn)


def test_the_question_limit_and_wrap(setup):
    person = Person("First answer.", "yes")
    _, model, state = setup([{"text": "One question?"}, LOOK_UP, write()], person, max_questions=1)
    assert state["questions"] == 1
    assert model.calls[1]["messages"][-1] == {"role": "user",
                                              "content": "First answer.\n\n" + LIMIT_REACHED}

    person = Person("/wrap", "yes")
    _, model, _ = setup([{"text": "One question?"}, LOOK_UP, write()], person)
    assert model.calls[1]["messages"][-1] == {"role": "user", "content": WRAP_UP}


def test_quit_and_resume(setup):
    person = Person("An answer.", "/quit")
    saved, model, state = setup([{"text": "First question?"}, {"text": "Second question?"}], person)
    assert saved is None
    stored = json.loads((setup.folder / "state.json").read_text(encoding="utf-8"))
    assert stored["session_id"] == "session-1" and stored["questions"] == 1
    assert stored["messages"][-1] == {"role": "assistant", "content": "Second question?"}

    # Resuming asks the waiting question again without calling the model first.
    person = Person("The second answer.", "yes")
    saved, model, _ = setup([LOOK_UP, write()], person, state=stored)
    assert person.asked[0] == "Second question?"
    assert saved["status"] == "confirmed"
    assert model.calls[0]["messages"][-1] == {"role": "user", "content": "The second answer."}
    questions = [row for row in db.list_events(setup.conn) if row["kind"] == "grounding.question"]
    assert len(questions) == 2                                          # not recorded twice


def test_lookups_that_cannot_run(setup):
    class Broken:
        def look_up(self, query):
            raise RuntimeError("no network\ntoday")

    long_query = "x" * 101
    person = Person("yes")
    _, model, state = setup([
        {"tool_calls": [{"name": "look_up", "arguments": {"query": long_query}},
                        {"name": "look_up", "arguments": {"query": "net cash flow"}},
                        {"name": "nonsense", "arguments": {}}]},
        write(make_brief(glossary=[{"term": "Typical month", "definition": "Usual spending."}],
                         process=[{"id": "s1", "name": "Ask", "kind": "input", "needs": [], "produces": "x"}])),
    ], person, researcher=Broken())
    results = model.calls[1]["messages"][-3:]
    assert all(result["role"] == "tool" and result["is_error"] for result in results)
    assert "at most 100 characters" in results[0]["content"]
    assert results[1]["content"] == "The lookup failed: no network today"
    assert "nonsense" in results[2]["content"]
    assert state["lookups"] == []
    assert "  (looking up: net cash flow)" in person.told and not any(long_query in t for t in person.told)


def test_several_lookups_in_one_turn_keep_their_order(setup):
    person = Person("yes")
    _, model, state = setup([
        {"tool_calls": [{"name": "look_up", "arguments": {"query": "balance"}},
                        {"name": "look_up", "arguments": {"query": "something unknown"}},
                        {"name": "look_up", "arguments": {"query": "cash forecast"}}]},
        write(),
    ], person)
    results = [json.loads(m["content"]) for m in model.calls[1]["messages"][-3:]]
    assert [r["query"] for r in results] == ["balance", "something unknown", "cash forecast"]
    assert [r["found"] for r in results] == [True, False, True]
    assert [l["query"] for l in state["lookups"]] == ["balance", "something unknown", "cash forecast"]
