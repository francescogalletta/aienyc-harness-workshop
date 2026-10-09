"""SPEC 4.6: the research desk remembers lookups, and the plan reads up before the first question."""
import json
import threading

import pytest

from harness import db
from harness.grounding import Lookup, ReferenceResearcher, ResearchDesk, plan_research
from harness.model import ScriptedModel

from step1_helpers import SOURCE


class Counting:
    def __init__(self, researcher):
        self.researcher, self.queries = researcher, []

    def look_up(self, query):
        self.queries.append(query)
        return self.researcher.look_up(query)


@pytest.fixture
def conn(tmp_path):
    conn = db.connect(tmp_path / "harness.db")
    assert "0002_lookups.sql" in db.migrate(conn)
    return conn


@pytest.fixture
def researcher(reference_file):
    return Counting(ReferenceResearcher(reference_file))


def test_a_lookup_comes_back_as_a_research_entry(conn, researcher):
    entry = ResearchDesk(researcher, conn).look_up("cash forecast")
    assert entry == {"query": "cash forecast", "status": "found", "name": "cash flow forecast",
                     "definition": "A plan of the money expected in and out over a future period.",
                     "sources": [{"title": "Example: cash flow forecast", "url": SOURCE}],
                     "origin": "reference", "planned": False, "cached": False}
    missing = ResearchDesk(researcher, conn).look_up("quantum budgeting")
    assert missing == {"query": "quantum budgeting", "status": "not_found", "name": "", "definition": "",
                       "sources": [], "origin": "reference", "planned": False, "cached": False}


def test_a_term_asked_before_is_not_fetched_again(conn, researcher, tmp_path):
    desk = ResearchDesk(researcher, conn)
    first = desk.look_up("cash forecast")
    again = desk.look_up("Cash-Forecast")              # the same key: case, hyphens and spaces aside
    assert researcher.queries == ["cash forecast"]
    assert again == {**first, "query": "Cash-Forecast", "cached": True}

    # It is in the database, so another desk, on another day, has it too.
    other = ResearchDesk(researcher, db.connect(tmp_path / "harness.db"))
    assert other.look_up("cash_forecast")["cached"] is True
    assert researcher.queries == ["cash forecast"]


def test_a_found_lookup_is_also_remembered_under_its_standard_name(conn, researcher):
    desk = ResearchDesk(researcher, conn)
    desk.look_up("cash forecast")
    by_name = desk.look_up("Cash flow forecast")
    assert by_name["cached"] is True and by_name["name"] == "cash flow forecast"
    assert researcher.queries == ["cash forecast"]
    rows = conn.execute("SELECT key, query, name, sources, origin, looked_up_at FROM lookups ORDER BY key")
    stored = [tuple(row) for row in rows]
    assert [row[:3] for row in stored] == [("cash flow forecast", "cash forecast", "cash flow forecast"),
                                           ("cash forecast", "cash forecast", "cash flow forecast")]
    assert json.loads(stored[0][3]) == [{"title": "Example: cash flow forecast", "url": SOURCE}]
    assert stored[0][4] == "reference" and stored[0][5].endswith("+00:00")


def test_only_found_lookups_are_stored(conn, researcher):
    class Broken:
        def look_up(self, query):
            raise RuntimeError("no network\ntoday")

    desk = ResearchDesk(researcher, conn)
    assert desk.look_up("quantum budgeting")["status"] == "not_found"
    assert desk.look_up("quantum budgeting")["cached"] is False       # asked again: it may exist by now
    assert researcher.queries == ["quantum budgeting", "quantum budgeting"]

    failed = ResearchDesk(Broken(), conn).look_up("net cash flow")
    assert failed["status"] == "failed" and failed["error"] == "no network today"
    assert failed["sources"] == [] and failed["planned"] is False and failed["cached"] is False
    assert conn.execute("SELECT count(*) FROM lookups").fetchone()[0] == 0


def test_look_up_many_runs_side_by_side_and_keeps_the_order(conn):
    together = threading.Barrier(3, timeout=5)

    class Meeting:
        """Answers only once three lookups are waiting at the same time."""

        def look_up(self, query):
            together.wait()
            return Lookup(query, query != "b", name=query.upper(), definition="Words.",
                          sources=({"title": "t", "url": f"https://example.org/{query}"},), origin="test")

    desk = ResearchDesk(Meeting(), conn)
    entries = desk.look_up_many(["a", "b", "c"])
    assert [entry["query"] for entry in entries] == ["a", "b", "c"]
    assert [entry["status"] for entry in entries] == ["found", "not_found", "found"]
    assert desk.looking() == []                                # nothing is with the researcher now
    assert desk.look_up_many([]) == []


def test_look_up_many_mixes_remembered_and_new(conn, researcher):
    desk = ResearchDesk(researcher, conn)
    desk.look_up("balance")
    entries = desk.look_up_many(["cash forecast", "balance", "Cash Forecast"])
    assert [entry["query"] for entry in entries] == ["cash forecast", "balance", "Cash Forecast"]
    assert [entry["cached"] for entry in entries] == [False, True, False]
    assert researcher.queries == ["balance", "cash forecast"]         # one request per term


def test_the_desk_shows_what_it_is_looking_up(conn):
    started, finish = threading.Event(), threading.Event()

    class Slow:
        def look_up(self, query):
            started.set()
            assert finish.wait(5)
            return Lookup(query, False)

    desk = ResearchDesk(Slow(), conn)
    seen = []

    def watch():
        assert started.wait(5)
        seen.extend(desk.looking())
        finish.set()

    watcher = threading.Thread(target=watch)
    watcher.start()
    desk.look_up("sinking fund")
    watcher.join(5)
    assert seen == ["sinking fund"] and desk.looking() == []


def plan(*terms):
    return ScriptedModel([{"tool_calls": [{"name": "plan_research", "arguments": {"terms": list(terms)}}]}])


def test_plan_research_reads_up_on_the_terms_the_model_names(conn, researcher):
    model, said = plan("cash flow forecast", "quantum budgeting"), []
    entries = plan_research(model, ResearchDesk(researcher, conn), "I want to plan my money.", say=said.append)
    assert [(e["query"], e["status"], e["planned"]) for e in entries] == [
        ("cash flow forecast", "found", True), ("quantum budgeting", "not_found", True)]
    assert said == ["  (reading up on: cash flow forecast, quantum budgeting)"]

    call = model.calls[0]
    assert "prepare a grounding interview" in call["system"]            # the given planner.md
    assert call["messages"] == [{"role": "user", "content": "I want to plan my money."}]
    assert [tool.name for tool in call["tools"]] == ["plan_research"]
    schema = call["tools"][0].input_schema
    assert schema["properties"]["terms"] == {"type": "array", "items": {"type": "string"}}


def test_plan_research_filters_the_terms(conn, researcher):
    model = plan("balance", "", "   ", "x" * 101, "Balance", "cash-flow forecast", "cash flow forecast", 7,
                 "one", "two", "three", "four", "five")
    said = []
    entries = plan_research(model, ResearchDesk(researcher, conn), "Help.", say=said.append)
    # Empty, too long, repeated and non-text terms are dropped, then at most six are kept.
    assert [entry["query"] for entry in entries] == ["balance", "cash-flow forecast", "one", "two", "three", "four"]
    assert said == ["  (reading up on: balance, cash-flow forecast, one, two, three, four)"]
    assert all(entry["planned"] for entry in entries)


def test_the_plan_is_empty_when_the_model_names_nothing_or_fails(conn, researcher):
    class Unreachable:
        def complete(self, **_):
            raise RuntimeError("cannot reach the model")

    desk, said = ResearchDesk(researcher, conn), []
    for model in (ScriptedModel([{"text": "No need."}]),
                  ScriptedModel([{"tool_calls": [{"name": "look_up", "arguments": {"query": "balance"}}]}]),
                  plan(), plan("", "y" * 200),
                  ScriptedModel([{"tool_calls": [{"name": "plan_research", "arguments": {"terms": "balance"}}]}]),
                  ScriptedModel([]), Unreachable()):
        assert plan_research(model, desk, "Help.", say=said.append) == []
    assert said == [] and researcher.queries == []
