"""SPEC 8.5 and 8.6: side conversations inside `run_agent`: at every kind of question, the order of model calls, what
crosses back, and what is recorded."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (ASIDE_CARRIED, ASIDE_CARRY, ASIDE_CLOSE, ASIDE_OPEN, DECISION_QUESTION,
                           DECISION_QUESTION_SUGGESTED, GATE_QUESTION, h, marked, side)

OK = "Done."
A_THING = "A thing."
TO_ASIDE = ["/aside what does this mean?", "/back", "no"]            # opens one, goes back, carries nothing
GATE = s4.gate_block(s4.surplus_item())
SURPLUS_PLAN = ("To work this out: surplus = income - spending\nI will need from you:\n"
                "  - income (a number): Money in each month.\n  - spending (a number): Money out each month.\n"
                "It gives back: The surplus per month.")
EXAMPLES = [
    "Example 1 of 3\n  income: 5123.45\n  spending: 3100.10\n  Working: 5123.45 less 3100.10 leaves 2023.35\n"
    "  Proposed answer: 2023.35",
    "Example 2 of 3\n  income: 4000\n  spending: 4500\n  Working: 4000 less 4500 is a shortfall of 500\n"
    "  Proposed answer: -500",
    "Example 3 of 3\n  income: 3000\n  spending: 3000\n  Working: 3000 less 3000 leaves 0\n  Proposed answer: 0"]
STEP_HEADER = "Step s1: Work out the monthly surplus"


def events_of(conn, kind):
    return [payload for _, _, payload in h.events(conn, kind)]


def asks(person):
    return s4.asked_of(person)


def opened(conn):
    return events_of(conn, "aside.opened")


def agent_text(model):
    """Every message the agent's model was given, in one string (its system prompt tells about /aside)."""
    return json.dumps([c["messages"] for c in model.of("analyst")], default=str)


def sandwiched(person, question):
    """The asks of a question that was put twice, around one side conversation of one turn."""
    texts = asks(person)
    first = texts.index(question)
    return texts[first:first + 4]


def test_an_aside_at_a_gate_then_yes_is_three_calls_and_the_carried_text_comes_last(ask_agent, conn):
    script = [s4.run(), side("Steady means it does not change."), h.say_text(OK)]
    answers = ["/aside What does steady mean?", "/back", "Rent is 1,100 now.", "yes", "/quit"]
    model, person = ask_agent(script, answers)
    assert model.roles() == ["analyst", "aside", "analyst"]
    messages = model.calls[2]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "user"]
    assert messages[2]["content"].startswith("{") and json.loads(messages[2]["content"])["output"] == "2000"
    assert messages[3] == {"role": "user", "content": ASIDE_CARRIED.format(text="Rent is 1,100 now.")}
    assert [p["text"] for p in events_of(conn, "ask.message")] == [h.QUESTION]


def test_at_an_ordinary_reply_the_reply_is_asked_again_and_nothing_is_looked_at(talk, conn):
    model, person = talk([h.say_text("Here is what I found."), side(A_THING)], [*TO_ASIDE, "/quit"], question=h.QUESTION)
    assert asks(person) == ["Here is what I found.", marked(A_THING), marked(ASIDE_CARRY), "Here is what I found."]
    assert opened(conn)[0]["looking_at"] is None and len(model.of("analyst")) == 1
    assert [p["text"] for p in events_of(conn, "ask.message")] == [h.QUESTION]


def test_the_aside_is_not_a_message_and_the_agent_never_hears_of_it(talk, conn):
    model, _ = talk([h.say_text("Here."), side(A_THING), h.say_text("Again.")], ["/aside what is that?", "/back", "no", "More", "/quit"])
    assert [p["text"] for p in events_of(conn, "ask.message")] == [h.QUESTION, "More"]
    assert "/aside" not in agent_text(model) and "what is that" not in agent_text(model) and A_THING not in agent_text(model)


def test_at_a_gate_the_gate_block_is_what_the_person_was_looking_at(ask_agent, conn):
    _, person = ask_agent([s4.run(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "yes", "/quit"])
    assert opened(conn)[0]["looking_at"] == GATE
    assert sandwiched(person, GATE_QUESTION) == [GATE_QUESTION, marked(A_THING), marked(ASIDE_CARRY), GATE_QUESTION]


def test_at_a_decision_the_decision_block_is_what_the_person_was_looking_at(ask_agent, conn):
    block = s4.decision_block("Should the date stay or move?", ["Keep the date", "Move the date"])
    _, person = ask_agent([s4.ask_decision(), side(A_THING), h.say_text(OK)], [*TO_ASIDE, "2", "/quit"])
    assert opened(conn)[0]["looking_at"] == block
    assert sandwiched(person, DECISION_QUESTION) == [DECISION_QUESTION, marked(A_THING), marked(ASIDE_CARRY), DECISION_QUESTION]
    assert person.log.count(("say", block)) == 2


def build_script():
    return [h.request_module("step", "s1"), h.propose_spec(), h.propose_examples(), h.write_module(), h.say_text("Built.")]


def test_at_the_plan_check_of_a_build_the_header_and_the_plan_are_what_was_looked_at(talk, months_only, conn):
    script = [h.request_module("step", "s1"), h.propose_spec(), side(A_THING), h.propose_examples(), h.write_module(),
              h.say_text("Built.")]
    answers = ["yes", *TO_ASIDE, "yes", *h.accepts(3), "/quit"]
    model, person = talk(script, answers)
    assert model.roles() == ["analyst", "spec_writer", "aside", "example_writer", "module_writer", "analyst"]
    assert opened(conn)[0]["looking_at"] == STEP_HEADER + "\n" + SURPLUS_PLAN
    assert sandwiched(person, h.PLAN_QUESTION) == [h.PLAN_QUESTION, marked(A_THING), marked(ASIDE_CARRY), h.PLAN_QUESTION]


def test_quit_in_an_aside_at_a_gate_is_a_no_with_the_words_quit(ask_agent, conn):
    model, person = ask_agent([s4.run(), side(A_THING), h.say_text(OK)], ["/aside what?", "/quit", "/quit"])
    assert json.loads(h.tool_message(model, 2)["content"]) == {"outcome": "not_run", "said": "/quit"}
    [row] = s4.decision_rows(conn)
    assert (row["kind"], row["choice"], row["words"]) == ("assumptions", "no", "/quit")
    assert h.rows(conn, "calc_runs") == [] and asks(person)[-1] == OK
