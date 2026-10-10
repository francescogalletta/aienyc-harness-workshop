"""SPEC 8.2: a run that takes something as given is shown to the person, who says yes or no, before it runs."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (ACCEPT_WORDS, ASSUME, EXPECT, GATE_QUESTION, SESSION, THINKING, decision_rows, h, quiet,
                           result_of, run, run_args)

BLOCK = s4.gate_block(s4.surplus_item())
REPLY = "monthly_surplus gives 2,000."
SCRIPT = [run(), h.say_text(REPLY)]


def declined_script():
    return [run(), h.say_text("Understood, nothing was run.")]


def test_the_block_then_the_question_then_the_run_then_the_next_call(ask_agent):
    """SPEC 8.6, 1: a run and its reply still take two agent calls, and a gate and a decision call no model."""
    model, person = ask_agent(SCRIPT, ["yes", "/quit"])
    assert quiet(person) == [
        ("call", "analyst"), ("say", BLOCK), ("ask", GATE_QUESTION), ("say", "  (running monthly_surplus)"),
        ("call", "analyst"), ("ask", REPLY)]
    assert model.roles() == ["analyst", "analyst"]


@pytest.mark.parametrize("answer", ["not now"])
def test_anything_else_is_a_no_and_the_leniency_of_a_build_request_does_not_apply(ask_agent, conn, answer):
    model, person = ask_agent(declined_script(), [answer, "/quit"])
    assert h.rows(conn, "calc_runs") == [] and h.events(conn, "calc.run") == []
    [decision] = decision_rows(conn)
    assert decision["choice"] == "no" and decision["words"] == answer
    assert "  (running monthly_surplus)" not in person.told


def test_a_no_gives_the_call_the_result_not_run_with_what_the_person_said(ask_agent):
    model, _ = ask_agent(declined_script(), ["  Not with those  ", "/quit"])
    result = h.tool_message(model, 1)
    assert not result.get("is_error")
    assert result["content"] == json.dumps({"outcome": "not_run", "said": "Not with those"})
    assert list(json.loads(result["content"])) == ["outcome", "said"]
