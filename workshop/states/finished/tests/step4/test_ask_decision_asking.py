"""SPEC 8.3: what the person is shown for a judgment, how the answer is read, what is recorded and what the agent gets."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (DECISION_QUESTION, DECISION_QUESTION_SUGGESTED, ask_decision, decision_block, h)

OK = "Done."
OPTIONS = ["Keep the date", "Move the date", "Ask the landlord"]
BOTH = [DECISION_QUESTION, DECISION_QUESTION_SUGGESTED]
S2 = {"id": "s2", "name": "Decide how much to set aside"}


def decide(ask_agent, answer, *, options=OPTIONS, extra=("/quit",), **changes):
    """One decision answered with `answer`. Returns (result dict, model, person)."""
    model, person = ask_agent([ask_decision(options=options, **changes), h.say_text(OK)], [answer, *extra])
    return json.loads(h.tool_message(model, 1)["content"]), model, person


def log_without_progress(person):
    return s4.quiet(person)


def position(person, entry):
    return person.log.index(entry)


def test_the_block_is_said_and_then_the_question_is_asked(ask_agent):
    _, _, person = decide(ask_agent, "1")
    block = decision_block("Should the date stay or move?", OPTIONS)
    k = position(person, ("say", block))
    assert person.log[k + 1] == ("ask", DECISION_QUESTION)


def test_with_a_recommendation_the_question_offers_yes(ask_agent):
    _, _, person = decide(ask_agent, "1", recommendation=2, why="It leaves room.")
    block = decision_block("Should the date stay or move?", OPTIONS, 2, "It leaves room.")
    k = position(person, ("say", block))
    assert person.log[k + 1] == ("ask", DECISION_QUESTION_SUGGESTED)


@pytest.mark.parametrize("answer, choice", [("2", "2"), ("MOVE THE DATE", "2")])
def test_a_number_or_the_text_of_an_option_picks_it(ask_agent, conn, answer, choice):
    result, _, _ = decide(ask_agent, answer)
    assert result["choice"] == choice and result["option"] == OPTIONS[int(choice) - 1]
    assert s4.decision_rows(conn)[0]["choice"] == choice


@pytest.mark.parametrize("answer", ["I would wait a week"])
def test_anything_else_is_something_else_with_the_persons_words(ask_agent, conn, answer):
    result, _, _ = decide(ask_agent, answer)
    assert result["choice"] == "something else" and result["option"] is None and result["said"] == answer
    [row] = s4.decision_rows(conn)
    assert row["choice"] == "something else" and row["words"] == answer


@pytest.mark.parametrize("answer", ["yes"])
def test_an_accept_word_takes_the_suggestion(ask_agent, answer):
    result, _, _ = decide(ask_agent, answer, recommendation=3, why="Cheapest.")
    assert result["choice"] == "3" and result["option"] == "Ask the landlord" and result["said"] == answer


def judgment_brief(*, extra=()):
    brief = h.make_brief()
    brief["process"] = [*brief["process"],
                        {"id": "s4", "name": "Decide on a date", "kind": "judgment", "needs": ["s3"], "produces": "A date"},
                        {"id": "s5", "name": "Work out the cost", "kind": "calculation", "method": "arithmetic",
                         "formula": "cost = 1", "needs": ["s4"], "produces": "A cost"}]
    return brief


def steps_of(model, call_index):
    return json.loads(h.tool_message(model, call_index)["content"])["judgment_steps"]


def test_the_record_of_a_judgment(ask_agent, conn):
    script = [s4.run(assumptions=[]), ask_decision(step="s2", options=[" Keep  the date ", "Move\nthe date"], runs=[1],
                                                   recommendation=2, why="Safer."), h.say_text(OK)]
    ask_agent(script, ["1", "/quit"])
    [row] = s4.decision_rows(conn)
    block = decision_block("Should the date stay or move?", ["Keep the date", "Move the date"], 2, "Safer.", S2)
    assert (row["session_id"], row["kind"], row["step_id"], row["question"]) == (h.SESSION, "judgment", "s2", block)
    assert json.loads(row["options"]) == ["Keep the date", "Move the date"]
    assert (row["choice"], row["words"], json.loads(row["runs"])) == ("1", "1", [1])
