"""SPEC 9.7: the verifier inside `run_agent`: when it runs, the order of model calls, the notes, and `verify` off."""
import json

import pytest

import step5_helpers as s5
from step5_helpers import (DATA_BLOCK, FINDING_NOTE, MESSAGE, PROGRESS, SESSION, THINKING, VERIFY_PROGRESS, ask_finding,
                           entry, h, report, s4, summary_call)

OK = "Nothing is left over each month."
RUN = h.run_module(inputs={"income": "4132.31", "spending": "4132.31"}, assumptions=[], expected="about nothing")
EXAMPLE_SCRIPT = [summary_call(), report(entry()), ask_finding(1), RUN, h.say_text(OK)]


def analyst_calls(model):
    return [i for i, call in enumerate(model.calls) if s5.role_of(call["system"]) == "analyst"]


def users(model, index):
    return [m["content"] for m in model.calls[index]["messages"] if m["role"] == "user"]


# ---- the example of 9.7 ----------------------------------------------------------------------------------------------

def test_five_model_calls_in_the_order_of_the_spec(talk, example_loaded):
    model, person = talk(EXAMPLE_SCRIPT, ["2", "/quit"])
    assert model.roles() == ["verifier", "verifier", "analyst", "analyst", "analyst"]


def test_the_events_of_the_example_in_the_order_of_the_spec(talk, conn, example_loaded):
    talk(EXAMPLE_SCRIPT, ["2", "/quit"])
    kinds = s5.kinds_after_start(conn)
    assert kinds[:7] == ["ask.message", "data.summary", "verify.report", "finding.opened", "ask.decision_asked",
                         "ask.decision", "finding.closed"]
    assert kinds[-1] == "ask.reply" and len(kinds) > 8
    assert not [k for k in kinds if k.startswith(("ask.correction", "verify.dropped", "finding.refused"))]


def test_what_the_person_sees_and_when_the_model_is_called(talk, example_loaded):
    _, person = talk(EXAMPLE_SCRIPT, ["2", "/quit"])
    log = [entry for entry in person.log if entry[0] in ("say", "ask", "call")]
    assert log[:12] == [PROGRESS, ("call", "verifier"), PROGRESS, ("call", "verifier"), THINKING, ("call", "analyst"),
                        ("say", DATA_BLOCK), ("ask", s4.DECISION_QUESTION), THINKING, ("call", "analyst"),
                        ("say", "  (running monthly_surplus)"), THINKING]
    assert log[12:] == [("call", "analyst"), ("ask", OK)]


def test_the_agent_is_called_with_the_message_and_then_a_note_for_the_finding(talk, example_loaded):
    model, _ = talk(EXAMPLE_SCRIPT, ["2", "/quit"])
    first = analyst_calls(model)[0]
    assert users(model, first) == [MESSAGE, FINDING_NOTE.format(id=1, block=DATA_BLOCK)]


def test_the_verifier_is_given_the_message_and_the_agent_the_message_too(talk, example_loaded):
    model, _ = talk(EXAMPLE_SCRIPT, ["2", "/quit"])
    assert model.calls[0]["messages"] == [{"role": "user", "content": MESSAGE}]
    assert model.calls[0]["system"] != model.calls[2]["system"]


def test_the_chosen_figure_is_backed_and_the_run_happens(talk, conn, example_loaded):
    talk(EXAMPLE_SCRIPT, ["2", "/quit"])
    [run] = h.rows(conn, "calc_runs")
    assert json.loads(run["inputs"]) == {"income": "4132.31", "spending": "4132.31"}
    assert s5.payloads(conn, "ask.reply") == [{"text": OK}]


def test_the_result_of_the_decision_is_what_the_agent_gets_next(talk, example_loaded):
    model, _ = talk(EXAMPLE_SCRIPT, ["2", "/quit"])
    result = json.loads(h.tool_message(model, 3)["content"])
    assert result["outcome"] == "decided" and result["choice"] == "2" and result["use"] == "4132.31"


# ---- when the verifier runs ---------------------------------------------------------------------------------------------

def test_a_message_without_a_figure_is_not_checked(talk, conn):
    model, person = talk([h.say_text(OK)], ["/quit"], question="How long until I reach my target?")
    assert model.roles() == ["analyst"] and VERIFY_PROGRESS not in person.told
    assert s5.events(conn, "verify.report") == [] and s5.events(conn, "verify.failed") == []


def test_a_message_with_a_figure_but_nothing_to_check_against_is_not_checked(talk, conn):
    brief = h.make_brief(particulars=[])
    model, _ = talk([h.say_text(OK)], ["/quit"], brief=brief)
    assert model.roles() == ["analyst"]


def test_every_person_message_is_checked_the_second_too(talk, conn, example_loaded):
    script = [summary_call(), report(), h.say_text("Tell me more."), report(), h.say_text(OK)]
    model, person = talk(script, ["I earn about 6k a month", "/quit"])
    assert model.roles() == ["verifier", "verifier", "analyst", "verifier", "analyst"]
    assert [p["text"] for p in s5.payloads(conn, "ask.message")] == [MESSAGE, "I earn about 6k a month"]
    assert s5.payloads(conn, "verify.report") == [{"findings": []}, {"findings": []}]


def test_a_message_that_is_checked_but_has_no_finding_goes_straight_to_the_agent(talk, example_loaded):
    model, person = talk([report(), h.say_text(OK)], ["/quit"])
    assert model.roles() == ["verifier", "analyst"]
    first = analyst_calls(model)[0]
    assert users(model, first) == [MESSAGE]
    assert person.log[:4] == [PROGRESS, ("call", "verifier"), THINKING, ("call", "analyst")]


def test_the_answer_to_a_decision_with_a_figure_is_not_checked(talk, conn, example_loaded):
    script = [summary_call(), report(entry()), ask_finding(1), h.say_text(OK)]
    model, _ = talk(script, ["I will use 6,000 then", "/quit"])
    assert model.roles() == ["verifier", "verifier", "analyst", "analyst"]
    assert [p["text"] for p in s5.payloads(conn, "ask.message")] == [MESSAGE]


def test_the_answers_at_a_gate_and_a_request_are_not_checked(talk, conn, example_loaded):
    run = h.run_module(inputs={"income": "1150", "spending": "1150"}, assumptions=["Spending stays the same."],
                       expected="about nothing")
    script = [report(), run, h.say_text(OK)]
    model, _ = talk(script, ["no, my spending is 4,500", "/quit"], question="My rent is 1,400 a month")
    assert model.roles() == ["verifier", "analyst", "analyst"]


def test_a_person_message_after_a_stop_is_checked(talk, conn, example_loaded):
    script = [report(), h.say_text("Which month?"), report(), h.say_text(OK)]
    model, _ = talk(script, ["Still 5k a month", "/quit"])
    assert model.roles() == ["verifier", "analyst", "verifier", "analyst"]


# ---- a check that fails ------------------------------------------------------------------------------------------------

class VerifierFails(s5.Model):
    """The verifier's model call raises; the agent's calls are answered from the script."""

    def complete(self, *, system, messages, tools=()):
        if s5.role_of(system) == "verifier":
            raise RuntimeError("the model is down")
        return super().complete(system=system, messages=messages, tools=tools)


def test_a_failed_check_is_recorded_and_the_conversation_goes_on(agent, conn, brief, installed, example_loaded):
    person = h.Person("/quit")
    model = VerifierFails([h.say_text(OK)], person)
    agent.run_agent(model=model, conn=conn, ask=person.ask, say=person.say, question=MESSAGE, verify=True, brief=brief,
                    today=s5.DAY, session_id=SESSION)
    assert model.roles() == ["analyst"] and model.of("analyst")[0]["messages"][-1]["content"] == MESSAGE
    [failed] = s5.payloads(conn, "verify.failed")
    assert list(failed) == ["reason"] and "the model is down" in failed["reason"]
    assert any(text.startswith("  (the check of your figures did not finish: ") for text in person.told)
    assert s5.payloads(conn, "ask.reply") == [{"text": OK}]
    kinds = s5.kinds_after_start(conn)
    assert kinds[:2] == ["ask.message", "verify.failed"]


# ---- verify off ----------------------------------------------------------------------------------------------------------

def run_without(agent, conn, brief, script, answers=("/quit",), **options):
    person = h.Person(*answers)
    model = s5.Model(script, person)
    agent.run_agent(model=model, conn=conn, ask=person.ask, say=person.say, question=MESSAGE, brief=brief,
                    today=s5.DAY, session_id=SESSION, **options)
    return model, person


def test_verify_is_off_when_not_given(agent, conn, brief, installed, example_loaded):
    model, person = run_without(agent, conn, brief, [h.say_text(OK)])
    assert model.roles() == ["analyst"] and VERIFY_PROGRESS not in person.told
    assert users(model, 0) == [MESSAGE]
    assert s5.kinds_after_start(conn) == ["ask.message", "ask.reply"]


def test_verify_false_is_the_same(agent, conn, brief, installed, example_loaded):
    model, _ = run_without(agent, conn, brief, [h.say_text(OK)], verify=False)
    assert model.roles() == ["analyst"] and s5.kinds_after_start(conn) == ["ask.message", "ask.reply"]


def test_without_verify_a_saved_value_is_replaced_as_in_step_four(agent, conn, brief, installed):
    s5.put_input(conn, "monthly_income", "5000")
    script = [h.save_input("monthly_income", "5k"), h.say_text(OK)]
    model, _ = run_without(agent, conn, brief, script)
    assert s5.saved_input(conn, "monthly_income")["value"] == json.dumps("5k")
    assert s5.finding_rows(conn) == [] and "finding" not in " ".join(s5.kinds_after_start(conn))


def test_without_verify_runs_and_saves_are_never_refused(agent, conn, brief, installed, findings, example_loaded):
    findings.open_finding(conn, session_id=SESSION, kind="brief", claim="x 1,400", claim_figure="1,400",
                          reference="y 1,150", reference_figure="1,150", difference="d")
    script = [h.run_module(inputs={"income": "1150", "spending": "1150"}, assumptions=[], expected="about nothing"),
              h.say_text(OK)]
    model, _ = run_without(agent, conn, brief, script)
    assert len(h.rows(conn, "calc_runs")) == 1 and s5.events(conn, "finding.refused") == []
    assert users(model, 0) == [MESSAGE]
