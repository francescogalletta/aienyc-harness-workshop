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
