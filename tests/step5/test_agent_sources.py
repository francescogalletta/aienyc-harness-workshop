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


def test_without_a_summary_the_same_figure_is_unbacked(talk, conn, example_loaded):
    model, _ = talk([run_with("4132.31"), h.say_text(OK)], ["/quit"], question=QUESTION)
    assert outcome(model)["content"].startswith("These numbers did not come from the person")
    assert h.rows(conn, "calc_runs") == []


def test_a_summary_of_another_conversation_backs_nothing(talk, summaries, conn, example_loaded):
    summaries.run_summary(conn, SUMMARY, session_id="another")
    model, _ = talk([run_with("4132.31"), h.say_text(OK)], ["/quit"], question=QUESTION)
    assert outcome(model)["content"].startswith("These numbers did not come from the person")


def test_the_figures_of_the_summary_that_the_verifier_asked_for_back_the_agent(talk, conn, example_loaded):
    model, _ = talk([summary_call(), report(), run_with("4132.31"), h.say_text(OK)], ["/quit"])
    assert len(h.rows(conn, "calc_runs")) == 1


def test_a_reply_may_quote_a_figure_of_a_summary(talk, summaries, conn, example_loaded):
    summaries.run_summary(conn, SUMMARY, session_id=SESSION)
    model, person = talk([h.say_text("Your files show 4132.31 going out each month.")], ["/quit"], question=QUESTION)
    assert s5.events(conn, "ask.correction") == [] and len(s5.events(conn, "ask.reply")) == 1


def test_a_reply_with_a_figure_that_no_summary_has_is_corrected(talk, summaries, conn, example_loaded):
    summaries.run_summary(conn, SUMMARY, session_id=SESSION)
    talk([h.say_text("Your files show 4132.32 going out each month."), h.say_text(OK)], ["/quit"], question=QUESTION)
    assert [p["reason"] for p in s5.payloads(conn, "ask.correction")] == ["reply"]


# ---- the choice at a finding ------------------------------------------------------------------------------------------------------------

def test_the_figure_of_the_data_is_backed_after_choosing_it(talk, conn, example_loaded):
    model, _ = talk([summary_call(), report(entry()), ask_finding(1), run_with("4132.31"), h.say_text(OK)], ["2", "/quit"])
    assert len(h.rows(conn, "calc_runs")) == 1


def test_the_figure_the_person_kept_is_backed(talk, conn, example_loaded):
    model, _ = talk([summary_call(), report(entry()), ask_finding(1), run_with("5000"), h.say_text(OK)], ["1", "/quit"])
    assert len(h.rows(conn, "calc_runs")) == 1


def test_the_figure_of_the_brief_is_backed_after_choosing_it(talk, conn):
    model, _ = talk([report(brief_entry()), ask_finding(1), run_with("1150"), h.say_text(OK)], ["2", "/quit"],
                    question=RENT_MESSAGE)
    assert len(h.rows(conn, "calc_runs")) == 1


def test_the_figure_of_the_person_own_words_is_backed(talk, conn, example_loaded):
    script = [summary_call(), report(entry()), ask_finding(1), run_with("4800"), h.say_text(OK)]
    talk(script, ["neither, I think it is 4800", "/quit"])
    assert len(h.rows(conn, "calc_runs")) == 1


def test_a_figure_nobody_gave_is_still_unbacked_after_a_finding(talk, conn, example_loaded):
    script = [summary_call(), report(entry()), ask_finding(1), run_with("4800"), h.say_text(OK)]
    model, _ = talk(script, ["2", "/quit"])
    assert h.rows(conn, "calc_runs") == []
    assert h.tool_message(model, 4)["content"].startswith("These numbers did not come from the person")
