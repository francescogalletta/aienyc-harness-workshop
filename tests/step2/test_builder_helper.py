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

def test_a_free_text_reply_gets_one_helper_call_made_as_soon_as_it_is_typed(build):
    _, model, person = run(build, [REPLY, "/quit"], CORRECT)
    assert model.roles() == ["spec_writer", "example_writer", "example_helper"]
    marked = person.log.index(("call", "example_helper"))
    assert person.log[marked - 2:marked] == [("ask", CONFIRM_EXAMPLE), ("say", READING_REPLY)]


def test_the_helper_has_its_prompt_and_one_tool_with_the_respond_schema(build):
    _, model, _ = run(build, [REPLY, "/quit"], CORRECT)
    [call] = helper_calls(model)
    assert [t.name for t in call["tools"]] == ["respond"]
    assert h.without_descriptions(call["tools"][0].input_schema) == h.RESPOND_SCHEMA
    assert [m["role"] for m in call["messages"]] == ["user"]


def test_the_user_message_of_the_helper(build):
    _, model, _ = run(build, [f"  {REPLY}  ", "/quit"], CORRECT)
    [call] = helper_calls(model)
    assert call["messages"][0]["content"] == sections(
        ("spec", SPEC), ("example", {"inputs": EX1["inputs"], "expected": EX1["expected"], "working": EX1["working"]}),
        ("answer shown", None), ("replies", [REPLY]))


def test_the_answer_shown_is_the_transcribed_answer_that_was_waiting_and_all_replies_come_with_it(build):
    _, model, _ = run(build, [REPLY, "no, the high one is wrong", "/quit"], CORRECT, respond("explain", message="Which one?"))
    first, second = helper_calls(model)
    assert second["messages"][0]["content"] == sections(
        ("spec", SPEC), ("example", EX1), ("answer shown", ANSWER), ("replies", [REPLY, "no, the high one is wrong"]))
    assert "[answer shown]\nnull" in first["messages"][0]["content"]


def test_after_any_reply_no_answer_is_waiting_until_a_valid_correct_sets_a_new_one(build):
    calls = [CORRECT, respond("explain", message="Which one?"), respond("explain", message="And now?")]
    _, model, _ = run(build, [REPLY, "hmm", "what", "/quit"], *calls)
    third = helper_calls(model)[2]["messages"][0]["content"]
    assert "[answer shown]\nnull" in third


def test_the_replies_are_those_about_this_example_only(build):
    _, model, _ = run(build, ["why this?", "/accept", "and this?", "/quit"],
                      respond("explain", message="It is made up."), respond("explain", message="It is made up."))
    first, second = helper_calls(model)
    assert second["messages"][0]["content"] == sections(
        ("spec", SPEC), ("example", EX2), ("answer shown", None), ("replies", ["and this?"]))
    assert "why this?" not in second["messages"][0]["content"]


def test_the_helper_never_sees_the_notes_the_brief_or_the_other_examples(build, conn, notes):
    notes.add_note(conn, step_id="s0", text="NOTE-MARKER about my 4242 savings", session_id="earlier")
    _, model, _ = run(build, ["why this?", "/quit"], respond("explain", message="It is made up."))
    [call] = helper_calls(model)
    text = call["system"] + call["messages"][0]["content"]
    for secret in ("NOTE-MARKER", "4242", GOAL, PARTICULAR, EX2["working"], "20000"):
        assert secret not in text, secret


def test_the_index_counts_the_examples_as_shown(build, conn):
    run(build, ["/accept", "why this?", "/quit"], respond("explain", message="It is made up."))
    assert payloads(conn, "calc.example_reply") == [{"module": "trip_cost", "index": 2, "text": "why this?"}]
    assert payloads(conn, "calc.helper_answer")[0]["index"] == 2


def test_the_event_of_the_reply_is_recorded_before_the_call_with_the_stripped_text(build, conn):
    run(build, [f"  {REPLY}\n", "/quit"], CORRECT)
    assert events(conn, "calc.example_reply") == [("calc.example_reply", "person", {
        "module": "trip_cost", "index": 1, "text": REPLY})]
    assert kinds_of_the_step(conn)[-2:] == ["calc.example_reply", "calc.helper_answer"]


def test_a_helper_call_that_raises_is_not_caught(build):
    with pytest.raises(ScriptExhausted):
        run(build, [REPLY, "/quit"])                              # the script has no reply for the helper


def test_only_the_first_tool_call_is_read(build, conn):
    both = tools(("respond", {"action": "explain", "message": "First."}), ("respond", {"action": "skip"}))
    _, _, person = run(build, [REPLY, "/quit"], both)
    assert ("say", "First.") in person.log and decisions(conn) == []


# ---- correct ---------------------------------------------------------------------------------

def test_a_corrected_answer_is_shown_back_and_confirmation_is_asked(build, conn):
    _, _, person = run(build, [REPLY, "/quit"], CORRECT)
    assert after_helper(person)[:2] == [("say", ANSWER_SHOWN), ("ask", CONFIRM_ANSWER)]
    assert events(conn, "calc.helper_answer") == [("calc.helper_answer", "agent", {
        "module": "trip_cost", "index": 1, "arguments": {"action": "correct", "answer": ANSWER}})]
    assert decisions(conn) == []                                  # nothing is confirmed yet


@pytest.mark.parametrize("word", ["yes", "/accept", "OK", "Y"])
def test_an_accept_word_confirms_the_transcribed_answer(build, conn, word):
    run(build, [REPLY, word, "/quit"], CORRECT)
    assert decisions(conn) == [(1, "corrected", ANSWER)]


def test_a_confirmed_answer_is_the_one_sent_by_the_helper(build, conn):
    answer = {"expected": "17500", "high": "23000", "low": "13000"}           # the order is the helper's
    run(build, [REPLY, "yes", "/quit"], respond("correct", answer=answer))
    assert list(payloads(conn, "calc.golden_decision")[0]["expected"]) == ["expected", "high", "low"]


def test_the_confirmation_is_asked_again_when_empty(build):
    _, _, person = run(build, [REPLY, "", "  ", "/quit"], CORRECT)
    assert person.asked[-3:] == [CONFIRM_ANSWER] * 3


def test_skip_declines_the_transcribed_answer_and_leaves_the_example_out(build, conn):
    run(build, [REPLY, "/skip", "/quit"], CORRECT)
    assert decisions(conn) == [(1, "skipped", None)]


def test_quit_at_the_confirmation_stops_the_build(build, conn):
    results, _, _ = run(build, [REPLY, "/quit"], CORRECT)
    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_STOPPED}]
    assert decisions(conn) == []


def test_free_text_at_the_confirmation_goes_to_the_helper_again(build):
    _, model, person = run(build, [REPLY, "no, change the high one", "/quit"], CORRECT,
                           respond("explain", message="Which number should it be?"))
    assert model.roles().count("example_helper") == 2
    assert after_helper(person, 1)[:2] == [("say", "Which number should it be?"), ("ask", CONFIRM_EXAMPLE)]


def test_after_a_declined_answer_a_yes_confirms_the_proposed_answer_again(build, conn):
    run(build, [REPLY, "hmm no", "yes", "/quit"], CORRECT, respond("explain", message="Which number should it be?"))
    assert decisions(conn) == [(1, "accepted", PROPOSED)]


def test_while_an_answer_waits_a_value_typed_for_a_number_output_is_read_directly(build, conn):
    script = [propose_spec(), propose_examples(), respond("correct", answer="2000")]
    _, _, person = build(script, ["yes", "make it 2,000", "2100", "/quit"], brief=only_step("s1"))
    assert ("say", "  Your answer: 2000") in person.log and CONFIRM_ANSWER in person.asked
    assert decisions(conn) == [(1, "corrected", "2100")]


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


def test_the_events_of_a_note_come_in_order(build, conn):
    run(build, ["I pay 450 a month for the van", "/quit"], respond("note"))
    assert kinds_of_the_step(conn)[-3:] == ["calc.example_reply", "calc.helper_answer", "calc.note_saved"]
    [(_, actor, saved)] = events(conn, "calc.note_saved")
    assert actor == "person" and saved["step"] == "s1" and saved["text"] == "I pay 450 a month for the van"


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


def test_a_reply_without_a_tool_call(build, conn):
    assert reject(build, conn, say_text("I do not know.")) == ("no tool call", None)


def test_a_first_call_to_another_tool(build, conn):
    call = tools(("write_module", {"module_py": "", "tests_py": ""}), ("respond", {"action": "skip"}))
    assert reject(build, conn, call) == ("no tool call", None)


@pytest.mark.parametrize("arguments", [{"action": "dance"}, {}, {"answer": ANSWER}])
def test_an_unknown_action(build, conn, arguments):
    assert reject(build, conn, tool("respond", arguments)) == ("unknown action", arguments)


def test_a_corrected_answer_must_be_present(build, conn):
    assert reject(build, conn, respond("correct")) == ("no answer", {"action": "correct"})


def test_a_corrected_answer_must_fit_the_output_type(build, conn):
    try:
        from_json("abc", "object")
    except ValueError as error:
        reason = str(error)
    arguments = {"action": "correct", "answer": "abc"}
    assert reject(build, conn, tool("respond", arguments)) == (f"the answer does not fit: {reason}", arguments)


@pytest.mark.parametrize("answer", [
    {"low": "13000", "high": "23000"}, {**ANSWER, "middle": "17500"}, {"low": "13000", "expected": "17500"}])
def test_an_object_answer_must_have_exactly_the_keys_of_the_proposed_answer(build, conn, answer):
    problem, arguments = reject(build, conn, respond("correct", answer=answer))
    assert problem == "the answer must have exactly these keys: low, expected, high" and arguments["answer"] == answer


def test_the_keys_are_checked_before_the_numbers(build, conn):
    problem, _ = reject(build, conn, respond("correct", answer={"low": "99999"}))
    assert problem.startswith("the answer must have exactly these keys")


def test_a_number_the_person_did_not_give_is_refused(build, conn):
    problem, _ = reject(build, conn, respond("correct", answer=ANSWER), answer="add 500 to expected")
    assert problem == "unbacked numbers: 17500"


def test_the_unbacked_numbers_are_listed_in_order_joined_by_commas(build, conn):
    answer = {"low": "13000", "expected": "17500", "high": "21000"}
    problem, _ = reject(build, conn, respond("correct", answer=answer), answer="make it better")
    assert problem == "unbacked numbers: 17500, 21000"


@pytest.mark.parametrize("message", ["", "   \n", None, 5])
def test_an_explanation_must_not_be_empty(build, conn, message):
    arguments = {"action": "explain", "message": message}
    assert reject(build, conn, tool("respond", arguments)) == ("empty message", arguments)


def test_an_explanation_without_a_message(build, conn):
    assert reject(build, conn, respond("explain"))[0] == "empty message"


def test_an_explanation_with_a_number_nobody_gave_is_refused(build, conn):
    message = "That makes 9,999 in all."
    assert reject(build, conn, respond("explain", message=message))[0] == "unbacked numbers: 9,999"


def test_after_a_refusal_no_answer_is_waiting(build, conn):
    run(build, [REPLY, "hmm", "yes", "/quit"], CORRECT, say_text("Sorry."))
    assert decisions(conn) == [(1, "accepted", PROPOSED)]


# ---- the sources of the number check -----------------------------------------------------------

def accepted(build, conn, answers, call):
    run(build, [*answers, "/quit"], call)
    assert payloads(conn, "calc.helper_rejected") == []
    return payloads(conn, "calc.helper_answer")


def test_numbers_of_the_example_inputs_expected_answer_and_working_are_backed(build, conn):
    answer = {"low": "10000", "expected": "3000", "high": "7000"}
    assert accepted(build, conn, ["use the base for low"], respond("correct", answer=answer))


def test_a_number_of_the_person_is_backed_however_it_is_written(build, conn):
    assert accepted(build, conn, [REPLY], CORRECT)


def test_a_number_of_an_earlier_reply_is_backed(build, conn):
    answers = [REPLY, "no, the rest is wrong"]
    run(build, [*answers, "/quit"], CORRECT, respond("correct", answer={"low": "13000", "expected": "17500", "high": "23000"}))
    assert len(payloads(conn, "calc.helper_answer")) == 2 and payloads(conn, "calc.helper_rejected") == []


def test_a_number_of_a_reply_backs_an_explanation(build, conn):
    assert accepted(build, conn, ["why 17,500?"], respond("explain", message="You asked about 17,500."))


def test_a_small_whole_number_is_not_checked(build, conn):
    assert accepted(build, conn, ["what is this?"], respond("explain", message="It shows 3 cases."))


def test_a_number_that_is_only_in_the_spec_is_refused(build, conn):
    spec = ranged_spec(output={"type": "object", "description": "low, expected and high: the cost, from 4321 up."})
    run(build, ["the expected one is lower", "/quit"],
        respond("correct", answer={"low": "13000", "expected": "4321", "high": "23000"}), spec=spec)
    assert problems_of(conn)[0][0] == "unbacked numbers: 4321"


def test_a_number_that_is_only_in_a_note_is_refused(build, conn, notes):
    notes.add_note(conn, step_id="s0", text="My budget is 7777.", session_id="earlier")
    run(build, ["the expected one is lower", "/quit"],
        respond("correct", answer={"low": "13000", "expected": "7777", "high": "23000"}))
    assert problems_of(conn)[0][0] == "unbacked numbers: 7777"


def test_a_number_that_is_only_in_the_brief_is_refused(build, conn):
    run(build, ["the expected one is lower", "/quit"],
        respond("correct", answer={"low": "13000", "expected": "1150", "high": "23000"}))
    assert problems_of(conn)[0][0] == "unbacked numbers: 1150"
