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

@pytest.mark.parametrize("word", sorted(ACCEPT_WORDS) + ["YES", "Okay", "  Yes.  "])
def test_an_accept_word_accepts_the_plan_whatever_its_case(build, conn, word):
    results, model, _ = build(surplus_script(), [word, "/accept", "/accept", "/accept"], brief=only_step("s1"))
    assert results == [BUILT] and len(model.calls) == 3
    assert plan_events(conn) == [(1, "accepted", word.strip())]
    assert events(conn, "calc.plan_decision")[0][1] == "person"


def test_an_empty_answer_asks_again_and_records_nothing(build, conn):
    _, _, person = build(surplus_script(), ["", "   ", "yes", "/accept", "/accept", "/accept"], brief=only_step("s1"))
    assert person.asked[:3] == [PLAN_QUESTION] * 3
    assert plan_events(conn) == [(1, "accepted", "yes")]


def test_quit_stops_the_build_at_the_plan_and_records_no_decision(build, conn):
    results, model, _ = build(surplus_script(), [" /quit "], brief=only_step("s1"))
    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_STOPPED}]
    assert len(model.calls) == 1
    assert events(conn, "calc.plan_decision") == [] and rows(conn, "notes") == []
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_STOPPED}]


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


@pytest.mark.parametrize("answer", ["no", "yes please", "I have a list of costs", "/accepted"])
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


def test_the_revised_plan_is_shown_and_asked_about_in_a_new_round(build, builder):
    _, _, person = feedback_build(build)
    first, second = (builder.plan_words(saved_spec(spec, "s1")) for spec in (surplus_spec(), revised_spec()))
    told = [entry for entry in person.log if entry[0] in ("say", "ask")]
    start = told.index(("say", first))
    assert told[start:start + 5] == [
        ("say", first), ("ask", PLAN_QUESTION), ("say", WRITING_SPEC.format(attempt=1)), ("say", second),
        ("ask", PLAN_QUESTION)]


def test_the_answer_goes_back_as_the_result_of_the_accepted_call_in_the_same_conversation(build):
    _, model, _ = feedback_build(build)
    first, second = model.calls[0], model.calls[1]
    assert second["system"] == first["system"] and second["tools"] == first["tools"]
    user, assistant, result = second["messages"]
    assert user == first["messages"][0]
    assert assistant["role"] == "assistant" and assistant["tool_calls"][0]["arguments"] == surplus_spec()
    assert result["role"] == "tool" and result["tool_call_id"] == assistant["tool_calls"][0]["id"]
    assert result["content"] == PLAN_FEEDBACK.format(text=FEEDBACK) and not result.get("is_error")


def test_the_feedback_in_the_tool_result_is_the_stripped_answer(build):
    _, model, _ = feedback_build(build, f"\n  {FEEDBACK}  \n")
    assert model.calls[1]["messages"][-1]["content"].split("\n")[1] == FEEDBACK


def test_other_calls_of_the_accepted_reply_get_the_one_call_error_and_its_text_is_kept(build):
    reply = tools(("propose_spec", surplus_spec()), ("propose_spec", revised_spec()), ("reuse_module", {}),
                  text="Here is the plan.")
    _, model, _ = feedback_build(build, first=reply)
    _, assistant, accepted, other_one, other_two = model.calls[1]["messages"]
    assert assistant["content"] == "Here is the plan." and len(assistant["tool_calls"]) == 3
    assert [m["tool_call_id"] for m in (accepted, other_one, other_two)] == [c["id"] for c in assistant["tool_calls"]]
    assert not accepted.get("is_error")
    assert [(m["content"], m["is_error"]) for m in (other_one, other_two)] == [(h.ONE_CALL, True)] * 2


def test_earlier_refused_attempts_stay_in_the_conversation(build):
    _, model, _ = build([BAD, propose_spec(), *REVISED], [FEEDBACK, "yes", "/accept", "/accept", "/accept"],
                        brief=only_step("s1"))
    roles = [m["role"] for m in model.calls[2]["messages"]]
    assert roles == ["user", "assistant", "tool", "assistant", "tool"]
    assert model.calls[2]["messages"][2]["is_error"] is True


def test_the_notes_section_of_the_first_message_is_not_rewritten_by_the_feedback(build):
    _, model, _ = feedback_build(build)
    assert model.calls[1]["messages"][0] == model.calls[0]["messages"][0]
    assert FEEDBACK not in model.calls[1]["messages"][0]["content"]


def test_a_revised_spec_has_three_attempts_of_its_own(build):
    script = [BAD, say_text("no tool"), propose_spec(), BAD, say_text("no tool"), *REVISED]
    results, _, person = build(script, [FEEDBACK, "yes", "/accept", "/accept", "/accept"], brief=only_step("s1"))
    assert results == [BUILT]
    attempts = [t for t in person.told if t.startswith("  (writing the plan")]
    assert attempts == [WRITING_SPEC.format(attempt=n) for n in (1, 2, 3, 1, 2, 3)]


def test_a_revised_spec_is_checked_like_any_other(build, conn):
    _, _, _ = build([propose_spec(), BAD, *REVISED], [FEEDBACK, "yes", "/accept", "/accept", "/accept"],
                    brief=only_step("s1"))
    assert [p["step"] for p in payloads(conn, "calc.spec_rejected")] == ["s1"]
    assert kinds(conn, "calc.")[:6] == ["calc.spec_proposed", "calc.plan_decision", "calc.note_saved",
                                       "calc.spec_rejected", "calc.spec_proposed", "calc.plan_decision"]


def test_the_events_of_a_round_of_feedback_come_in_order(build, conn):
    feedback_build(build)
    assert kinds(conn, "calc.")[:6] == ["calc.spec_proposed", "calc.plan_decision", "calc.note_saved",
                                       "calc.spec_proposed", "calc.plan_decision", "calc.examples_proposed"]
    assert plan_events(conn) == [(1, "feedback", FEEDBACK), (2, "accepted", "yes")]
    [(_, actor, note)] = events(conn, "calc.note_saved")
    assert actor == "person" and note == {"id": 1, "step": "s1", "text": FEEDBACK}
    assert [p["spec"] for p in payloads(conn, "calc.spec_proposed")] == [
        saved_spec(surplus_spec(), "s1"), saved_spec(revised_spec(), "s1")]


def test_the_examples_are_written_for_the_revised_spec(build):
    _, model, _ = feedback_build(build)
    [call] = h.phase_calls(model, "example_writer.md")
    assert h.sections(("spec", saved_spec(revised_spec(), "s1"))) in call["messages"][0]["content"]


def test_a_spec_that_is_reused_after_feedback_ends_the_step(build, conn, registry):
    h.install_surplus(conn, step_id="old_step")
    first = propose_spec(surplus_spec(name="savings_gap"))
    results, model, person = build([first, reuse_module("monthly_surplus", "It already does it.")],
                                   [FEEDBACK], brief=only_step("s1"))
    assert results == [{"step": "s1", "outcome": "reused", "module": "monthly_surplus", "reason": ""}]
    assert len(model.calls) == 2 and person.asked == [PLAN_QUESTION]
    assert registry.step_map(conn)["s1"] == "monthly_surplus"
    assert payloads(conn, "calc.module_reused") == [{"step": "s1", "module": "monthly_surplus",
                                                    "reason": "It already does it."}]
    assert [row["text"] for row in rows(conn, "notes")] == [FEEDBACK]


def test_skip_after_feedback_ends_the_step_and_the_note_stays(build, conn):
    results, model, _ = build([propose_spec(), propose_spec(revised_spec())], [FEEDBACK, "/skip"], brief=only_step("s1"))
    assert results[0]["reason"] == REASON_SKIPPED and len(model.calls) == 2
    assert plan_events(conn) == [(1, "feedback", FEEDBACK), (2, "skipped", "/skip")]
    assert [row["text"] for row in rows(conn, "notes")] == [FEEDBACK]


def test_quit_after_feedback_ends_the_build_and_the_note_stays(build, conn):
    results, _, _ = build([propose_spec(), propose_spec(revised_spec())], [FEEDBACK, "/quit"], brief=only_step("s1"))
    assert results[0]["reason"] == REASON_STOPPED
    assert plan_events(conn) == [(1, "feedback", FEEDBACK)]
    assert [row["text"] for row in rows(conn, "notes")] == [FEEDBACK]


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


def test_the_events_of_the_third_round_come_in_order(build, conn):
    three_rounds(build)
    assert kinds(conn, "calc.")[:12] == [
        "calc.spec_proposed", "calc.plan_decision", "calc.note_saved", "calc.spec_proposed", "calc.plan_decision",
        "calc.note_saved", "calc.spec_proposed", "calc.plan_decision", "calc.note_saved", "calc.plan_kept",
        "calc.examples_proposed", "calc.golden_decision"]


def test_plan_kept_is_said_before_the_examples_are_written(build):
    _, _, person = three_rounds(build)
    told = person.told
    assert told.index(PLAN_KEPT) < told.index(h.WRITING_EXAMPLES.format(attempt=1))


def test_three_refused_revisions_keep_the_plan_the_person_was_last_shown(build, conn):
    script = [propose_spec(), BAD, say_text("no tool"), BAD, propose_examples(), write_module()]
    results, model, person = build(script, [FEEDBACK, "/accept", "/accept", "/accept"], brief=only_step("s1"))
    assert results == [BUILT] and len(model.calls) == 6
    assert person.asked.count(PLAN_QUESTION) == 1 and person.told.count(PLAN_KEPT) == 1
    assert payloads(conn, "calc.plan_kept") == [{"step": "s1", "reason": "spec"}]
    assert kinds(conn, "calc.")[:7] == [
        "calc.spec_proposed", "calc.plan_decision", "calc.note_saved", "calc.spec_rejected", "calc.spec_rejected",
        "calc.plan_kept", "calc.examples_proposed"]
    [call] = h.phase_calls(model, "example_writer.md")
    assert h.sections(("spec", saved_spec(surplus_spec(), "s1"))) in call["messages"][0]["content"]


def test_refused_revisions_do_not_end_the_step_and_the_note_stays(build, conn):
    script = [propose_spec(), BAD, BAD, BAD, propose_examples(), write_module()]
    results, _, _ = build(script, [FEEDBACK, "/accept", "/accept", "/accept"], brief=only_step("s1"))
    assert results[0]["outcome"] == "built" and [row["text"] for row in rows(conn, "notes")] == [FEEDBACK]


def test_a_second_round_that_fails_keeps_the_plan_of_the_first_revision(build, conn):
    script = [propose_spec(), propose_spec(revised_spec()), BAD, BAD, BAD, propose_examples(revised_examples()),
              write_module(REVISED_PY, REVISED_TESTS)]
    results, model, _ = build(script, ["one", "two", "/accept", "/accept", "/accept"], brief=only_step("s1"))
    assert results == [BUILT]
    assert payloads(conn, "calc.plan_kept") == [{"step": "s1", "reason": "spec"}]
    [call] = h.phase_calls(model, "example_writer.md")
    assert h.sections(("spec", saved_spec(revised_spec(), "s1"))) in call["messages"][0]["content"]


# ---- reuse and rebuild -------------------------------------------------------------------------

def test_a_reuse_has_no_plan_check(build, conn):
    h.install_surplus(conn, step_id="old_step")
    _, _, person = build([reuse_module("monthly_surplus")], brief=only_step("s1"))
    assert person.asked == [] and events(conn, "calc.plan_decision") == []


def test_a_kept_step_has_no_plan_check(build, conn):
    h.install_surplus(conn, step_id="s1")
    _, model, person = build([], brief=only_step("s1"))
    assert model.calls == [] and person.asked == [] and events(conn, "calc.plan_decision") == []


def test_a_rebuild_goes_through_the_plan_check_with_feedback_and_no_reuse(build, conn, registry):
    h.install_surplus(conn, step_id="s1")
    script = [propose_spec(), propose_spec(revised_spec(name="another_name")), *REVISED[1:]]
    results, model, person = build(script, [FEEDBACK, "yes", "/accept", "/accept", "/accept"], rebuild="monthly_surplus")
    assert results == [BUILT]
    assert person.asked.count(PLAN_QUESTION) == 2
    assert [[t.name for t in call["tools"]] for call in model.calls[:2]] == [["propose_spec"]] * 2
    assert registry.get_module(conn, "monthly_surplus")["spec"] == saved_spec(revised_spec(), "s1")
    assert [row["text"] for row in rows(conn, "notes")] == [FEEDBACK]
