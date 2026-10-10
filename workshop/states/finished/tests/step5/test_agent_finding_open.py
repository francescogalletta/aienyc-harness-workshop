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




def test_save_input_is_refused_and_nothing_is_saved(talk, conn, example_loaded):
    save = h.save_input("monthly_spending", "4132.31", "from my files")
    model, _ = talk([*OPEN, save, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert tool_content(model, 3) == FINDING_OPEN.format(id=1)
    assert s5.saved_input(conn, "monthly_spending") is None and s5.events(conn, "ask.input_saved") == []
    assert s5.payloads(conn, "finding.refused") == [{"finding": 1, "tool": "save_input", "arguments": {
        "name": "monthly_spending", "value": "4132.31", "note": "from my files"}}]














# ---- the assumption gate holds no run ----------------------------------------------------------------------------------

ASSUMING = h.tool("run_module", {**RUN_ARGS, "assumptions": ["Spending stays the same."]})






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










def test_after_the_decision_replies_are_shown(talk, conn, example_loaded):
    model, person = talk([*OPEN, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert asked(person)[-1] == OK and s5.events(conn, "ask.correction") == []






