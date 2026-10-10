"""SPEC 9.7 and 5.9: the number check of the agent also reads the data summaries of the conversation, and the person's
choice at a finding."""
import json

import pytest

import step5_helpers as s5
from step5_helpers import RENT_MESSAGE, SESSION, ask_finding, brief_entry, entry, h, report, summary_call

OK = "Done."
QUESTION = "How long will it take?"                          # no figure: the verifier does not run
SUMMARY = {"measure": "money_out", "account": "all", "months": 3}


def run_with(income, spending="1150"):
    return h.run_module(inputs={"income": income, "spending": spending}, assumptions=[], expected="about nothing")


def outcome(model, call_index=1):
    return h.tool_message(model, call_index)


# ---- the summaries of this conversation ----------------------------------------------------------------------------------------------

def test_a_figure_of_a_summary_of_this_conversation_is_backed(talk, summaries, conn, example_loaded):
    summaries.run_summary(conn, SUMMARY, session_id=SESSION)
    model, _ = talk([run_with("4132.31"), h.say_text(OK)], ["/quit"], question=QUESTION)
    assert json.loads(outcome(model)["content"])["output"] == "2982.31" and len(h.rows(conn, "calc_runs")) == 1




def test_a_summary_of_another_conversation_backs_nothing(talk, summaries, conn, example_loaded):
    summaries.run_summary(conn, SUMMARY, session_id="another")
    model, _ = talk([run_with("4132.31"), h.say_text(OK)], ["/quit"], question=QUESTION)
    assert outcome(model)["content"].startswith("These numbers did not come from the person")








# ---- the choice at a finding ------------------------------------------------------------------------------------------------------------









