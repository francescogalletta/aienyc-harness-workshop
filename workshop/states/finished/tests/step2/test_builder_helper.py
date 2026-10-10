"""SPEC 5.7, the example helper: free text about a worked example gets one model call with the `respond` tool."""
import pytest

import step2_helpers as h
from harness.calc.values import from_json
from harness.model import ScriptExhausted
from step2_helpers import (CONFIRM_ANSWER, CONFIRM_EXAMPLE, GOAL, NOT_UNDERSTOOD, NOTE_KEPT, PARTICULAR, READING_REPLY,
                           REASON_STOPPED, events, only_step, payloads, propose_examples, propose_spec, ranged_examples,
                           ranged_spec, respond, say_text, saved_spec, sections, tool, tools)

SPEC = saved_spec(ranged_spec(), "s1")
EX1, EX2, _ = ranged_examples()
PROPOSED = EX1["expected"]
ANSWER = {"low": "13000", "expected": "17500", "high": "23000"}
REPLY = "expected should be 17,500, the rest is fine"
ANSWER_SHOWN = "  Your answer:\n    low: 13000\n    expected: 17500\n    high: 23000"
CORRECT = respond("correct", answer=ANSWER)


def run(build, answers, *calls, spec=None):
    """Answer the plan with yes, then the examples of `ranged_spec` with `answers`. `calls` are the helper's replies."""
    script = [propose_spec(spec or ranged_spec()), propose_examples(ranged_examples()), *calls]
    return build(script, ["yes", *answers], brief=only_step("s1"))


def after_helper(person, n=0):
    """What was said and asked after the n-th call of the helper."""
    marks = [i for i, entry in enumerate(person.log) if entry == ("call", "example_helper")]
    return [entry for entry in person.log[marks[n] + 1:] if entry[0] != "call"]


def decisions(conn):
    return [(p["index"], p["decision"], p["expected"]) for p in payloads(conn, "calc.golden_decision")]


def kinds_of_the_step(conn):
    """The calc events, without the `step_not_built` that a quit at the end adds."""
    return [kind for kind in h.kinds(conn, "calc.") if kind != "calc.step_not_built"]


def helper_calls(model):
    return h.phase_calls(model, "example_helper.md")


# ---- the call --------------------------------------------------------------------------------


def test_the_helper_never_sees_the_notes_the_brief_or_the_other_examples(build, conn, notes):
    notes.add_note(conn, step_id="s0", text="NOTE-MARKER about my 4242 savings", session_id="earlier")
    _, model, _ = run(build, ["why this?", "/quit"], respond("explain", message="It is made up."))
    [call] = helper_calls(model)
    text = call["system"] + call["messages"][0]["content"]
    for secret in ("NOTE-MARKER", "4242", GOAL, PARTICULAR, EX2["working"], "20000"):
        assert secret not in text, secret


# ---- correct ---------------------------------------------------------------------------------

def test_a_corrected_answer_is_shown_back_and_confirmation_is_asked(build, conn):
    _, _, person = run(build, [REPLY, "/quit"], CORRECT)
    assert after_helper(person)[:2] == [("say", ANSWER_SHOWN), ("ask", CONFIRM_ANSWER)]
    assert events(conn, "calc.helper_answer") == [("calc.helper_answer", "agent", {
        "module": "trip_cost", "index": 1, "arguments": {"action": "correct", "answer": ANSWER}})]
    assert decisions(conn) == []                                  # nothing is confirmed yet


@pytest.mark.parametrize("word", ["yes"])
def test_an_accept_word_confirms_the_transcribed_answer(build, conn, word):
    run(build, [REPLY, word, "/quit"], CORRECT)
    assert decisions(conn) == [(1, "corrected", ANSWER)]


# ---- explain, note, skip ---------------------------------------------------------------------

def test_an_explanation_is_said_stripped_and_the_example_is_asked_about_again(build, conn):
    _, _, person = run(build, ["what is this?", "yes", "/quit"],
                       respond("explain", message="  It is a made-up example, with 3 cases.  "))
    assert after_helper(person)[:2] == [("say", "It is a made-up example, with 3 cases."), ("ask", CONFIRM_EXAMPLE)]
    assert decisions(conn) == [(1, "accepted", PROPOSED)]
    assert payloads(conn, "calc.helper_answer")[0]["arguments"]["action"] == "explain"


def test_a_note_is_kept_with_this_reply_and_the_person_is_thanked(build, conn, notes):
    reply = "I pay 450 a month for the van"
    _, _, person = run(build, [f"  {reply}  ", "/quit"], respond("note"))
    assert notes.list_notes(conn) == [{"step": "s1", "text": reply}]
    assert after_helper(person)[:2] == [("say", NOTE_KEPT), ("ask", CONFIRM_EXAMPLE)]
    assert decisions(conn) == []


def test_a_skip_leaves_the_example_out_and_goes_on_to_the_next(build, conn):
    _, _, person = run(build, ["I cannot check this one", "/quit"], respond("skip"))
    assert decisions(conn) == [(1, "skipped", None)]
    assert any(t.startswith("Example 2 of 3") for t in person.told)
    assert kinds_of_the_step(conn)[-3:] == ["calc.example_reply", "calc.helper_answer", "calc.golden_decision"]


# ---- what the helper sends is checked --------------------------------------------------------

def problems_of(conn):
    return [(p["problem"], p["arguments"]) for p in payloads(conn, "calc.helper_rejected")]


def reject(build, conn, call, answer=REPLY):
    """One helper reply that must be refused. Returns the (problem, arguments) recorded."""
    _, model, person = run(build, [answer, "/quit"], call)
    assert after_helper(person)[:2] == [("say", NOT_UNDERSTOOD), ("ask", CONFIRM_EXAMPLE)]
    assert model.roles().count("example_helper") == 1             # no second attempt
    assert events(conn, "calc.helper_answer") == [] and decisions(conn) == []
    [(_, actor, payload)] = events(conn, "calc.helper_rejected")
    assert actor == "harness" and (payload["module"], payload["index"]) == ("trip_cost", 1)
    return problems_of(conn)[0]


def test_a_number_the_person_did_not_give_is_refused(build, conn):
    problem, _ = reject(build, conn, respond("correct", answer=ANSWER), answer="add 500 to expected")
    assert problem == "unbacked numbers: 17500"


# ---- the sources of the number check -----------------------------------------------------------

def accepted(build, conn, answers, call):
    run(build, [*answers, "/quit"], call)
    assert payloads(conn, "calc.helper_rejected") == []
    return payloads(conn, "calc.helper_answer")


def test_a_number_that_is_only_in_the_brief_is_refused(build, conn):
    run(build, ["the expected one is lower", "/quit"],
        respond("correct", answer={"low": "13000", "expected": "1150", "high": "23000"}))
    assert problems_of(conn)[0][0] == "unbacked numbers: 1150"
