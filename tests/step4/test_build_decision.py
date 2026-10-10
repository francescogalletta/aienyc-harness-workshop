"""SPEC 8.4: a request_module writes a decision of kind build, just after ask.module_outcome."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import decision_block, h

REPLY = h.say_text("Understood.")
ACCEPT3 = h.accepts(3)
NEW_SCRIPT = [h.request_module("new"), *h.yearly_script(), h.say_text("Built.")]
NEW_ANSWERS = ["yes", "yes", *ACCEPT3, "/quit"]


def build_decisions(conn):
    return [d for d in s4.decision_rows(conn) if d["kind"] == "build"]


def around_the_outcome(conn):
    kinds = s4.conversation_kinds(conn)
    at = kinds.index("ask.module_outcome")
    return kinds[at:at + 2]


@pytest.mark.parametrize("case, target, block, step_id, fixture", [
    ("step", "s1", h.STEP_BLOCK, "s1", "months_only")])
def test_a_declined_request_writes_a_build_decision_of_no(request, talk, conn, case, target, block, step_id, fixture):
    request.getfixturevalue(fixture)
    talk([h.request_module(case, target), REPLY], ["not now, thanks", "/quit"])
    [row] = s4.decision_rows(conn)
    assert (row["kind"], row["session_id"], row["step_id"], row["question"]) == ("build", h.SESSION, step_id, block)
    assert json.loads(row["options"]) == [] and json.loads(row["runs"]) == []
    assert (row["choice"], row["words"]) == ("no", "not now, thanks")


def test_a_built_step_writes_a_yes_for_its_step(talk, months_only, conn):
    script = [h.request_module("step", "s1"), *h.surplus_script(), h.say_text("Built.")]
    talk(script, ["yes", "yes", *ACCEPT3, "/quit"])
    [row] = s4.decision_rows(conn)
    assert (row["kind"], row["step_id"], row["choice"], row["words"], row["question"]) == (
        "build", "s1", "yes", "yes", h.STEP_BLOCK)
