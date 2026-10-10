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


BAD_QUESTIONS = [""]
BAD_OPTIONS = [["Only one"]]
BAD_RECOMMENDATIONS = [3]
BAD_RUNS = ["1"]


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


@pytest.mark.parametrize("step, shown", [("s9", "'s9'")])
def test_a_step_that_is_not_one_of_the_process(ask_agent, conn, step, shown):
    error, _, person = refused(ask_agent, {"step": step})
    assert error == DECISION_NO_STEP.format(step=shown)
    assert_nothing_shown(conn, person)


@pytest.mark.parametrize("recommendation", BAD_RECOMMENDATIONS, ids=repr)
def test_a_recommendation_that_is_not_the_number_of_an_option(ask_agent, conn, recommendation):
    error, _, person = refused(ask_agent, {"recommendation": recommendation, "why": "Because."})
    assert error == DECISION_BAD_RECOMMENDATION
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


@pytest.mark.parametrize("changes, numbers", [({"question": "Should the 4,321 stay?"}, "4,321")])
def test_a_number_that_nothing_backs_gives_inputs_unbacked_and_a_correction(ask_agent, conn, changes, numbers):
    arguments = ask_decision(**changes)["tool_calls"][0]["arguments"]
    error, _, person = refused(ask_agent, changes)
    assert error == h.INPUTS_UNBACKED.format(numbers=numbers)
    [(kind, actor, payload)] = h.events(conn, "ask.correction")
    assert actor == "harness" and payload["reason"] == "ask_decision"
    assert payload["numbers"] == numbers.split(", ") and payload["text"] == json.dumps(arguments)
    assert h.events(conn, "ask.decision_refused") == []
    assert_nothing_shown(conn, person)
