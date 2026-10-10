"""SPEC 8.2: which run_module calls are held for a yes, and which are handled as before."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (ASSUME, EXPECT, GATE_QUESTION, OTHER_ASSUME, SESSION, decision_rows, h, result_of, run,
                           run_args, run_pair)

OK = "Done."
HALF = {"income": "5000", "spending": "3000"}


def gate_asks(person):
    return person.asked.count(GATE_QUESTION)


def tool_contents(model, call_index):
    return [m["content"] for m in model.calls[call_index]["messages"] if m["role"] == "tool"]


def shown_gate(person):
    return [t for t in person.told if t.startswith(s4.GATE_INTRO)]


def test_no_assumptions_no_gate(ask_agent, conn):
    _, person = ask_agent([run(assumptions=[]), h.say_text(OK)])
    assert gate_asks(person) == 0 and shown_gate(person) == [] and len(h.rows(conn, "calc_runs")) == 1
    assert h.events(conn, "ask.gate") == [] and decision_rows(conn) == []


def mixed_reply():
    return run_pair(
        run(assumptions=[]),                                                  # 1: no assumptions: not held
        run(inputs={"income": "6000", "spending": "4000"}, assumptions=ASSUME, expected="the good month"),   # 2: held
        run(module="ghost"),                                                  # 3: not registered: not held
        run(inputs={"income": "5000", "spending": "2999"}),                   # 4: unbacked inputs: not held
        run(module="months_to_goal", inputs={"target": "10000", "monthly_saving": "2000"},
            assumptions=OTHER_ASSUME, expected="a handful of months"),        # 5: held (2000 is in the question)
        run(inputs={"income": "5000"}),                                       # 6: does not fit: not held
        run(expected=""))                                                     # 7: no expectation: not held


def test_one_reply_gets_one_gate_with_the_held_calls_in_reply_order(ask_agent, conn):
    model, person = ask_agent([mixed_reply(), h.say_text(OK)], ["yes", "/quit"], question=s4.TWO_CASES)
    block = s4.gate_block(s4.surplus_item(ASSUME, "the good month"), s4.months_item(OTHER_ASSUME, "a handful of months"))
    assert shown_gate(person) == [block] and gate_asks(person) == 1
    [decision] = decision_rows(conn)
    assert decision["question"] == block
    [(_, _, payload)] = h.events(conn, "ask.gate")
    assert [c["module"] for c in payload["calls"]] == ["monthly_surplus", "months_to_goal"]
    assert payload["calls"][0]["inputs"] == {"income": "6000", "spending": "4000"} and payload["block"] == block


def test_one_no_gives_every_held_call_not_run_and_the_others_go_on(ask_agent, conn):
    model, person = ask_agent([mixed_reply(), h.say_text(OK)], ["Not with those", "/quit"], question=s4.TWO_CASES)
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    said = json.dumps({"outcome": "not_run", "said": "Not with those"})
    assert messages[1]["content"] == said and messages[4]["content"] == said
    assert json.loads(messages[0]["content"])["output"] == "2000"                      # the call without assumptions ran
    assert messages[2]["content"] == h.NOT_REGISTERED.format(name="ghost")
    assert [r["module"] for r in h.rows(conn, "calc_runs")] == ["monthly_surplus"]
    assert gate_asks(person) == 1 and [d["choice"] for d in decision_rows(conn)] == ["no"]


def test_a_set_accepted_is_not_asked_about_again(ask_agent):
    script = [run(), run(inputs={"income": "6000", "spending": "4000"}), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "/quit"], question=s4.TWO_CASES)
    assert gate_asks(person) == 1


def test_an_unbacked_number_in_an_assumption_shows_nothing_and_refuses_the_call(ask_agent, conn):
    args = run_args(assumptions=["Assuming a 7.25% return on savings."], expected="what comes in")
    model, person = ask_agent([h.tool("run_module", args), h.say_text(OK)])
    result = h.tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == s4.GATE_UNBACKED.format(numbers="7.25%")
    assert shown_gate(person) == [] and gate_asks(person) == 0
    assert h.events(conn, "ask.gate") == [] and decision_rows(conn) == [] and h.rows(conn, "calc_runs") == []


def s3_with_description(files, description):
    return s4.s3.with_spec(files, description=description)


YEARLY_ARGS = {"module": "yearly_cost", "inputs": {"monthly": "250"}, "assumptions": ["Costs stay the same all year."],
               "expected": "twelve times the monthly cost"}
