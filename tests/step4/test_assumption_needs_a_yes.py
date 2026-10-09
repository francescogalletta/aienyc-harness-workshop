"""SPEC 8.2: which run_module calls are held for a yes, and which are handled as before."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import (ASSUME, EXPECT, GATE_QUESTION, OTHER_ASSUME, SESSION, decision_rows, h, result_of, run,
                           run_args, run_pair)

OK = "Done."
HALF = {"income": "5000", "spending": "3000"}


def gate_asks(person):
    return person.asked.count(GATE_QUESTION)


def tool_contents(model, call_index):
    return [m["content"] for m in model.calls[call_index]["messages"] if m["role"] == "tool"]


def shown_gate(person):
    return [t for t in person.told if t.startswith(s4.GATE_INTRO)]


# ---- a call that is handled as before: it is never shown -------------------------------------------------------

def test_no_assumptions_no_gate(ask_agent, conn):
    _, person = ask_agent([run(assumptions=[]), h.say_text(OK)])
    assert gate_asks(person) == 0 and shown_gate(person) == [] and len(h.rows(conn, "calc_runs")) == 1
    assert h.events(conn, "ask.gate") == [] and decision_rows(conn) == []


@pytest.mark.parametrize("assumptions", [[""], ["   ", "\n"], ["", "  "]])
def test_assumptions_that_are_all_empty_are_an_empty_set(ask_agent, conn, assumptions):
    _, person = ask_agent([run(assumptions=assumptions), h.say_text(OK)])
    assert gate_asks(person) == 0 and len(h.rows(conn, "calc_runs")) == 1


def test_inputs_that_nothing_produced_are_refused_as_before_and_never_shown(ask_agent, conn):
    bad = {"income": "5000", "spending": "2999"}
    model, person = ask_agent([run(inputs=bad), h.say_text(OK)])
    result = h.tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == h.INPUTS_UNBACKED.format(numbers="2999")
    [(_, _, payload)] = h.events(conn, "ask.correction")
    assert payload["reason"] == "run_module" and payload["numbers"] == ["2999"]
    assert gate_asks(person) == 0 and h.events(conn, "ask.gate") == []


def test_a_module_that_is_not_registered_is_refused_by_the_gate_and_never_shown(ask_agent):
    model, person = ask_agent([run(module="ghost"), h.say_text(OK)])
    result = h.tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == h.NOT_REGISTERED.format(name="ghost")
    assert gate_asks(person) == 0


def test_a_module_whose_files_changed_is_refused_and_never_shown(ask_agent, modules_dir):
    (modules_dir / "monthly_surplus" / "module.py").write_text(h.WRONG_SURPLUS_PY, encoding="utf-8")
    model, person = ask_agent([run(), h.say_text(OK)])
    result = h.tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == h.FILES_CHANGED.format(name="monthly_surplus")
    assert gate_asks(person) == 0


@pytest.mark.parametrize("expected", ["", "   ", "\n \t"])
def test_an_expectation_that_is_empty_is_refused_and_never_shown(ask_agent, expected):
    model, person = ask_agent([run(expected=expected), h.say_text(OK)])
    result = h.tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == h.NO_EXPECTATION.format(name="monthly_surplus")
    assert gate_asks(person) == 0


@pytest.mark.parametrize("assumptions", ["Spending stays the same.", [5], ["fine", None], {"a": "b"}])
def test_assumptions_that_are_not_a_list_of_strings_are_refused_and_never_shown(ask_agent, assumptions):
    call = h.tool("run_module", {**run_args(), "assumptions": assumptions})
    model, person = ask_agent([call, h.say_text(OK)])
    result = h.tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == h.NO_EXPECTATION.format(name="monthly_surplus")
    assert gate_asks(person) == 0


def test_inputs_that_do_not_fit_the_spec_are_refused_and_never_shown(ask_agent, conn):
    model, person = ask_agent([run(inputs={"income": "5000"}), h.say_text(OK)])
    result = h.tool_message(model, 1)
    assert result["is_error"] is True and result["content"].startswith("The inputs do not fit 'monthly_surplus': ")
    assert gate_asks(person) == 0 and h.rows(conn, "calc_runs") == []


def test_a_call_that_is_refused_before_testing_costs_no_test_run(ask_agent, conn):
    before = len(h.rows(conn, "test_runs"))
    ask_agent([run(inputs={"income": "5000"}), h.say_text(OK)])
    assert len(h.rows(conn, "test_runs")) == before


def test_only_run_module_is_held(ask_agent, conn):
    script = [h.tools(("save_input", {"name": "buffer", "value": "5000", "note": "n"})), h.say_text(OK)]
    _, person = ask_agent(script)
    assert gate_asks(person) == 0 and len(h.rows(conn, "inputs")) == 1


# ---- the calls of one reply, one gate --------------------------------------------------------------------------------

def mixed_reply():
    return run_pair(
        run(assumptions=[]),                                                  # 1: no assumptions: not held
        run(inputs={"income": "6000", "spending": "4000"}, assumptions=ASSUME, expected="the good month"),   # 2: held
        run(module="ghost"),                                                  # 3: not registered: not held
        run(inputs={"income": "5000", "spending": "2999"}),                   # 4: unbacked inputs: not held
        run(module="months_to_goal", inputs={"target": "10000", "monthly_saving": "2000"},
            assumptions=OTHER_ASSUME, expected="a handful of months"),        # 5: held (2000 is in the question)
        run(inputs={"income": "5000"}),                                       # 6: does not fit: not held
        run(expected=""))                                                     # 7: no expectation: not held


def test_one_reply_gets_one_gate_with_the_held_calls_in_reply_order(ask_agent, conn):
    model, person = ask_agent([mixed_reply(), h.say_text(OK)], ["yes", "/quit"], question=s4.TWO_CASES)
    block = s4.gate_block(s4.surplus_item(ASSUME, "the good month"), s4.months_item(OTHER_ASSUME, "a handful of months"))
    assert shown_gate(person) == [block] and gate_asks(person) == 1
    [decision] = decision_rows(conn)
    assert decision["question"] == block
    [(_, _, payload)] = h.events(conn, "ask.gate")
    assert [c["module"] for c in payload["calls"]] == ["monthly_surplus", "months_to_goal"]
    assert payload["calls"][0]["inputs"] == {"income": "6000", "spending": "4000"} and payload["block"] == block


def test_the_results_are_in_the_order_of_the_calls_whatever_the_gate_gave(ask_agent):
    model, _ = ask_agent([mixed_reply(), h.say_text(OK)], ["yes", "/quit"], question=s4.TWO_CASES)
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert len(messages) == 7
    assert json.loads(messages[0]["content"])["output"] == "2000"                      # 1
    assert json.loads(messages[1]["content"])["output"] == "2000"                      # 2 (held, yes)
    assert messages[2]["content"] == h.NOT_REGISTERED.format(name="ghost")             # 3
    assert messages[3]["content"] == h.INPUTS_UNBACKED.format(numbers="2999")          # 4
    assert json.loads(messages[4]["content"]) == {"module": "months_to_goal", "run_id": 3, "output": "5"}   # 5 (held, yes)
    assert messages[5]["content"].startswith("The inputs do not fit 'monthly_surplus'")  # 6
    assert messages[6]["content"] == h.NO_EXPECTATION.format(name="monthly_surplus")   # 7
    assert [bool(m.get("is_error")) for m in messages] == [False, False, True, True, False, True, True]


def test_one_no_gives_every_held_call_not_run_and_the_others_go_on(ask_agent, conn):
    model, person = ask_agent([mixed_reply(), h.say_text(OK)], ["Not with those", "/quit"], question=s4.TWO_CASES)
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    said = json.dumps({"outcome": "not_run", "said": "Not with those"})
    assert messages[1]["content"] == said and messages[4]["content"] == said
    assert json.loads(messages[0]["content"])["output"] == "2000"                      # the call without assumptions ran
    assert messages[2]["content"] == h.NOT_REGISTERED.format(name="ghost")
    assert [r["module"] for r in h.rows(conn, "calc_runs")] == ["monthly_surplus"]
    assert gate_asks(person) == 1 and [d["choice"] for d in decision_rows(conn)] == ["no"]


def test_a_yes_for_a_group_accepts_every_set_of_the_group(ask_agent):
    script = [mixed_reply(), run_pair(run(inputs={"income": "6000", "spending": "4000"}, assumptions=ASSUME),
                                      run(module="months_to_goal", inputs={"target": "10000", "monthly_saving": "2000"},
                                          assumptions=OTHER_ASSUME)), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "/quit"], question=s4.TWO_CASES)
    assert gate_asks(person) == 1


def test_two_held_calls_with_the_same_set_are_two_items_of_the_block(ask_agent, conn):
    first = run(assumptions=ASSUME, expected="the usual month")
    second = run(inputs={"income": "6000", "spending": "4000"}, assumptions=["  SPENDING stays the same each month. "],
                 expected="the good month")
    _, person = ask_agent([run_pair(first, second), h.say_text(OK)], ["yes", "/quit"], question=s4.TWO_CASES)
    assert shown_gate(person) == [s4.gate_block(s4.surplus_item(ASSUME, "the usual month"),
                                                s4.surplus_item(["  SPENDING stays the same each month. "], "the good month"))]
    assert len(h.rows(conn, "calc_runs")) == 2 and len(decision_rows(conn)) == 1


# ---- remembered for the conversation ---------------------------------------------------------------------------------

def test_a_set_accepted_is_not_asked_about_again(ask_agent):
    script = [run(), run(inputs={"income": "6000", "spending": "4000"}), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "/quit"], question=s4.TWO_CASES)
    assert gate_asks(person) == 1


@pytest.mark.parametrize("again", [
    ["Spending stays the same each month."], ["  spending STAYS   the same each month.  "],
    ["Spending stays the same each month.", ""], ["Spending stays the same each month.", "SPENDING STAYS THE SAME EACH MONTH."],
    ["\nSpending stays the\n\tsame each month.\n"]])
def test_the_same_set_written_another_way_is_the_same_set(ask_agent, again):
    script = [run(), run(assumptions=again), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "/quit"])
    assert gate_asks(person) == 1


def test_the_same_sentences_in_any_order_are_the_same_set(ask_agent):
    a, b = "Spending stays the same each month.", "Income is steady."
    script = [run(assumptions=[a, b]), run(assumptions=[b, a]), run(assumptions=[b, a, b]), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "/quit"])
    assert gate_asks(person) == 1


@pytest.mark.parametrize("other", [
    ["Spending stays the same each month"], ["Spending stays the same each month.", "Income is steady."],
    ["Income is steady."], ["Spending stays the same every month."]])
def test_a_different_set_is_asked_about_even_when_a_sentence_of_it_was_accepted(ask_agent, other):
    script = [run(), run(assumptions=other), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "yes", "/quit"])
    assert gate_asks(person) == 2
    shown = shown_gate(person)
    assert shown[1] == s4.gate_block(s4.surplus_item(other))


def test_a_smaller_set_is_not_let_through_by_a_bigger_one(ask_agent):
    both = ["Spending stays the same each month.", "Income is steady."]
    script = [run(assumptions=both), run(assumptions=ASSUME), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "yes", "/quit"])
    assert gate_asks(person) == 2


def test_only_the_calls_that_need_a_yes_are_in_a_later_block(ask_agent):
    script = [run(), run_pair(run(inputs={"income": "6000", "spending": "4000"}),
                              run(module="months_to_goal", inputs={"target": "10000", "monthly_saving": "2000"},
                                  assumptions=OTHER_ASSUME, expected="a few months")), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "yes", "/quit"], question=s4.TWO_CASES)
    assert shown_gate(person)[1] == s4.gate_block(s4.months_item(OTHER_ASSUME, "a few months"))
    assert gate_asks(person) == 2


def test_a_declined_set_is_asked_about_again_when_it_is_sent_again(ask_agent, conn):
    script = [run(), run(), run(), h.say_text(OK)]
    _, person = ask_agent(script, ["no", "no", "yes", "/quit"])
    assert gate_asks(person) == 3
    assert [d["choice"] for d in decision_rows(conn)] == ["no", "no", "yes"]


def test_a_decline_does_not_forget_what_was_accepted(ask_agent):
    script = [run(), run(assumptions=OTHER_ASSUME), run(), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "no", "/quit"])
    assert gate_asks(person) == 2


def test_a_set_is_accepted_for_every_module_it_is_sent_with(ask_agent):
    script = [run(), run(module="months_to_goal", inputs={"target": "10000", "monthly_saving": "2000"}), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "/quit"], question=s4.TWO_CASES)
    assert gate_asks(person) == 1


def test_nothing_is_remembered_across_conversations(agent, conn, brief, installed):
    for session in ("first-chat", "second-chat"):
        person = h.Person("yes", "/quit")
        model = s4.Model([run(), h.say_text(OK)], person)
        agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=session,
                        question=h.QUESTION, today=h.DAY)
        assert person.asked.count(GATE_QUESTION) == 1
    assert [d["session_id"] for d in decision_rows(conn)] == ["first-chat", "second-chat"]


def test_a_decision_in_the_database_does_not_let_a_new_conversation_through(agent, conn, brief, installed, decisions):
    decisions.record_decision(conn, session_id="old", kind="assumptions", step_id=None,
                              question=s4.gate_block(s4.surplus_item()), options=[], choice="yes", words="yes", runs=[])
    person = h.Person("yes", "/quit")
    agent.run_agent(model=s4.Model([run(), h.say_text(OK)], person), conn=conn, brief=brief, ask=person.ask,
                    say=person.say, session_id=SESSION, question=h.QUESTION, today=h.DAY)
    assert person.asked.count(GATE_QUESTION) == 1


# ---- the number check on the block ---------------------------------------------------------------------------------------

def test_an_unbacked_number_in_an_assumption_shows_nothing_and_refuses_the_call(ask_agent, conn):
    args = run_args(assumptions=["Assuming a 7.25% return on savings."], expected="what comes in")
    model, person = ask_agent([h.tool("run_module", args), h.say_text(OK)])
    result = h.tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == s4.GATE_UNBACKED.format(numbers="7.25%")
    assert shown_gate(person) == [] and gate_asks(person) == 0
    assert h.events(conn, "ask.gate") == [] and decision_rows(conn) == [] and h.rows(conn, "calc_runs") == []
    assert h.events(conn, "ask.correction") == [("ask.correction", "harness", {
        "reason": "assumptions", "numbers": ["7.25%"], "text": json.dumps([args])})]


def test_an_unbacked_number_in_the_expectation_is_refused_too(ask_agent, conn):
    args = run_args(expected="about 2,000 or so")
    model, _ = ask_agent([h.tool("run_module", args), h.say_text(OK)])
    assert h.tool_message(model, 1)["content"] == s4.GATE_UNBACKED.format(numbers="2,000")
    [(_, _, payload)] = h.events(conn, "ask.correction")
    assert payload["reason"] == "assumptions" and payload["numbers"] == ["2,000"]


def test_a_number_in_the_description_of_the_module_counts(conn, talk):
    files = s3_with_description(h.surplus_files("s1"), "The money left over in a typical 4,321 day month.")
    h.install(conn, files, "s1")
    h.install_months(conn, "s3")
    model, person = talk([run(), h.say_text(OK)])
    assert h.tool_message(model, 1)["content"] == s4.GATE_UNBACKED.format(numbers="4,321")
    assert shown_gate(person) == []


def s3_with_description(files, description):
    return s4.s3.with_spec(files, description=description)


def test_every_held_call_of_the_reply_gets_the_error_and_the_text_is_the_list_of_their_arguments(ask_agent, conn):
    bad = run_args(assumptions=["Assuming a 7.25% return on savings."])
    good = run_args(inputs={"income": "6000", "spending": "4000"}, assumptions=OTHER_ASSUME)
    other = run_args(assumptions=[])
    script = [h.tools(("run_module", bad), ("run_module", good), ("run_module", other)), h.say_text(OK)]
    model, person = ask_agent(script, question=s4.TWO_CASES)
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert [m["content"] for m in messages[:2]] == [s4.GATE_UNBACKED.format(numbers="7.25%")] * 2
    assert all(m["is_error"] is True for m in messages[:2])
    assert json.loads(messages[2]["content"])["output"] == "2000"               # the call that was not held went on
    [(_, _, payload)] = h.events(conn, "ask.correction")
    assert payload["text"] == json.dumps([bad, good])
    assert gate_asks(person) == 0


def test_the_agent_can_try_again_without_the_number(ask_agent, conn):
    script = [run(assumptions=["Assuming a 7.25% return on savings."]), run(), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "/quit"])
    assert gate_asks(person) == 1 and len(h.rows(conn, "calc_runs")) == 1


@pytest.mark.parametrize("assumption, expected", [
    ("Rent stays at 1,150 a month.", EXPECT),                       # a particular of the brief
    ("Take home stays 5000 a month.", "3000 goes out"),             # the person's own message
    ("Spending stays the same each month.", "about 5000 less 3000"),
    ("Today is 2026-03-14 and nothing changes.", EXPECT)])          # today
def test_numbers_the_check_knows_are_fine_in_the_block(ask_agent, assumption, expected):
    _, person = ask_agent([run(assumptions=[assumption], expected=expected), h.say_text(OK)], ["yes", "/quit"])
    assert gate_asks(person) == 1


def test_a_saved_input_and_a_note_back_numbers_in_the_block(ask_agent, conn, notes):
    conn.execute("INSERT INTO inputs (name, value, note, ts, session_id) VALUES (?, ?, ?, ?, ?)",
                 ("buffer", json.dumps("8250"), "said earlier", "2026-01-01T00:00:00+00:00", "an-earlier-session"))
    conn.commit()
    notes.add_note(conn, step_id="s1", text="My deposit is 4,321.", session_id="an-earlier-session")
    _, person = ask_agent([run(assumptions=["The buffer of 8,250 is untouched.", "The deposit of 4,321 is paid."]),
                           h.say_text(OK)], ["yes", "/quit"])
    assert gate_asks(person) == 1


def test_a_result_of_this_conversation_backs_a_number_in_a_later_block(ask_agent):
    script = [run(assumptions=[]), run(assumptions=ASSUME, expected="about 2,000 again"), h.say_text(OK)]
    _, person = ask_agent(script, ["yes", "/quit"])
    assert gate_asks(person) == 1


# ---- a call that comes to need a yes during the reply -----------------------------------------------------------------------

YEARLY_ARGS = {"module": "yearly_cost", "inputs": {"monthly": "250"}, "assumptions": ["Costs stay the same all year."],
               "expected": "twelve times the monthly cost"}


def test_a_module_built_by_the_same_reply_is_asked_first(ask_agent, conn):
    script = [h.tools(("request_module", h.request_arguments("new")), ("run_module", YEARLY_ARGS)),
              *h.yearly_script(), h.tool("run_module", YEARLY_ARGS), h.say_text("It comes to 3,000 a year.")]
    answers = ["yes", "yes", *h.accepts(3), "yes", "/quit"]
    model, person = ask_agent(script, answers, question=h.YEARLY_QUESTION)
    calls = model.of("analyst")
    assert model.roles() == ["analyst", "spec_writer", "example_writer", "module_writer", "analyst", "analyst"]
    messages = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert json.loads(messages[0]["content"])["outcome"] == "built" and not messages[0].get("is_error")
    assert messages[1]["is_error"] is True and messages[1]["content"] == s4.ASK_FIRST
    assert gate_asks(person) == 1                                     # the agent called again, and the gate was shown
    assert shown_gate(person) == [s4.gate_block((s4.YEARLY, YEARLY_ARGS["assumptions"], YEARLY_ARGS["expected"]))]
    assert [r["module"] for r in h.rows(conn, "calc_runs")] == ["yearly_cost"]
    assert result_of(model, 5)["output"] == "3000"
    assert h.events(conn, "ask.gate")[0][2]["calls"] == [YEARLY_ARGS]


def test_a_call_that_ran_without_being_shown_is_impossible_ask_first_runs_nothing(ask_agent, conn):
    script = [h.tools(("request_module", h.request_arguments("new")), ("run_module", YEARLY_ARGS)),
              *h.yearly_script(), h.say_text("I could not run it.")]
    model, person = ask_agent(script, ["yes", "yes", *h.accepts(3), "/quit"], question=h.YEARLY_QUESTION)
    assert h.rows(conn, "calc_runs") == [] and decision_rows(conn)[0]["kind"] == "build"
    assert gate_asks(person) == 0 and h.events(conn, "ask.gate") == []
    assert len(decision_rows(conn)) == 1


def test_inputs_that_a_run_of_the_same_reply_makes_known_are_asked_first(ask_agent, conn):
    """Unbacked when the reply was looked at, backed when the call is handled: the call has not been shown."""
    question = "I earn 5000, spend 3000 and want to reach 10000. How long will it take?"
    later = run(module="months_to_goal", inputs={"target": "10000", "monthly_saving": "2000"}, assumptions=OTHER_ASSUME,
                expected="a handful of months")
    script = [run_pair(run(assumptions=[]), later), h.say_text(OK)]
    model, person = ask_agent(script, question=question)
    messages = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert json.loads(messages[0]["content"])["output"] == "2000"
    assert messages[1]["is_error"] is True and messages[1]["content"] == s4.ASK_FIRST
    assert gate_asks(person) == 0 and h.events(conn, "ask.correction") == []
    assert [r["module"] for r in h.rows(conn, "calc_runs")] == ["monthly_surplus"]


def test_inputs_still_unbacked_when_the_call_is_handled_are_refused_as_before(ask_agent, conn):
    question = "I earn 5000, spend 3000 and want to reach 10000. How long will it take?"
    later = run(module="months_to_goal", inputs={"target": "10000", "monthly_saving": "2500"}, assumptions=OTHER_ASSUME)
    model, _ = ask_agent([run_pair(run(assumptions=[]), later), h.say_text(OK)], question=question)
    result = [m for m in model.calls[1]["messages"] if m["role"] == "tool"][1]
    assert result["is_error"] is True and result["content"] == h.INPUTS_UNBACKED.format(numbers="2500")
