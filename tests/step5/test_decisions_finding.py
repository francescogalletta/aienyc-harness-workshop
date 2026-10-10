"""SPEC 8.1 and 9.7 (step 5): the decision of kind `finding`: the record, `choice_words`, `python -m harness decisions`."""
import json

import pytest

import step5_helpers as s5
from step5_helpers import BRIEF_BLOCK, DATA_BLOCK, OPTIONS_BRIEF, OPTIONS_DATA, SESSION, h


def record(decisions, conn, **changes):
    arguments = {"session_id": SESSION, "kind": "finding", "step_id": None, "question": DATA_BLOCK, "options": OPTIONS_DATA,
                 "choice": "2", "words": "2", "runs": []}
    arguments.update(changes)
    return decisions.record_decision(conn, **arguments)




def test_a_finding_decision_is_recorded_with_its_event(decisions, conn):
    decision = record(decisions, conn)
    assert list(decision) == ["id", "ts", "session_id", "kind", "step", "question", "options", "choice", "words", "runs"]
    assert (decision["kind"], decision["step"], decision["question"], decision["options"]) == (
        "finding", None, DATA_BLOCK, OPTIONS_DATA)
    [(kind, actor, payload)] = h.events(conn, "ask.decision")
    assert actor == "person" and payload == {key: value for key, value in decision.items() if key not in ("ts", "session_id")}








def first_line(decision, chose):
    return f"{decision['id']}  {decision['ts']}  finding  step: -  chose: {chose}  runs: -"




