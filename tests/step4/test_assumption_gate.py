"""SPEC 8.2: a run that takes something as given is shown to the person, who says yes or no, before it runs."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (ACCEPT_WORDS, ASSUME, EXPECT, GATE_QUESTION, SESSION, THINKING, decision_rows, h, quiet,
                           result_of, run, run_args)

BLOCK = s4.gate_block(s4.surplus_item())
REPLY = "monthly_surplus gives 2,000."
SCRIPT = [run(), h.say_text(REPLY)]


def declined_script():
    return [run(), h.say_text("Understood, nothing was run.")]


# ---- what the person sees, and in which order --------------------------------------------------------------------

def test_the_gate_block_is_exactly_this(ask_agent):
    _, person = ask_agent(SCRIPT, ["yes", "/quit"])
    assert BLOCK == (
        "Before working this out, the assistant would take some things as given that you have not confirmed:\n"
        "  1. The money left over each month after spending.\n"
        "     Taking as given:\n"
        "       - Spending stays the same each month.\n"
        "     Expecting: what comes in less what goes out")
    assert [t for k, t in person.log if k == "say" and t.startswith("Before working")] == [BLOCK]


def test_the_block_then_the_question_then_the_run_then_the_next_call(ask_agent):
    """SPEC 8.6, 1: a run and its reply still take two agent calls, and a gate and a decision call no model."""
    model, person = ask_agent(SCRIPT, ["yes", "/quit"])
    assert quiet(person) == [
        ("call", "analyst"), ("say", BLOCK), ("ask", GATE_QUESTION), ("say", "  (running monthly_surplus)"),
        ("call", "analyst"), ("ask", REPLY)]
    assert model.roles() == ["analyst", "analyst"]


def test_the_question_is_the_fixed_text(ask_agent):
    _, person = ask_agent(SCRIPT, ["yes", "/quit"])
    assert GATE_QUESTION in person.asked
    assert s4.GATE_QUESTION == (
        "Go ahead on these? Type yes to go ahead. If something is not right, say so in your own words: nothing runs, "
        "and the assistant hears what you said. Type /aside to talk it through on the side first.")


def test_a_yes_lets_the_run_go_ahead_as_any_other_call(ask_agent, conn):
    model, _ = ask_agent(SCRIPT, ["yes", "/quit"])
    [row] = h.rows(conn, "calc_runs")
    assert (row["session_id"], row["module"]) == (SESSION, "monthly_surplus")
    assert json.loads(row["assumptions"]) == ASSUME and row["expected"] == EXPECT
    assert result_of(model, 1) == {"module": "monthly_surplus", "run_id": row["id"], "output": "2000"}
    assert not h.tool_message(model, 1).get("is_error")
    assert [m["role"] for m in model.calls[1]["messages"]] == ["user", "assistant", "tool"]


@pytest.mark.parametrize("answer", sorted(ACCEPT_WORDS) + ["YES", "Yes", "  yes  ", "Y", "OK", "Yes.", "\tyes\n"])
def test_the_accept_words_say_yes_in_any_case(ask_agent, conn, answer):
    ask_agent(SCRIPT, [answer, "/quit"])
    assert len(h.rows(conn, "calc_runs")) == 1
    [decision] = decision_rows(conn)
    assert decision["choice"] == "yes" and decision["words"] == answer.strip()


@pytest.mark.parametrize("answer", ["no", "n", "No.", "yeah", "yes please", "yes, but with 180", "yes!", "not now",
                                    "go ahead", "/quit", "/skip", "yes yes", "sure"])
def test_anything_else_is_a_no_and_the_leniency_of_a_build_request_does_not_apply(ask_agent, conn, answer):
    model, person = ask_agent(declined_script(), [answer, "/quit"])
    assert h.rows(conn, "calc_runs") == [] and h.events(conn, "calc.run") == []
    [decision] = decision_rows(conn)
    assert decision["choice"] == "no" and decision["words"] == answer
    assert "  (running monthly_surplus)" not in person.told


def test_a_no_gives_the_call_the_result_not_run_with_what_the_person_said(ask_agent):
    model, _ = ask_agent(declined_script(), ["  Not with those  ", "/quit"])
    result = h.tool_message(model, 1)
    assert not result.get("is_error")
    assert result["content"] == json.dumps({"outcome": "not_run", "said": "Not with those"})
    assert list(json.loads(result["content"])) == ["outcome", "said"]


def test_after_a_no_the_conversation_goes_on_and_the_same_set_is_asked_about_again(ask_agent, conn):
    script = [run(), run(), h.say_text("Done.")]
    _, person = ask_agent(script, ["no", "yes", "/quit"])
    assert person.asked.count(GATE_QUESTION) == 2
    assert [d["choice"] for d in decision_rows(conn)] == ["no", "yes"]
    assert len(h.rows(conn, "calc_runs")) == 1


def test_an_empty_answer_asks_again_with_the_same_text_and_records_nothing(ask_agent, conn):
    _, person = ask_agent(SCRIPT, ["", "   ", "\n", "yes", "/quit"])
    assert person.asked[:4] == [GATE_QUESTION] * 4
    assert [d["words"] for d in decision_rows(conn)] == ["yes"]
    assert len(h.events(conn, "ask.decision")) == 1


def test_a_quit_at_the_gate_is_a_no_and_does_not_end_the_conversation(ask_agent, conn):
    model, person = ask_agent(declined_script(), ["/quit", "/quit"])
    assert person.asked == [GATE_QUESTION, "Understood, nothing was run."]
    assert [m["role"] for m in model.calls[1]["messages"]] == ["user", "assistant", "tool"]


def test_the_gate_calls_no_model_of_its_own(ask_agent):
    model, _ = ask_agent(declined_script(), ["no", "/quit"])
    assert len(model.calls) == 2


def test_the_texts_of_a_reply_that_asks_for_a_run_are_still_not_shown(ask_agent):
    script = [h.tools(("run_module", run_args()), text="Surely 7,777!"), h.say_text(REPLY)]
    _, person = ask_agent(script, ["yes", "/quit"])
    assert "Surely 7,777!" not in person.told and "Surely 7,777!" not in person.asked


# ---- the record --------------------------------------------------------------------------------------------------

def test_the_decision_of_a_yes(ask_agent, conn):
    ask_agent(SCRIPT, ["yes", "/quit"])
    [decision] = decision_rows(conn)
    assert decision["id"] == 1 and decision["session_id"] == SESSION and decision["kind"] == "assumptions"
    assert decision["step_id"] is None and decision["question"] == BLOCK
    assert json.loads(decision["options"]) == [] and json.loads(decision["runs"]) == []
    assert (decision["choice"], decision["words"]) == ("yes", "yes")


def test_the_decision_of_a_no_keeps_the_words(ask_agent, conn):
    ask_agent(declined_script(), ["  Use my own figure instead  ", "/quit"])
    [decision] = decision_rows(conn)
    assert (decision["kind"], decision["choice"], decision["words"], decision["question"]) == (
        "assumptions", "no", "Use my own figure instead", BLOCK)


def test_the_events_of_a_shown_gate_in_order(ask_agent, conn):
    ask_agent(SCRIPT, ["yes", "/quit"])
    assert s4.conversation_kinds(conn) == ["ask.message", "ask.gate", "ask.decision", "calc.tests_run", "calc.run",
                                           "ask.reply"]


def test_the_events_of_a_gate_that_was_declined(ask_agent, conn):
    ask_agent(declined_script(), ["no", "/quit"])
    assert s4.conversation_kinds(conn) == ["ask.message", "ask.gate", "ask.decision", "ask.reply"]


def test_ask_gate_holds_the_arguments_as_sent_and_the_block_shown(ask_agent, conn):
    ask_agent(SCRIPT, ["yes", "/quit"])
    assert h.events(conn, "ask.gate") == [("ask.gate", "agent", {"calls": [run_args()], "block": BLOCK})]
    assert list(h.payloads(conn, "ask.gate")[0]) == ["calls", "block"]


def test_ask_decision_event_of_the_gate_is_the_decision_without_ts_and_session(ask_agent, conn):
    ask_agent(SCRIPT, ["yes", "/quit"])
    assert h.events(conn, "ask.decision") == [("ask.decision", "person", {
        "id": 1, "kind": "assumptions", "step": None, "question": BLOCK, "options": [], "choice": "yes",
        "words": "yes", "runs": []})]


def test_the_events_carry_the_session_id(ask_agent, conn):
    ask_agent(SCRIPT, ["yes", "/quit"])
    rows = conn.execute("SELECT DISTINCT session_id FROM events WHERE kind IN ('ask.gate', 'ask.decision')").fetchall()
    assert [r["session_id"] for r in rows] == [SESSION]


def test_the_words_of_a_gate_answer_are_a_source_for_the_number_check(ask_agent):
    script = [run(), h.say_text("You said 180 at the gate.")]
    _, person = ask_agent(script, ["yes, but with 180", "/quit"])
    assert person.asked[-1] == "You said 180 at the gate."


def test_the_gate_block_is_not_a_reply_and_the_run_is_recorded_with_its_assumptions(ask_agent, conn):
    ask_agent(SCRIPT, ["yes", "/quit"])
    [run_row] = h.rows(conn, "calc_runs")
    assert json.loads(run_row["assumptions"]) == ASSUME
    assert h.events(conn, "ask.reply") == [("ask.reply", "agent", {"text": REPLY})]


# ---- the gate looks at a reply before any of its calls is handled -------------------------------------------------------

def test_the_gate_comes_before_a_save_input_of_the_same_reply(ask_agent, conn):
    script = [h.tools(("save_input", {"name": "buffer", "value": "5000", "note": "n"}), ("run_module", run_args())),
              h.say_text("Noted.")]
    model, _ = ask_agent(script, ["yes", "/quit"])
    names = h.kinds(conn)
    assert names.index("ask.decision") < names.index("ask.input_saved") < names.index("calc.run")
    assert [m["content"] for m in model.calls[1]["messages"] if m["role"] == "tool"][0] == h.SAVED


def test_other_calls_go_on_when_the_person_says_no(ask_agent, conn):
    script = [h.tools(("run_module", run_args()), ("save_input", {"name": "buffer", "value": "5000", "note": "n"}),
                      ("frobnicate", {})), h.say_text("Understood.")]
    model, _ = ask_agent(script, ["no", "/quit"])
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert [json.loads(messages[0]["content"])["outcome"], messages[1]["content"], messages[2]["content"]] == [
        "not_run", h.SAVED, "There is no tool called frobnicate here."]
    assert len(h.rows(conn, "inputs")) == 1 and h.rows(conn, "calc_runs") == []


def test_a_request_for_a_build_in_the_same_reply_is_asked_after_the_gate(months_only, talk, conn):
    script = [h.tools(("request_module", h.request_arguments("step", "s1")), ("run_module", run_args("months_to_goal", {
        "target": "10000", "monthly_saving": "2000"}))), h.say_text("Done.")]
    _, person = talk(script, ["yes", "no", "/quit"], question="I want 10000 and can save 2000 a month. How long?")
    asks = [t for t in person.asked if t in (GATE_QUESTION, h.REQUEST_QUESTION)]
    assert asks == [GATE_QUESTION, h.REQUEST_QUESTION]


# ---- the module's words, and the number check on the block -------------------------------------------------------------

def test_the_block_shows_the_description_of_the_module_of_each_call(ask_agent):
    script = [run(module="months_to_goal", inputs={"target": "100000", "monthly_saving": "2000"}), h.say_text("Done.")]
    _, person = ask_agent(script, ["yes", "/quit"], question="I want to reach 100000 and can save 2000 a month.")
    assert s4.gate_block(s4.months_item()) in person.told
    assert h.months_spec()["description"] in s4.gate_block(s4.months_item())


def test_expected_is_shown_in_one_line(ask_agent):
    script = [run(expected="  about\n  what comes in\tless what goes out "), h.say_text("Done.")]
    _, person = ask_agent(script, ["yes", "/quit"])
    shown = next(t for t in person.told if t.startswith("Before working"))
    assert shown.split("\n")[-1] == "     Expecting: about what comes in less what goes out"


def test_a_sentence_is_shown_in_one_line_and_once(ask_agent):
    script = [run(assumptions=["  Spending   stays\nthe same.  ", "spending stays the SAME.", "", "Income is steady."]),
              h.say_text("Done.")]
    _, person = ask_agent(script, ["yes", "/quit"])
    shown = next(t for t in person.told if t.startswith("Before working"))
    assert shown.split("\n")[3:6] == ["       - Spending stays the same.", "       - Income is steady.",
                                      "     Expecting: what comes in less what goes out"]
    assert len(shown.split("\n")) == 6


def test_the_calls_of_the_event_keep_every_sentence_as_sent(ask_agent, conn):
    sent = ["  Spending   stays\nthe same.  ", "spending stays the SAME.", ""]
    ask_agent([run(assumptions=sent), h.say_text("Done.")], ["yes", "/quit"])
    [payload] = h.payloads(conn, "ask.gate")
    assert payload["calls"][0]["assumptions"] == sent
    [row] = h.rows(conn, "calc_runs")
    assert json.loads(row["assumptions"]) == sent


def test_the_agent_does_not_ask_about_the_computed_output(ask_agent):
    _, person = ask_agent(SCRIPT, ["yes", "/quit"])
    shown = [t for t in person.told + person.asked if "2000" in t or "2,000" in t.replace(REPLY, "")]
    assert shown == []
