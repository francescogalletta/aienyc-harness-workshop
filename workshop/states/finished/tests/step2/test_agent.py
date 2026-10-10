"""SPEC 5.9: the agent answers questions, and cannot put a number in front of the person that nothing produced."""
import json
from datetime import date, datetime, timedelta

import pytest

import step2_helpers as h
from harness.model import ScriptedModel
from step2_helpers import (DAY, QUESTION, BAD_NAME, EMPTY_REPLY, EMPTY_VALUE, GATE_UNBACKED, INPUTS_UNBACKED, NO_EXPECTATION,
                           NOT_REGISTERED, NUMBERS_CORRECTION, OPENING, SAVED, SESSION, TOO_MANY, WITHHELD, WITHHELD_NOTE,
                           Person, events, payloads, rows, run_module, save_input, say_text, tool, tool_message, tools,
                           user_messages)

UNBACKED_REPLY = "You will have 9,999 left."
OTHER_UNBACKED = "Perhaps 8,888 instead."


# ---- the fixed strings and schemas -----------------------------------------------------------


# ---- the model is called with ----------------------------------------------------------------


# ---- the loop --------------------------------------------------------------------------------

def test_the_reply_is_shown_by_asking_the_person_about_it(ask_agent, conn):
    model, person = ask_agent([say_text("Hello there.")])
    assert person.asked == ["Hello there."]
    assert "Hello there." not in person.told
    assert events(conn, "ask.reply") == [("ask.reply", "agent", {"text": "Hello there."})]


# ---- the number check on replies -------------------------------------------------------------

def test_an_unbacked_reply_is_corrected_without_the_person_seeing_it(ask_agent, conn):
    model, person = ask_agent([say_text(UNBACKED_REPLY), say_text("It depends on your plan.")])
    assert [(m["role"], m["content"]) for m in model.calls[1]["messages"]] == [
        ("user", QUESTION), ("assistant", UNBACKED_REPLY), ("user", NUMBERS_CORRECTION.format(numbers="9,999"))]
    assert person.asked == ["It depends on your plan."]
    assert UNBACKED_REPLY not in person.asked + person.told
    assert events(conn, "ask.correction") == [("ask.correction", "harness", {
        "reason": "reply", "numbers": ["9,999"], "text": UNBACKED_REPLY})]
    assert events(conn, "ask.withheld") == []


def test_a_reply_that_is_unbacked_again_is_withheld(ask_agent, conn):
    model, person = ask_agent([say_text(UNBACKED_REPLY), say_text(OTHER_UNBACKED)])
    assert person.asked == [WITHHELD.format(numbers="8,888")]
    assert OTHER_UNBACKED not in person.asked + person.told
    assert events(conn, "ask.withheld") == [("ask.withheld", "harness", {"numbers": ["8,888"], "text": OTHER_UNBACKED})]
    assert events(conn, "ask.reply") == []
    assert len(events(conn, "ask.correction")) == 1 and len(model.calls) == 2


# ---- what counts as known --------------------------------------------------------------------

def test_numbers_from_the_persons_question_are_backed(ask_agent):
    _, person = ask_agent([say_text("You said 5,000 comes in and 3,000 goes out.")])
    assert person.asked == ["You said 5,000 comes in and 3,000 goes out."]


def test_a_result_of_this_session_backs_the_reply(ask_agent):
    script = [run_module(), say_text("monthly_surplus gives 2,000.")]
    _, person = ask_agent(script)
    assert person.asked == ["monthly_surplus gives 2,000."]


def test_a_result_of_another_session_does_not(ask_agent, gate, conn):
    gate.call(conn, "monthly_surplus", {"income": "5000", "spending": "3000"}, assumptions=[], expected="x",
              session_id="an-earlier-session")
    _, person = ask_agent([say_text("Your surplus is 2,000."), say_text("Your surplus is 2,000.")],
                          question="What is my surplus?")
    assert person.asked == [WITHHELD.format(numbers="2,000")]


# ---- run_module ------------------------------------------------------------------------------

def test_run_module_goes_through_the_gate(ask_agent, conn):
    model, person = ask_agent([run_module(), say_text("It gives 2,000.")])
    [run] = rows(conn, "calc_runs")
    assert run["session_id"] == SESSION and run["module"] == "monthly_surplus"
    assert json.loads(run["inputs"]) == {"income": "5000", "spending": "3000"}
    assert json.loads(run["assumptions"]) == []
    result = tool_message(model, 1)
    assert not result.get("is_error")
    assert json.loads(result["content"]) == {"module": "monthly_surplus", "run_id": run["id"], "output": "2000"}
    assert person.asked == ["It gives 2,000."]


def test_run_module_inputs_that_nothing_produced_are_refused_before_the_gate(ask_agent, conn):
    bad = {"income": "5000", "spending": "2999"}
    before = len(rows(conn, "test_runs"))
    model, _ = ask_agent([run_module(inputs=bad), say_text("Cannot do that.")])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == INPUTS_UNBACKED.format(numbers="2999")
    [(_, actor, payload)] = events(conn, "ask.correction")
    assert actor == "harness" and payload["reason"] == "run_module" and payload["numbers"] == ["2999"]
    assert json.loads(payload["text"]) == {"module": "monthly_surplus", "inputs": bad,
                                           "assumptions": [], "expected": "about the usual amount"}
    assert rows(conn, "calc_runs") == [] and len(rows(conn, "test_runs")) == before
    assert events(conn, "calc.run") == [] and events(conn, "calc.refused") == []


def test_a_refusal_of_the_gate_reaches_the_model_as_an_error(ask_agent, conn):
    model, person = ask_agent([run_module(module="ghost"), say_text("There is no such module.")])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == NOT_REGISTERED.format(name="ghost")
    assert events(conn, "calc.refused")[0][2]["module"] == "ghost"
    assert person.asked == ["There is no such module."]


# ---- save_input ------------------------------------------------------------------------------

def test_a_saved_input_is_stored_recorded_and_acknowledged(ask_agent, conn):
    script = [save_input("monthly_income", "5000", "said by the person"), say_text("Noted.")]
    model, _ = ask_agent(script)
    [row] = rows(conn, "inputs")
    assert (row["name"], json.loads(row["value"]), row["note"], row["session_id"]) == (
        "monthly_income", "5000", "said by the person", SESSION)
    assert datetime.fromisoformat(row["ts"]).utcoffset() == timedelta(0)
    assert events(conn, "ask.input_saved") == [("ask.input_saved", "agent", {
        "name": "monthly_income", "value": "5000", "note": "said by the person"})]
    result = tool_message(model, 1)
    assert result["content"] == SAVED and not result.get("is_error")


def test_a_saved_input_backs_numbers_in_the_next_session(ask_agent, agent, conn, brief):
    ask_agent([save_input("monthly_income", "5000", "n"), say_text("Noted.")])
    model, person = ScriptedModel([say_text("Your income is 5,000.")]), Person("/quit")
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id="next-session",
                    question="What do you know about me?", today=DAY)
    assert person.asked == ["Your income is 5,000."]


def test_a_value_nobody_gave_is_refused(ask_agent, conn):
    arguments = {"name": "monthly_income", "value": "9876", "note": "worked out"}
    model, _ = ask_agent([tool("save_input", arguments), say_text("Sorry.")])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == INPUTS_UNBACKED.format(numbers="9876")
    [(_, actor, payload)] = events(conn, "ask.correction")
    assert actor == "harness" and payload["reason"] == "save_input" and payload["numbers"] == ["9876"]
    assert json.loads(payload["text"]) == arguments
    assert rows(conn, "inputs") == [] and events(conn, "ask.input_saved") == []


# ---- other tool calls ------------------------------------------------------------------------


# ---- events ----------------------------------------------------------------------------------

