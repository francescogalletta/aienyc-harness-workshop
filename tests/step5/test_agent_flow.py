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














# ---- when the verifier runs ---------------------------------------------------------------------------------------------















# ---- a check that fails ------------------------------------------------------------------------------------------------

class VerifierFails(s5.Model):
    """The verifier's model call raises; the agent's calls are answered from the script."""

    def complete(self, *, system, messages, tools=()):
        if s5.role_of(system) == "verifier":
            raise RuntimeError("the model is down")
        return super().complete(system=system, messages=messages, tools=tools)




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






