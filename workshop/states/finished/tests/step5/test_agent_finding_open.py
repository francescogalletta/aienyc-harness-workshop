"""SPEC 9.7: while a finding is open: `run_module` and `save_input` are refused, no run is held at the gate, and replies
are held back."""
import json

import pytest

import step5_helpers as s5
from step5_helpers import (DATA_BLOCK, FINDING_FIRST, FINDING_OPEN, MESSAGE, WIDE_BRIEF, WIDE_MESSAGE, ask_finding, entry,
                           h, report, s4, summary_call, wide_block, wide_entry)

OK = "Nothing is left over each month."
RUN_ARGS = {"module": "monthly_surplus", "inputs": {"income": "4132.31", "spending": "4132.31"}, "assumptions": [],
            "expected": "about nothing"}
RUN = h.tool("run_module", RUN_ARGS)
OPEN = [summary_call(), report(entry())]                       # a message that opens finding 1


def tool_content(model, call_index, position=-1):
    return h.tool_message(model, call_index, position)["content"]


def asked(person):
    return [text for kind, text in person.log if kind == "ask"]


# ---- run_module and save_input are refused ----------------------------------------------------------------------------

def test_run_module_is_refused_and_nothing_runs(talk, conn, example_loaded):
    model, person = talk([*OPEN, RUN, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert tool_content(model, 3) == FINDING_OPEN.format(id=1)
    assert h.rows(conn, "calc_runs") == [] and ("say", "  (running monthly_surplus)") not in person.log
    assert s5.payloads(conn, "finding.refused") == [{"finding": 1, "tool": "run_module", "arguments": RUN_ARGS}]
    assert s5.actors(conn, "finding.refused") == ["harness"]


def test_nothing_else_happens_for_a_refused_run(talk, conn, example_loaded):
    talk([*OPEN, RUN, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    kinds = s5.kinds_after_start(conn)
    assert kinds[kinds.index("finding.opened"):kinds.index("ask.decision_asked")] == ["finding.opened", "finding.refused"]
    assert "ask.correction" not in kinds and "ask.gate" not in kinds


def test_save_input_is_refused_and_nothing_is_saved(talk, conn, example_loaded):
    save = h.save_input("monthly_spending", "4132.31", "from my files")
    model, _ = talk([*OPEN, save, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert tool_content(model, 3) == FINDING_OPEN.format(id=1)
    assert s5.saved_input(conn, "monthly_spending") is None and s5.events(conn, "ask.input_saved") == []
    assert s5.payloads(conn, "finding.refused") == [{"finding": 1, "tool": "save_input", "arguments": {
        "name": "monthly_spending", "value": "4132.31", "note": "from my files"}}]


@pytest.mark.parametrize("call, tool_name", [
    (h.run_module("no_such_module", {"income": "4132.31"}), "run_module"),
    (h.run_module(inputs={"income": "99999", "spending": "88888"}), "run_module"),
    (h.run_module(inputs={"income": "oops"}), "run_module"),
    (h.save_input("Not Snake", "4132.31"), "save_input"),
    (h.save_input("monthly_spending", ""), "save_input"),
    (h.save_input("monthly_spending", "777777"), "save_input"),
], ids=["unknown module", "unbacked inputs", "bad inputs", "bad name", "empty value", "unbacked value"])
def test_the_refusal_comes_before_every_other_check(talk, conn, example_loaded, call, tool_name):
    model, _ = talk([*OPEN, call, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert tool_content(model, 3) == FINDING_OPEN.format(id=1)
    [refused] = s5.payloads(conn, "finding.refused")
    assert refused["tool"] == tool_name and refused["finding"] == 1
    assert s5.events(conn, "ask.correction") == []


def test_both_calls_of_one_reply_are_refused_in_order(talk, conn, example_loaded):
    both = h.tools(("run_module", RUN_ARGS), ("save_input", {"name": "monthly_spending", "value": "4132.31", "note": "n"}))
    model, _ = talk([*OPEN, both, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert [m["content"] for m in model.calls[3]["messages"] if m["role"] == "tool"] == [FINDING_OPEN.format(id=1)] * 2
    assert [p["tool"] for p in s5.payloads(conn, "finding.refused")] == ["run_module", "save_input"]


def test_a_refused_call_does_not_count_as_a_run_request(talk, conn, example_loaded):
    model, _ = talk([*OPEN, RUN, RUN, RUN, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert len(s5.payloads(conn, "finding.refused")) == 3 and len(h.rows(conn, "calc_runs")) == 0


def test_request_module_is_not_refused_while_a_finding_is_open(talk, conn, example_loaded):
    request = h.tool("request_module", {"case": "step", "target": "s9", "works_out": "w", "from_what": "f",
                                        "gives": "g", "formula": "x", "why": "y"})
    model, _ = talk([*OPEN, request, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert s5.events(conn, "finding.refused") == [] and s5.events(conn, "ask.request_refused")


def test_the_oldest_open_finding_is_named(talk, conn):
    run = h.run_module(inputs={"income": "1150", "spending": "1150"}, assumptions=[], expected="about nothing")
    script = [report(wide_entry("rent"), wide_entry("gym")), run, ask_finding(1), run, ask_finding(2), run, h.say_text(OK)]
    model, _ = talk(script, ["1", "1", "/quit"], question=WIDE_MESSAGE, brief=WIDE_BRIEF)
    assert tool_content(model, 2) == FINDING_OPEN.format(id=1)
    assert tool_content(model, 4) == FINDING_OPEN.format(id=2)
    assert len(h.rows(conn, "calc_runs")) == 1
    assert [p["finding"] for p in s5.payloads(conn, "finding.refused")] == [1, 2]


def test_both_findings_are_noted_oldest_first(talk, example_loaded):
    script = [report(wide_entry("rent"), wide_entry("gym")), ask_finding(1), ask_finding(2), h.say_text(OK)]
    model, _ = talk(script, ["1", "1", "/quit"], question=WIDE_MESSAGE, brief=WIDE_BRIEF)
    notes = [s5.FINDING_NOTE.format(id=1, block=wide_block("rent")), s5.FINDING_NOTE.format(id=2, block=wide_block("gym"))]
    assert [m["content"] for m in model.calls[1]["messages"] if m["role"] == "user"] == [WIDE_MESSAGE, *notes]


# ---- the assumption gate holds no run ----------------------------------------------------------------------------------

ASSUMING = h.tool("run_module", {**RUN_ARGS, "assumptions": ["Spending stays the same."]})


def test_a_run_with_assumptions_is_not_shown_at_the_gate_while_a_finding_is_open(talk, conn, example_loaded):
    model, person = talk([*OPEN, ASSUMING, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert s4.GATE_QUESTION not in asked(person) and s5.events(conn, "ask.gate") == []
    assert tool_content(model, 3) == FINDING_OPEN.format(id=1)
    assert [d["kind"] for d in h.rows(conn, "decisions")] == ["finding"]


def test_once_the_finding_is_decided_the_gate_asks_as_before(talk, conn, example_loaded):
    model, person = talk([*OPEN, ASSUMING, ask_finding(1), ASSUMING, h.say_text(OK)], ["2", "yes", "/quit"])
    assert asked(person).count(s4.GATE_QUESTION) == 1
    assert [d["kind"] for d in h.rows(conn, "decisions")] == ["finding", "assumptions"]
    assert len(h.rows(conn, "calc_runs")) == 1


# ---- replies are held back ---------------------------------------------------------------------------------------------------

HELD = "It will take 99 months."


def test_a_reply_with_text_is_held_back_and_the_model_is_called_again(talk, conn, example_loaded):
    model, person = talk([*OPEN, h.say_text(HELD), ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert model.roles() == ["verifier", "verifier", "analyst", "analyst", "analyst"]
    assert s5.payloads(conn, "ask.correction") == [{"reason": "finding", "numbers": [], "text": HELD}]
    assert HELD not in asked(person) and HELD not in person.told
    assert s5.events(conn, "ask.withheld") == []
    assert [(m["role"], m["content"]) for m in model.calls[3]["messages"][-2:]] == [
        ("assistant", HELD), ("user", FINDING_FIRST.format(id=1))]


def test_the_held_reply_is_not_read_by_the_number_check(talk, conn, example_loaded):
    talk([*OPEN, h.say_text("It is 99 or 98 or 97."), ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    [correction] = s5.payloads(conn, "ask.correction")
    assert correction["reason"] == "finding" and correction["numbers"] == []


def test_the_oldest_finding_is_named_in_the_text_to_the_agent(talk, conn):
    script = [report(wide_entry("rent"), wide_entry("gym")), h.say_text(HELD), ask_finding(1), ask_finding(2), h.say_text(OK)]
    model, _ = talk(script, ["1", "1", "/quit"], question=WIDE_MESSAGE, brief=WIDE_BRIEF)
    assert model.calls[2]["messages"][-1] == {"role": "user", "content": FINDING_FIRST.format(id=1)}


def test_an_empty_reply_is_answered_as_in_step_two(talk, conn, example_loaded):
    model, _ = talk([*OPEN, h.say_text(""), ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert model.calls[3]["messages"][-1] == {"role": "user", "content": h.EMPTY_REPLY}
    assert s5.events(conn, "ask.correction") == []


def test_a_held_reply_does_not_use_the_correction_for_numbers(talk, conn, example_loaded):
    script = [*OPEN, h.say_text(HELD), ask_finding(1), h.say_text("It takes 99 months."), h.say_text(OK)]
    model, person = talk(script, ["1", "/quit"])
    reasons = [p["reason"] for p in s5.payloads(conn, "ask.correction")]
    assert reasons == ["finding", "reply"] and s5.events(conn, "ask.withheld") == []
    assert s5.payloads(conn, "ask.reply") == [{"text": OK}]


def test_after_the_decision_replies_are_shown(talk, conn, example_loaded):
    model, person = talk([*OPEN, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert asked(person)[-1] == OK and s5.events(conn, "ask.correction") == []


def test_every_held_reply_counts_towards_the_calls_of_a_message(talk, conn, example_loaded):
    script = [*OPEN, *[h.say_text(f"Hold {k}.") for k in range(10)]]
    model, person = talk(script, ["/quit"])
    assert len(model.of("analyst")) == 10
    assert len(s5.payloads(conn, "ask.correction")) == 10 and len(s5.events(conn, "ask.stopped")) == 1
    assert asked(person) == [h.TOO_MANY]


def test_a_finding_left_open_is_noted_again_at_the_next_message(talk, conn, example_loaded):
    script = [*OPEN, *[h.say_text(f"Hold {k}.") for k in range(10)], ask_finding(1), h.say_text(OK)]
    model, person = talk(script, ["How long will it take?", "2", "/quit"])
    assert model.roles().count("verifier") == 2                                  # the second message has no figure
    second = model.of("analyst")[10]["messages"]
    users = [m["content"] for m in second if m["role"] == "user"]
    assert users[-2:] == ["How long will it take?", s5.FINDING_NOTE.format(id=1, block=DATA_BLOCK)]
    assert s5.finding_rows(conn)[0]["status"] == "decided"


def test_a_finding_that_the_conversation_never_decides_stays_open(talk, conn, example_loaded, findings):
    talk([*OPEN, *[h.say_text(f"Hold {k}.") for k in range(10)]], ["/quit"])
    [row] = findings.list_findings(conn, session_id=s5.SESSION)
    assert row["status"] == "open" and row["decision"] is None and row["choice"] is None and row["chosen"] is None
