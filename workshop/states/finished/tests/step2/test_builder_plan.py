"""SPEC 5.7, the plan check: the person reads the spec in plain words before any example."""
import json

import pytest

import step2_helpers as h
from step2_helpers import (ACCEPT_WORDS, PLAN_FEEDBACK, PLAN_KEPT, PLAN_QUESTION, REASON_SKIPPED, REASON_STOPPED,
                           REVISED_PY, REVISED_TESTS, WRITING_SPEC, built, events, kinds, months_script, only_step,
                           payloads, propose_examples, propose_spec, reuse_module, revised_examples, revised_spec,
                           rows, say_text, saved_spec, surplus_script, surplus_spec, tools, write_module)

FEEDBACK = "I have a list of costs, not one total."
BAD = propose_spec(name="Bad Name")
REVISED = [propose_spec(revised_spec()), propose_examples(revised_examples()), write_module(REVISED_PY, REVISED_TESTS)]
BUILT = {"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""}


def plan_events(conn):
    return [(p["round"], p["decision"], p["text"]) for p in payloads(conn, "calc.plan_decision")]


# ---- the person's answer -----------------------------------------------------------------------

@pytest.mark.parametrize("word", ["yes"])
def test_an_accept_word_accepts_the_plan_whatever_its_case(build, conn, word):
    results, model, _ = build(surplus_script(), [word, "/accept", "/accept", "/accept"], brief=only_step("s1"))
    assert results == [BUILT] and len(model.calls) == 3
    assert plan_events(conn) == [(1, "accepted", word.strip())]
    assert events(conn, "calc.plan_decision")[0][1] == "person"


def test_quit_at_the_plan_ends_the_whole_build(build):
    results, model, person = build(surplus_script() + months_script(), ["/quit"])
    assert [r["step"] for r in results] == ["s1"] and len(model.calls) == 1
    assert not any(t.startswith("Step s3") for t in person.told)


def test_skip_leaves_the_step_for_later_and_the_next_step_goes_ahead(build, conn):
    results, model, _ = build([propose_spec(), *months_script()], ["/skip", *built()])
    assert results[0] == {"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_SKIPPED}
    assert results[1]["outcome"] == "built" and len(model.calls) == 4
    assert plan_events(conn) == [(1, "skipped", "/skip"), (1, "accepted", "yes")]
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_SKIPPED}]
    assert rows(conn, "notes") == []


@pytest.mark.parametrize("answer", ["yes please"])
def test_anything_else_is_feedback(build, conn, answer):
    results, model, _ = build([propose_spec(), propose_spec(revised_spec()), *REVISED[1:]],
                              [answer, "yes", "/accept", "/accept", "/accept"], brief=only_step("s1"))
    assert plan_events(conn)[0] == (1, "feedback", answer)
    assert results == [BUILT] and len(model.calls) == 4


# ---- feedback goes back to the spec writer ---------------------------------------------------

def feedback_build(build, feedback=FEEDBACK, first=None):
    return build([first or propose_spec(), *REVISED], [feedback, "yes", "/accept", "/accept", "/accept"],
                 brief=only_step("s1"))


def test_feedback_is_saved_as_a_note_and_the_revised_spec_is_built(build, conn, notes, modules_dir):
    results, _, _ = feedback_build(build, f"  {FEEDBACK}  ")
    assert results == [BUILT]
    assert notes.list_notes(conn) == [{"step": "s1", "text": FEEDBACK}]
    [note] = rows(conn, "notes")
    assert (note["step_id"], note["session_id"], note["text"]) == ("s1", h.SESSION, FEEDBACK)
    written = json.loads((modules_dir / "monthly_surplus" / "spec.json").read_text(encoding="utf-8"))
    assert written == saved_spec(revised_spec(), "s1")


# ---- the round limit and a revision that does not pass ---------------------------------------

def three_rounds(build):
    """Three plans, and feedback on each. The third feedback cannot go back to the writer."""
    third = propose_spec(revised_spec(description="Third version."))
    script = [propose_spec(), propose_spec(revised_spec()), third, propose_examples(revised_examples()),
              write_module(REVISED_PY, REVISED_TESTS)]
    return build(script, ["one", "two", "three", "/accept", "/accept", "/accept"], brief=only_step("s1"))


def test_the_plan_is_shown_at_most_three_times_and_feedback_goes_back_twice(build, conn):
    results, model, person = three_rounds(build)
    assert results == [BUILT]
    assert person.asked.count(PLAN_QUESTION) == 3
    assert model.roles() == ["spec_writer"] * 3 + ["example_writer", "module_writer"]
    assert plan_events(conn) == [(1, "feedback", "one"), (2, "feedback", "two"), (3, "feedback", "three")]


def test_feedback_beyond_the_limit_is_kept_and_said_and_goes_on_with_the_last_plan(build, conn):
    _, model, person = three_rounds(build)
    assert person.told.count(PLAN_KEPT) == 1
    assert payloads(conn, "calc.plan_kept") == [{"step": "s1", "reason": "rounds"}]
    assert events(conn, "calc.plan_kept")[0][1] == "harness"
    assert [row["text"] for row in rows(conn, "notes")] == ["one", "two", "three"]
    [call] = h.phase_calls(model, "example_writer.md")
    assert h.sections(("spec", saved_spec(revised_spec(description="Third version."), "s1"))) in \
        call["messages"][0]["content"]


# ---- reuse and rebuild -------------------------------------------------------------------------


