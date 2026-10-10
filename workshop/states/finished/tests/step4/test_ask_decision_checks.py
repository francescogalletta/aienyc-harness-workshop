"""SPEC 8.3: the checks of `ask_decision`, in order. A call that fails one shows the person nothing."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (DECISION_BAD_RECOMMENDATION, DECISION_NO_QUESTION, DECISION_NO_STEP, DECISION_NO_WHY,
                           DECISION_OPTIONS, DECISION_QUESTION, DECISION_QUESTION_SUGGESTED, DECISION_RUNS,
                           DECISION_UNKNOWN_RUNS, DROP, ONE_DECISION, TOO_MANY_DECISIONS, ask_decision, h)

OK = "Done."
BOTH = [DECISION_QUESTION, DECISION_QUESTION_SUGGESTED]


def decision_asks(person):
    return [text for text in s4.asked_of(person) if text in BOTH]


def shown_decisions(person):
    return [text for kind, text in person.log if kind == "say" and text.startswith("Only you can decide this")]


def refused(ask_agent, changes, answers=("/quit",), **options):
    """One refused call: returns (error text, model, person)."""
    model, person = ask_agent([ask_decision(**changes), h.say_text(OK)], list(answers), **options)
    result = h.tool_message(model, 1)
    assert result["is_error"] is True
    return result["content"], model, person


def assert_nothing_shown(conn, person):
    assert decision_asks(person) == [] and shown_decisions(person) == []
    assert h.events(conn, "ask.decision_asked") == [] and s4.decision_rows(conn) == []


# ---- every error, with its event ----------------------------------------------------------------------------------

BAD_QUESTIONS = [DROP, None, "", "   ", "\n\t", 5, ["Which?"]]
BAD_OPTIONS = [DROP, None, "Keep or move", ["Only one"], [], ["a", "b", "c", "d", "e"], ["a", 2], ["a", None], ["a", ""],
               ["a", "   "], ["a", "A"], ["Keep  the date", " keep the\ndate "], {"1": "a", "2": "b"}, [["a"], ["b"]]]
BAD_RECOMMENDATIONS = [0, 3, -1, True, False, "1", 1.5, [1], {"n": 1}]
BAD_RUNS = [DROP, None, "1", 1, [1, "2"], [True], [1.5], [None], {"1": 1}]


@pytest.mark.parametrize("question", BAD_QUESTIONS)
def test_a_question_that_is_not_text_or_is_empty(ask_agent, conn, question):
    error, _, person = refused(ask_agent, {"question": question})
    assert error == DECISION_NO_QUESTION
    assert_nothing_shown(conn, person)


@pytest.mark.parametrize("options", BAD_OPTIONS, ids=repr)
def test_options_that_are_not_two_to_four_different_texts(ask_agent, conn, options):
    error, _, person = refused(ask_agent, {"options": options})
    assert error == DECISION_OPTIONS
    assert_nothing_shown(conn, person)


@pytest.mark.parametrize("options", [["a", "b"], ["a", "b", "c"], ["a", "b", "c", "d"], ["Keep", "Move", "Wait"]])
def test_two_to_four_different_options_pass(ask_agent, options):
    model, person = ask_agent([ask_decision(options=options), h.say_text(OK)], ["1", "/quit"])
    assert decision_asks(person) != [] and json.loads(h.tool_message(model, 1)["content"])["outcome"] == "decided"


@pytest.mark.parametrize("step, shown", [("s9", "'s9'"), ("S2", "'S2'"), (" s2", "' s2'"), ("added_1", "'added_1'"),
                                         (5, "5"), (True, "true"), (["s2"], '["s2"]'), ({"id": "s2"}, '{"id": "s2"}'),
                                         (1.5, "1.5"), (False, "false")])
def test_a_step_that_is_not_one_of_the_process(ask_agent, conn, step, shown):
    error, _, person = refused(ask_agent, {"step": step})
    assert error == DECISION_NO_STEP.format(step=shown)
    assert_nothing_shown(conn, person)


@pytest.mark.parametrize("step", [DROP, None, "", "s1", "s2", "s3"])
def test_no_step_or_a_step_of_the_process_of_any_kind_passes(ask_agent, step):
    model, person = ask_agent([ask_decision(step=step), h.say_text(OK)], ["1", "/quit"])
    assert json.loads(h.tool_message(model, 1)["content"])["outcome"] == "decided"
    assert len(decision_asks(person)) == 1


def test_a_step_added_in_this_or_an_earlier_session_is_a_step_of_the_process(ask_agent, conn):
    h.add_new_step(conn, session_id="earlier")
    model, person = ask_agent([ask_decision(step="added_1"), h.say_text(OK)], ["1", "/quit"])
    assert json.loads(h.tool_message(model, 1)["content"])["outcome"] == "decided"
    assert shown_decisions(person)[0].split("\n")[0].startswith("Only you can decide this. It is step added_1 (not in the brief)")


def test_an_added_step_that_does_not_exist_yet_is_not_a_step(ask_agent, conn):
    error, _, _ = refused(ask_agent, {"step": "added_1"})
    assert error == DECISION_NO_STEP.format(step="'added_1'")


@pytest.mark.parametrize("recommendation", BAD_RECOMMENDATIONS, ids=repr)
def test_a_recommendation_that_is_not_the_number_of_an_option(ask_agent, conn, recommendation):
    error, _, person = refused(ask_agent, {"recommendation": recommendation, "why": "Because."})
    assert error == DECISION_BAD_RECOMMENDATION
    assert_nothing_shown(conn, person)


def test_a_recommendation_may_be_any_option_number_up_to_the_options_shown(ask_agent):
    for n in (1, 2, 3):
        model, person = ask_agent([ask_decision(options=["a", "b", "c"], recommendation=n, why="Because."), h.say_text(OK)],
                                  ["1", "/quit"])
        assert shown_decisions(person)[0].endswith(f"  The assistant suggests {n}: Because.")


@pytest.mark.parametrize("recommendation", [DROP, None])
def test_a_recommendation_that_is_missing_or_null_is_none_and_its_why_is_not_read(ask_agent, recommendation):
    model, person = ask_agent([ask_decision(recommendation=recommendation, why=5), h.say_text(OK)], ["1", "/quit"])
    assert json.loads(h.tool_message(model, 1)["content"])["outcome"] == "decided"
    assert "The assistant suggests" not in shown_decisions(person)[0]
    assert decision_asks(person) == [DECISION_QUESTION]


@pytest.mark.parametrize("why", [DROP, None, "", "   ", "\n", 5, ["Because."]])
def test_a_recommendation_needs_a_reason(ask_agent, conn, why):
    error, _, person = refused(ask_agent, {"recommendation": 1, "why": why})
    assert error == DECISION_NO_WHY
    assert_nothing_shown(conn, person)


@pytest.mark.parametrize("runs", BAD_RUNS, ids=repr)
def test_runs_that_are_not_a_list_of_whole_numbers(ask_agent, conn, runs):
    error, _, person = refused(ask_agent, {"runs": runs})
    assert error == DECISION_RUNS
    assert_nothing_shown(conn, person)


def test_runs_that_are_not_runs_of_this_session(ask_agent, conn):
    error, _, person = refused(ask_agent, {"runs": [1, 99, 99, 77]})
    assert error == DECISION_UNKNOWN_RUNS.format(runs="1, 99, 77")             # no run exists yet
    assert_nothing_shown(conn, person)


def test_only_the_ids_that_are_not_runs_are_named_each_once_in_the_order_sent(ask_agent, conn):
    script = [s4.run(assumptions=[]), ask_decision(runs=[77, 1, 99, 77, 1]), h.say_text(OK)]
    model, person = ask_agent(script, ["/quit"])
    result = h.tool_message(model, 2)
    assert result["is_error"] is True and result["content"] == DECISION_UNKNOWN_RUNS.format(runs="77, 99")
    assert_nothing_shown(conn, person)


def test_a_run_of_another_session_is_not_a_run_of_this_one(agent, conn, brief, installed):
    person = h.Person("/quit")
    model = s4.Model([s4.run(assumptions=[]), h.say_text(OK)], person)
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id="other-chat",
                    question=h.QUESTION, today=h.DAY)
    assert len(h.rows(conn, "calc_runs")) == 1
    person = h.Person("/quit")
    model = s4.Model([ask_decision(runs=[1]), h.say_text(OK)], person)
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id="this-chat",
                    question=h.QUESTION, today=h.DAY)
    assert h.tool_message(model, 1)["content"] == DECISION_UNKNOWN_RUNS.format(runs="1")
    assert s4.decision_rows(conn) == []


def test_runs_of_this_session_pass_in_any_order_with_repeats_and_are_sent_as_they_are(ask_agent, conn):
    script = [s4.run(assumptions=[]), s4.run(assumptions=[]), ask_decision(runs=[2, 1, 2]), h.say_text(OK)]
    model, _ = ask_agent(script, ["1", "/quit"])
    assert json.loads(h.tool_message(model, 3)["content"])["outcome"] == "decided"
    assert json.loads(s4.decision_rows(conn)[0]["runs"]) == [2, 1, 2]


def test_an_empty_list_of_runs_passes(ask_agent, conn):
    ask_agent([ask_decision(runs=[]), h.say_text(OK)], ["1", "/quit"])
    assert json.loads(s4.decision_rows(conn)[0]["runs"]) == []


# ---- the event of a refused call -------------------------------------------------------------------------------

def test_a_refused_call_records_ask_decision_refused_of_the_harness(ask_agent, conn):
    arguments = ask_decision(question="  ")["tool_calls"][0]["arguments"]
    error, _, _ = refused(ask_agent, {"question": "  "})
    [(kind, actor, payload)] = h.events(conn, "ask.decision_refused")
    assert (kind, actor) == ("ask.decision_refused", "harness")
    assert list(payload) == ["error", "arguments"] and payload == {"error": error, "arguments": arguments}
    assert h.events(conn, "ask.correction") == []


def test_the_arguments_of_the_event_are_those_sent_whatever_was_wrong(ask_agent, conn):
    changes = {"options": ["a", "b", "c", "d", "e"], "step": "s9", "recommendation": 9, "why": DROP, "runs": "x",
               "extra": "kept"}
    arguments = ask_decision(**changes)["tool_calls"][0]["arguments"]
    refused(ask_agent, changes)
    [(_, _, payload)] = h.events(conn, "ask.decision_refused")
    assert payload["arguments"] == arguments and "why" not in payload["arguments"]


def test_a_refused_call_is_between_the_agent_calls_that_it_belongs_to(ask_agent, conn):
    refused(ask_agent, {"question": ""})
    kinds = s4.conversation_kinds(conn)
    assert kinds.index("ask.decision_refused") > kinds.index("ask.message")
    assert kinds.index("ask.decision_refused") < kinds.index("ask.reply")
    assert "ask.decision_asked" not in kinds and "ask.decision" not in kinds


# ---- the order of the checks -------------------------------------------------------------------------------------

BREAKS = {                                   # each break one check, with the error it gives
    "question": ({"question": ""}, DECISION_NO_QUESTION),
    "options": ({"options": ["only"]}, DECISION_OPTIONS),
    "step": ({"step": "s9"}, DECISION_NO_STEP.format(step="'s9'")),
    "recommendation": ({"recommendation": 7, "why": "Because."}, DECISION_BAD_RECOMMENDATION),
    "why": ({"recommendation": 1, "why": ""}, DECISION_NO_WHY),
    "runs": ({"runs": "x"}, DECISION_RUNS),
    "unknown": ({"runs": [42]}, DECISION_UNKNOWN_RUNS.format(runs="42")),
}
ORDER = ["question", "options", "step", "recommendation", "why", "runs", "unknown"]


@pytest.mark.parametrize("first, second", [(a, b) for k, a in enumerate(ORDER) for b in ORDER[k + 1:]
                                           if not (a == "recommendation" and b == "why")
                                           and not (a == "runs" and b == "unknown")])
def test_when_two_checks_fail_the_earlier_one_speaks(ask_agent, first, second):
    changes = {**BREAKS[second][0], **BREAKS[first][0]}
    error, _, _ = refused(ask_agent, changes)
    assert error == BREAKS[first][1]


def test_a_bad_recommendation_speaks_before_a_missing_why(ask_agent):
    error, _, _ = refused(ask_agent, {"recommendation": 7, "why": ""})
    assert error == DECISION_BAD_RECOMMENDATION


def test_bad_runs_speak_before_unknown_runs(ask_agent):
    error, _, _ = refused(ask_agent, {"runs": [1, "x"]})
    assert error == DECISION_RUNS


# ---- one decision per reply -------------------------------------------------------------------------------------

def two_in_one_reply(first, second):
    return h.tools(("ask_decision", first), ("ask_decision", second))


def test_only_the_first_call_of_a_reply_is_handled(ask_agent, conn):
    first = s4.ask_decision_arguments(question="First question?")
    second = s4.ask_decision_arguments(question="Second question?")
    model, person = ask_agent([two_in_one_reply(first, second), h.say_text(OK)], ["1", "/quit"])
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert json.loads(messages[0]["content"])["outcome"] == "decided"
    assert messages[1]["is_error"] is True and messages[1]["content"] == ONE_DECISION
    assert len(shown_decisions(person)) == 1 and "First question?" in shown_decisions(person)[0]
    assert len(s4.decision_rows(conn)) == 1
    [(_, actor, payload)] = h.events(conn, "ask.decision_refused")
    assert actor == "harness" and payload == {"error": ONE_DECISION, "arguments": second}


def test_the_first_call_counts_whatever_came_of_it(ask_agent, conn):
    bad = s4.ask_decision_arguments(question="")
    good = s4.ask_decision_arguments(question="Second question?")
    model, person = ask_agent([two_in_one_reply(bad, good), h.say_text(OK)])
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert [m["content"] for m in messages] == [DECISION_NO_QUESTION, ONE_DECISION]
    assert all(m["is_error"] for m in messages)
    assert [p["error"] for _, _, p in h.events(conn, "ask.decision_refused")] == [DECISION_NO_QUESTION, ONE_DECISION]
    assert_nothing_shown(conn, person)


def test_one_decision_is_checked_before_anything_else_of_the_second_call(ask_agent):
    first = s4.ask_decision_arguments()
    second = s4.ask_decision_arguments(question="", options=[])
    model, _ = ask_agent([two_in_one_reply(first, second), h.say_text(OK)], ["1", "/quit"])
    assert h.tool_message(model, 1)["content"] == ONE_DECISION


def test_a_refused_first_call_that_failed_the_number_check_also_counts(ask_agent, conn):
    unbacked = s4.ask_decision_arguments(options=["Set aside 4,321", "Set aside less"])
    good = s4.ask_decision_arguments()
    model, person = ask_agent([two_in_one_reply(unbacked, good), h.say_text(OK)])
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert messages[0]["content"] == h.INPUTS_UNBACKED.format(numbers="4,321") and messages[1]["content"] == ONE_DECISION
    assert_nothing_shown(conn, person)


# ---- at most MAX_DECISIONS per person message --------------------------------------------------------------------

def three_replies():
    return [ask_decision(question="First?"), ask_decision(question="Second?"), ask_decision(question="Third?")]


def test_two_decisions_are_shown_and_the_third_is_refused(ask_agent, conn):
    model, person = ask_agent([*three_replies(), h.say_text(OK)], ["1", "2", "/quit"])
    assert len(shown_decisions(person)) == 2 and len(s4.decision_rows(conn)) == 2
    result = h.tool_message(model, 3)
    assert result["is_error"] is True and result["content"] == TOO_MANY_DECISIONS
    [(_, actor, payload)] = h.events(conn, "ask.decision_refused")
    assert actor == "harness" and payload["error"] == TOO_MANY_DECISIONS
    assert payload["arguments"] == s4.ask_decision_arguments(question="Third?")


def test_the_limit_is_two_per_person_message(ask_agent):
    assert s4.MAX_DECISIONS == 2


def test_the_limit_is_checked_before_the_other_checks(ask_agent):
    script = [*three_replies()[:2], ask_decision(question=""), h.say_text(OK)]
    model, _ = ask_agent(script, ["1", "1", "/quit"])
    assert h.tool_message(model, 3)["content"] == TOO_MANY_DECISIONS


def test_a_third_call_in_a_reply_with_a_second_one_gets_the_limit_and_not_one_decision(ask_agent):
    script = [ask_decision(question="First?"), ask_decision(question="Second?"),
              two_in_one_reply(s4.ask_decision_arguments(), s4.ask_decision_arguments()), h.say_text(OK)]
    model, _ = ask_agent(script, ["1", "1", "/quit"])
    messages = [m["content"] for m in model.calls[3]["messages"] if m["role"] == "tool"][-2:]
    assert messages == [TOO_MANY_DECISIONS, ONE_DECISION]


def test_a_refused_call_does_not_count_towards_the_limit(ask_agent, conn):
    script = [ask_decision(question=""), ask_decision(question="First?"), ask_decision(question="Second?"), h.say_text(OK)]
    model, person = ask_agent(script, ["1", "2", "/quit"])
    assert len(shown_decisions(person)) == 2 and len(s4.decision_rows(conn)) == 2
    assert h.tool_message(model, 3)["content"] != TOO_MANY_DECISIONS


def test_a_decision_counts_whatever_the_answer(ask_agent, conn):
    script = [*three_replies(), h.say_text(OK)]
    model, person = ask_agent(script, ["Neither, thank you", "/quit", "/quit"])
    assert [d["choice"] for d in s4.decision_rows(conn)] == ["something else", "something else"]
    assert h.tool_message(model, 3)["content"] == TOO_MANY_DECISIONS


def test_the_count_starts_again_at_each_person_message(ask_agent, conn):
    script = [*three_replies(), h.say_text("Here is where we are."), ask_decision(question="Fourth?"),
              ask_decision(question="Fifth?"), ask_decision(question="Sixth?"), h.say_text("And now?")]
    model, person = ask_agent(script, ["1", "1", "Go on", "1", "1", "/quit"])
    assert h.tool_message(model, 3)["content"] == TOO_MANY_DECISIONS
    assert len(s4.decision_rows(conn)) == 4
    assert h.tool_message(model, 7)["content"] == TOO_MANY_DECISIONS


def test_the_limit_is_not_the_limit_of_builds_or_the_other_way_round(talk, months_only, conn):
    script = [*three_replies()[:2], h.request_module("step", "s1"), h.say_text(OK)]
    model, person = talk(script, ["1", "1", "no", "/quit"])
    result = h.tool_message(model, 3)
    assert result["content"] != h.TOO_MANY_REQUESTS and h.rows(conn, "decisions")[-1]["kind"] == "build"


# ---- the number check -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("changes, numbers", [
    ({"question": "Should the 4,321 stay?"}, "4,321"),
    ({"options": ["Set aside 4,321", "Set aside less"]}, "4,321"),
    ({"options": ["Keep the date", "Move it to 4,321"]}, "4,321"),
    ({"recommendation": 1, "why": "It leaves 7.25% spare."}, "7.25%"),
    ({"options": ["Put 4,321 aside", "Put 8,765 aside"]}, "4,321, 8,765"),
])
def test_a_number_that_nothing_backs_gives_inputs_unbacked_and_a_correction(ask_agent, conn, changes, numbers):
    arguments = ask_decision(**changes)["tool_calls"][0]["arguments"]
    error, _, person = refused(ask_agent, changes)
    assert error == h.INPUTS_UNBACKED.format(numbers=numbers)
    [(kind, actor, payload)] = h.events(conn, "ask.correction")
    assert actor == "harness" and payload["reason"] == "ask_decision"
    assert payload["numbers"] == numbers.split(", ") and payload["text"] == json.dumps(arguments)
    assert h.events(conn, "ask.decision_refused") == []
    assert_nothing_shown(conn, person)


def test_numbers_the_person_gave_the_brief_and_run_results_back_the_block(ask_agent, conn):
    script = [s4.run(assumptions=[]),
              ask_decision(question="Put 3000 aside of the 2,000 left, with rent at 1,150?",
                           options=["Set aside 5000", "Set aside 2000"], runs=[1]),
              h.say_text(OK)]
    model, person = ask_agent(script, ["1", "/quit"])
    assert json.loads(h.tool_message(model, 2)["content"])["outcome"] == "decided"
    assert h.events(conn, "ask.correction") == []


def test_the_step_number_and_the_option_numbers_are_not_checked(ask_agent):
    model, _ = ask_agent([ask_decision(step="s2", options=["a", "b", "c", "d"], recommendation=4, why="Fine."),
                          h.say_text(OK)], ["1", "/quit"])
    assert json.loads(h.tool_message(model, 1)["content"])["outcome"] == "decided"


def test_a_number_given_in_the_words_of_an_earlier_decision_backs_a_later_block(ask_agent, conn):
    script = [ask_decision(question="First?"), ask_decision(question="Put 3,333 aside, or keep it?"), h.say_text(OK)]
    model, person = ask_agent(script, ["Put 3,333 aside", "1", "/quit"])
    assert json.loads(h.tool_message(model, 2)["content"])["outcome"] == "decided"
    assert h.events(conn, "ask.correction") == []


def test_numbers_of_the_gate_answer_back_a_later_block_too(ask_agent, conn):
    script = [s4.run(), ask_decision(question="Use 180 instead?"), h.say_text(OK)]
    model, _ = ask_agent(script, ["No, spending is really 180", "1", "/quit"])
    assert json.loads(h.tool_message(model, 2)["content"])["outcome"] == "decided"
    assert h.events(conn, "ask.correction") == []


def test_an_unbacked_number_counts_neither_towards_the_limit_nor_as_a_shown_decision(ask_agent, conn):
    bad = ask_decision(question="Put 4,321 aside?")
    script = [bad, ask_decision(question="First?"), ask_decision(question="Second?"), h.say_text(OK)]
    model, person = ask_agent(script, ["1", "1", "/quit"])
    assert len(s4.decision_rows(conn)) == 2 and h.tool_message(model, 3)["content"] != TOO_MANY_DECISIONS


def test_the_checks_run_whatever_the_gate_state_is(ask_agent, conn):
    """A decision does not need a yes first and does not give one."""
    script = [ask_decision(), s4.run(), h.say_text(OK)]
    model, person = ask_agent(script, ["1", "yes", "/quit"])
    assert [d["kind"] for d in s4.decision_rows(conn)] == ["judgment", "assumptions"]
