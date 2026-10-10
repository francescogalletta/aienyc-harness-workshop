"""SPEC 4.4 and 4.6: the grounding interview. A scripted model asks, a scripted person answers."""
import json

import pytest

from harness import db
from harness.grounding import ReferenceResearcher, ResearchDesk, new_state, run_interview
from harness.grounding.interview import CONFIRM, LIMIT_REACHED, MAX_LOOKUPS, ONE_QUESTION, WRAP_UP
from harness.model import ScriptedModel

from step1_helpers import LOOK_UP, PLAN, SOURCE, make_brief, write


def look_up(*queries):
    return {"tool_calls": [{"name": "look_up", "arguments": {"query": query}} for query in queries]}


class Counting:
    """A researcher that counts what reaches it."""

    def __init__(self, researcher):
        self.researcher, self.queries = researcher, []

    def look_up(self, query):
        self.queries.append(query)
        return self.researcher.look_up(query)


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

    def run(script, person, *, state=None, researcher=None, plan=False, **options):
        """Run an interview. Without `plan=True` the script starts at the interviewer's first turn."""
        model = ScriptedModel(script)
        state = state or new_state("session-1", "I want to stay on top of my cash flow.")
        desk = ResearchDesk(researcher or run.researcher, conn)
        saved = run_interview(model=model, researcher=desk, ask=person.ask, say=person.say, conn=conn,
                              state=state, brief_dir=tmp_path / "brief", state_path=tmp_path / "state.json",
                              plan=plan, **options)
        return saved, model, state

    run.conn, run.folder = conn, tmp_path
    run.researcher = Counting(ReferenceResearcher(reference_file))
    return run


def kinds(conn):
    return [(row["kind"], row["actor"]) for row in db.list_events(conn)]


def test_a_whole_interview(setup):
    person = Person("The forecast one.", "A bank export.", "/accept")
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
    assert person.asked[2] == CONFIRM == "Type /accept to accept this brief, or say what should change."
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
    assert result["origin"] == "reference" and "repeat" not in result and "note" not in result

    saved_brief = json.loads((setup.folder / "brief" / "domain_brief.json").read_text(encoding="utf-8"))
    assert saved_brief["meta"]["status"] == "confirmed" and saved_brief["meta"]["session_id"] == "session-1"
    assert saved_brief["meta"]["lookups"][0]["query"] == "cash flow forecast"
    assert not (setup.folder / "state.json").exists()        # nothing left to resume
    assert state["research"] == [{
        "query": "cash flow forecast", "status": "found", "name": "cash flow forecast",
        "definition": "A plan of the money expected in and out over a future period.",
        "sources": [{"title": "Example: cash flow forecast", "url": SOURCE}],
        "origin": "reference", "planned": False, "cached": False}]
    assert state["proposed"] is None

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


def test_the_plan_runs_first_and_tells_the_interviewer_what_is_ready(setup):
    person = Person("/accept")
    plan = {"tool_calls": [{"name": "plan_research", "arguments": {
        "terms": ["cash flow forecast", "quantum budgeting", "balance"]}}]}
    saved, model, state = setup([plan, look_up("cash-flow forecast", "quantum budgeting"), write()],
                                person, plan=True)
    assert saved["status"] == "confirmed"

    # The planner saw the opening statement and its own instructions, and one tool.
    assert "prepare a grounding interview" in model.calls[0]["system"]
    assert model.calls[0]["messages"] == [{"role": "user", "content": "I want to stay on top of my cash flow."}]
    assert [tool.name for tool in model.calls[0]["tools"]] == ["plan_research"]
    assert person.told[0] == "  (reading up on: cash flow forecast, quantum budgeting, balance)"

    # The interviewer was told what is ready, at the end of the opening message.
    assert model.calls[1]["messages"] == [{"role": "user", "content": (
        "I want to stay on top of my cash flow.\n\n"
        "[harness] Already read up on, ready for look_up: cash flow forecast, balance. "
        "No source found for: quantum budgeting.")}]
    assert [tool.name for tool in model.calls[1]["tools"]] == ["look_up", "write_brief"]

    assert [(e["query"], e["status"], e["planned"]) for e in state["research"]] == [
        ("cash flow forecast", "found", True), ("quantum budgeting", "not_found", True),
        ("balance", "found", True)]
    assert [l["query"] for l in state["lookups"]] == ["cash flow forecast", "balance"]

    # Looking up a planned term is instant: no lookup, nothing said, nothing recorded.
    ready, missing = model.calls[2]["messages"][-2:]
    assert json.loads(ready["content"])["repeat"] is True and not ready.get("is_error")
    assert json.loads(ready["content"])["sources"][0]["url"] == SOURCE
    assert missing["is_error"] is True
    assert missing["content"] == 'No source was found for "quantum budgeting" earlier. Do not look it up again.'
    assert setup.researcher.queries == ["cash flow forecast", "quantum budgeting", "balance"]
    assert not any("looking up" in text for text in person.told)
    assert kinds(setup.conn) == [("grounding.research_plan", "agent"), ("grounding.brief_written", "harness")]
    plan_event = db.list_events(setup.conn, kind="grounding.research_plan")[0]
    assert json.loads(plan_event["payload"]) == {"terms": ["cash flow forecast", "quantum budgeting", "balance"]}


def test_a_term_is_looked_up_once(setup):
    person = Person("/accept")
    _, model, state = setup([
        look_up("cash forecast", "something unknown"),
        # Asked again: by the same words, by the standard name, twice in one turn.
        look_up("Cash  Forecast", "cash-flow forecast", "something_unknown", "balance", "BALANCE"),
        write(),
    ], person)
    assert setup.researcher.queries == ["cash forecast", "something unknown", "balance"]

    again, by_name, unknown, new, twice = model.calls[2]["messages"][-5:]
    for result in (again, by_name):
        lookup = json.loads(result["content"])
        assert lookup["repeat"] is True and lookup["found"] and lookup["query"] == "cash forecast"
        assert not result.get("is_error")
    assert unknown["is_error"] is True
    assert unknown["content"] == 'No source was found for "something_unknown" earlier. Do not look it up again.'
    assert "repeat" not in json.loads(new["content"])
    assert json.loads(twice["content"])["repeat"] is True

    # A repeat says nothing to the person, records nothing and adds nothing to the state.
    assert [text for text in person.told if "looking up" in text] == [
        "  (looking up: cash forecast)", "  (looking up: something unknown)", "  (looking up: balance)"]
    assert len(db.list_events(setup.conn, kind="grounding.lookup")) == 3
    assert [e["query"] for e in state["research"]] == ["cash forecast", "something unknown", "balance"]
    assert [l["query"] for l in state["lookups"]] == ["cash forecast", "balance"]


def test_a_failed_lookup_is_not_tried_again(setup):
    class Broken:
        def __init__(self):
            self.queries = []

        def look_up(self, query):
            self.queries.append(query)
            raise RuntimeError("no network")

    broken = Broken()
    brief = make_brief(glossary=[], process=[{"id": "s1", "name": "Ask", "kind": "input",
                                              "needs": [], "produces": "x"}])
    _, model, _ = setup([look_up("net cash flow"), look_up("net cash flow"), write(brief)],
                        Person("/accept"), researcher=broken)
    assert broken.queries == ["net cash flow"]
    assert model.calls[2]["messages"][-1]["content"] == (
        'No source was found for "net cash flow" earlier. Do not look it up again.')


def test_the_lookup_limit(setup):
    assert MAX_LOOKUPS == 12
    terms = [f"term {number}" for number in range(1, 14)]
    person = Person("/accept")
    _, model, state = setup([
        PLAN,                                                   # planned terms do not count
        look_up(*terms[:6]), look_up(*terms[6:11]),
        look_up(terms[11], terms[12], "term 1", "cash flow forecast"),
        write(),
    ], person, plan=True)
    twelfth, thirteenth, repeat, planned = model.calls[4]["messages"][-4:]
    assert json.loads(twelfth["content"])["query"] == "term 12"
    assert thirteenth["is_error"] is True and thirteenth["content"] == (
        "The lookup limit for this interview is used up. Carry on with what you have.")
    assert "earlier" in repeat["content"]                       # a known term is still answered
    assert json.loads(planned["content"])["repeat"] is True
    assert len(state["research"]) == 13 and len(setup.researcher.queries) == 13
    assert "  (looking up: term 13)" not in person.told
