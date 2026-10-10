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


def test_the_kinds_include_finding_last(decisions):
    assert decisions.KINDS == ("assumptions", "judgment", "build", "finding")


def test_a_finding_decision_is_recorded_with_its_event(decisions, conn):
    decision = record(decisions, conn)
    assert list(decision) == ["id", "ts", "session_id", "kind", "step", "question", "options", "choice", "words", "runs"]
    assert (decision["kind"], decision["step"], decision["question"], decision["options"]) == (
        "finding", None, DATA_BLOCK, OPTIONS_DATA)
    [(kind, actor, payload)] = h.events(conn, "ask.decision")
    assert actor == "person" and payload == {key: value for key, value in decision.items() if key not in ("ts", "session_id")}


def test_an_unknown_kind_is_still_refused(decisions, conn):
    with pytest.raises(ValueError, match="unknown kind: finding_"):
        record(decisions, conn, kind="finding_")


@pytest.mark.parametrize("choice, words, expected", [
    ("1", "1", "1. " + OPTIONS_DATA[0]), ("2", "option 2", "2. " + OPTIONS_DATA[1]),
    ("something else", "use 4,500", "something else")])
def test_choice_words_for_a_finding(decisions, conn, choice, words, expected):
    assert decisions.choice_words(record(decisions, conn, choice=choice, words=words)) == expected


def test_list_decisions_holds_findings_among_the_others(decisions, conn):
    record(decisions, conn)
    record(decisions, conn, kind="assumptions", question="g", options=[], choice="yes", words="yes")
    assert [d["kind"] for d in decisions.list_decisions(conn, session_id=SESSION)] == ["finding", "assumptions"]


def first_line(decision, chose):
    return f"{decision['id']}  {decision['ts']}  finding  step: -  chose: {chose}  runs: -"


def test_the_decisions_command_shows_a_finding(decisions, conn):
    decision = record(decisions, conn)
    result = h.run_cli(["decisions"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [first_line(decision, "2. " + OPTIONS_DATA[1]),
                                          *["  " + line for line in DATA_BLOCK.split("\n")], "  in their words: 2"]


def test_the_decisions_command_shows_a_finding_decided_in_words(decisions, conn):
    decision = record(decisions, conn, question=BRIEF_BLOCK, options=OPTIONS_BRIEF, choice="something else",
                      words="Neither, it is 1,300 now")
    lines = h.run_cli(["decisions"]).stdout.splitlines()
    assert lines[0] == first_line(decision, "something else") and lines[-1] == "  in their words: Neither, it is 1,300 now"
