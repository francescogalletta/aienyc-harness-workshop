"""SPEC 5.9: the agent answers questions, and cannot put a number in front of the person that nothing produced."""
import json
from datetime import date, datetime, timedelta

import pytest

import step2_helpers as h
from harness.model import ScriptedModel
from step2_helpers import (BAD_NAME, EMPTY_REPLY, EMPTY_VALUE, INPUTS_UNBACKED, NO_EXPECTATION, NOT_REGISTERED,
                           NUMBERS_CORRECTION, OPENING, SAVED, SESSION, TOO_MANY, WITHHELD, WITHHELD_NOTE, Person,
                           events, payloads, rows, run_module, save_input, say_text, tool, tools)

DAY = date(2026, 3, 14)
QUESTION = "I earn 5000 and spend 3000 a month. What is left each month?"
UNBACKED_REPLY = "You will have 9,999 left."
OTHER_UNBACKED = "Perhaps 8,888 instead."


@pytest.fixture
def installed(conn):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")


@pytest.fixture
def ask_agent(agent, conn, brief, installed):
    """Run the agent with a scripted model and a person who answers from a list (then must be done)."""
    def run(script, answers=("/quit",), *, question=QUESTION, **options):
        model, person = ScriptedModel(script), Person(*answers)
        options = {"today": DAY, "session_id": SESSION, "brief": brief, **options}
        agent.run_agent(model=model, conn=conn, ask=person.ask, say=person.say, question=question, **options)
        return model, person
    return run


def tool_message(model, call_index, position=-1):
    return [m for m in model.calls[call_index]["messages"] if m["role"] == "tool"][position]


def user_messages(model, call_index):
    return [m["content"] for m in model.calls[call_index]["messages"] if m["role"] == "user"]


# ---- the fixed strings and schemas -----------------------------------------------------------

@pytest.mark.parametrize("name", [
    "OPENING", "NUMBERS_CORRECTION", "WITHHELD", "WITHHELD_NOTE", "INPUTS_UNBACKED", "EMPTY_REPLY", "TOO_MANY",
    "BAD_NAME", "EMPTY_VALUE", "SAVED"])
def test_the_fixed_strings(agent, name):
    assert getattr(agent, name) == getattr(h, name)


def test_the_limit_and_the_schemas(agent):
    assert agent.MAX_CALLS == 10
    assert h.without_descriptions(agent.RUN_MODULE_SCHEMA) == h.RUN_MODULE_SCHEMA
    assert h.without_descriptions(agent.SAVE_INPUT_SCHEMA) == h.SAVE_INPUT_SCHEMA


# ---- the model is called with ----------------------------------------------------------------

def test_the_model_gets_the_question_and_the_two_tools(ask_agent):
    model, person = ask_agent([say_text("Let me think.")])
    [call] = model.calls
    assert call["messages"] == [{"role": "user", "content": QUESTION}]
    assert [t.name for t in call["tools"]] == ["run_module", "save_input"]
    assert [h.without_descriptions(t.input_schema) for t in call["tools"]] == [h.RUN_MODULE_SCHEMA, h.SAVE_INPUT_SCHEMA]
    assert "  (thinking)" in person.told


def test_the_system_prompt_is_analyst_md_with_the_context(ask_agent, brief):
    model, _ = ask_agent([say_text("Hello.")])
    context = h.sections(
        ("today", "2026-03-14"), ("goal", brief["goal"]), ("particulars", brief["particulars"]),
        ("process", brief["process"]),
        ("modules", {"monthly_surplus": {"steps": ["s1"], "spec": h.saved_spec(h.surplus_spec(), "s1")},
                     "months_to_goal": {"steps": ["s3"], "spec": h.saved_spec(h.months_spec(), "s3")}}),
        ("saved inputs", {}))
    system = model.calls[0]["system"]
    assert system.strip() == h.prompt_text("analyst.md").replace("{context}", context).strip()
    assert "{context}" not in system


def test_today_defaults_to_the_real_date(agent, conn, brief, installed):
    model, person = ScriptedModel([say_text("Hello.")]), Person("/quit")
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=SESSION, question="Hi")
    assert f"[today]\n{date.today().isoformat()}" in model.calls[0]["system"]


def test_the_context_is_made_once_when_the_session_starts(ask_agent):
    script = [tools(("save_input", {"name": "buffer", "value": "5000", "note": "n"})), say_text("Saved it."),
              say_text("Done.")]
    model, _ = ask_agent(script, ["Anything else?", "/quit"])
    assert len({call["system"] for call in model.calls}) == 1
    assert "buffer" not in model.calls[0]["system"]


# ---- the loop --------------------------------------------------------------------------------

def test_the_reply_is_shown_by_asking_the_person_about_it(ask_agent, conn):
    model, person = ask_agent([say_text("Hello there.")])
    assert person.asked == ["Hello there."]
    assert "Hello there." not in person.told
    assert events(conn, "ask.reply") == [("ask.reply", "agent", {"text": "Hello there."})]


def test_a_follow_up_is_recorded_and_added_to_the_conversation(ask_agent, conn):
    model, _ = ask_agent([say_text("First."), say_text("Second.")], ["And next month?", "/quit"])
    assert user_messages(model, 1) == [QUESTION, "And next month?"]
    assert [(m["role"], m["content"]) for m in model.calls[1]["messages"]] == [
        ("user", QUESTION), ("assistant", "First."), ("user", "And next month?")]
    assert events(conn, "ask.message")[-1] == ("ask.message", "person", {"text": "And next month?"})


def test_the_first_message_is_recorded_too(ask_agent, conn):
    ask_agent([say_text("Hello.")])
    assert payloads(conn, "ask.message") == [{"text": QUESTION}]


def test_a_typed_answer_is_stripped_before_it_is_recorded_and_used(ask_agent, conn):
    model, _ = ask_agent([say_text("First."), say_text("Second.")], ["  And next month?  \n", "/quit"])
    assert user_messages(model, 1) == [QUESTION, "And next month?"]
    assert payloads(conn, "ask.message")[-1] == {"text": "And next month?"}


def test_the_answer_to_the_opening_question_is_stripped_and_recorded(ask_agent, conn):
    model, _ = ask_agent([say_text("Hello.")], ["  What is left?  ", "/quit"], question="")
    assert user_messages(model, 0) == ["What is left?"]
    assert payloads(conn, "ask.message") == [{"text": "What is left?"}]


def test_quit_ends_the_session_and_is_not_recorded(ask_agent, conn):
    model, person = ask_agent([say_text("Hello.")], ["  /quit  "])
    assert len(model.calls) == 1
    assert all(p["text"] != "/quit" for p in payloads(conn, "ask.message"))


def test_an_empty_answer_asks_again_with_the_same_text(ask_agent):
    _, person = ask_agent([say_text("Hello.")], ["", "   ", "/quit"])
    assert person.asked == ["Hello."] * 3


def test_without_a_question_the_agent_opens_by_asking(ask_agent):
    model, person = ask_agent([say_text("Hello.")], ["What is left?", "/quit"], question="")
    assert person.asked[0] == OPENING
    assert model.calls[0]["messages"] == [{"role": "user", "content": "What is left?"}]


@pytest.mark.parametrize("answer", ["", "   ", "/quit"])
def test_an_empty_or_quit_answer_to_the_opening_ends_the_session(ask_agent, answer):
    model, person = ask_agent([], [answer], question="")
    assert model.calls == [] and person.asked == [OPENING]


def test_an_empty_reply_is_sent_back(ask_agent):
    model, person = ask_agent([say_text(""), say_text("Here you are.")])
    assert model.calls[1]["messages"][-1] == {"role": "user", "content": EMPTY_REPLY}
    assert person.asked == ["Here you are."]


def test_the_model_is_called_at_most_ten_times_per_person_message(ask_agent, conn):
    model, person = ask_agent([say_text("")] * 10)
    assert len(model.calls) == 10
    assert person.asked == [TOO_MANY]
    assert events(conn, "ask.stopped") == [("ask.stopped", "harness", {"reason": "too many steps"})]


def test_the_count_starts_again_with_the_next_person_message(ask_agent):
    model, person = ask_agent([say_text("")] * 10 + [say_text("Fine.")], ["Try once more", "/quit"])
    assert len(model.calls) == 11
    assert person.asked == [TOO_MANY, "Fine."]


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


def test_the_numbers_are_listed_in_order_joined_by_commas(ask_agent):
    model, _ = ask_agent([say_text("First 1,111 then 2,222 then 1,111."), say_text("Fine.")])
    assert model.calls[1]["messages"][-1]["content"] == NUMBERS_CORRECTION.format(numbers="1,111, 2,222")


def test_after_a_withheld_reply_the_next_message_carries_a_note(ask_agent):
    model, person = ask_agent([say_text(UNBACKED_REPLY), say_text(OTHER_UNBACKED), say_text("I cannot say.")],
                              ["Please try again", "/quit"])
    assert model.calls[2]["messages"][-2]["role"] == "assistant"
    assert model.calls[2]["messages"][-2]["content"] == OTHER_UNBACKED
    assert model.calls[2]["messages"][-1] == {
        "role": "user", "content": "Please try again\n\n" + WITHHELD_NOTE.format(numbers="8,888")}
    assert person.asked == [WITHHELD.format(numbers="8,888"), "I cannot say."]


def test_every_person_message_gets_its_own_correction(ask_agent, conn):
    script = [say_text(UNBACKED_REPLY), say_text("Fine."), say_text(UNBACKED_REPLY), say_text("Fine again.")]
    ask_agent(script, ["Next question", "/quit"])
    assert len(events(conn, "ask.correction")) == 2 and events(conn, "ask.withheld") == []


def test_the_text_of_a_reply_that_calls_tools_is_not_shown_or_checked(ask_agent, conn):
    script = [tools(("save_input", {"name": "buffer", "value": "5000", "note": "n"}), text="Surely 7,777!"),
              say_text("Noted.")]
    _, person = ask_agent(script, question="Remember that my buffer is 5000.")
    assert person.asked == ["Noted."] and "Surely 7,777!" not in person.told
    assert events(conn, "ask.correction") == []


# ---- what counts as known --------------------------------------------------------------------

def test_numbers_from_the_persons_question_are_backed(ask_agent):
    _, person = ask_agent([say_text("You said 5,000 comes in and 3,000 goes out.")])
    assert person.asked == ["You said 5,000 comes in and 3,000 goes out."]


def test_numbers_from_later_messages_are_backed(ask_agent):
    _, person = ask_agent([say_text("Hello."), say_text("Counting the 777 bonus.")], ["My bonus is 777.", "/quit"])
    assert person.asked == ["Hello.", "Counting the 777 bonus."]


def test_numbers_from_the_brief_are_backed(ask_agent):
    _, person = ask_agent([say_text("Your rent is 1,150 a month.")])
    assert person.asked == ["Your rent is 1,150 a month."]


def test_today_is_backed(ask_agent):
    _, person = ask_agent([say_text("Today is 2026-03-14.")])
    assert person.asked == ["Today is 2026-03-14."]


def test_a_date_that_is_not_today_is_not_backed(ask_agent, conn):
    ask_agent([say_text("The deadline is 2026-03-15."), say_text("No date.")])
    [numbers] = [p["numbers"] for p in payloads(conn, "ask.correction")]
    assert len(numbers) == 1 and "15" in numbers[0]


def test_saved_inputs_from_any_session_are_backed(ask_agent, conn):
    conn.execute("INSERT INTO inputs (name, value, note, ts, session_id) VALUES (?, ?, ?, ?, ?)",
                 ("buffer", json.dumps("8250"), "said earlier", datetime.now().isoformat(), "an-earlier-session"))
    conn.commit()
    _, person = ask_agent([say_text("You keep 8,250 as a buffer.")])
    assert person.asked == ["You keep 8,250 as a buffer."]


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


def test_assumptions_and_expectations_are_not_checked(ask_agent, conn):
    script = [run_module(assumptions=["Assuming a 7.25% return on savings."], expected="roughly 1,999 or so"),
              say_text("Done.")]
    ask_agent(script)
    [run] = rows(conn, "calc_runs")
    assert json.loads(run["assumptions"]) == ["Assuming a 7.25% return on savings."]
    assert run["expected"] == "roughly 1,999 or so"
    assert events(conn, "ask.correction") == []


# ---- run_module ------------------------------------------------------------------------------

def test_run_module_goes_through_the_gate(ask_agent, conn):
    script = [run_module(assumptions=["Income is steady."], expected="about 2,000"), say_text("It gives 2,000.")]
    model, person = ask_agent(script)
    [run] = rows(conn, "calc_runs")
    assert run["session_id"] == SESSION and run["module"] == "monthly_surplus"
    assert json.loads(run["inputs"]) == {"income": "5000", "spending": "3000"}
    assert json.loads(run["assumptions"]) == ["Income is steady."] and run["expected"] == "about 2,000"
    assert "  (running monthly_surplus)" in person.told
    result = tool_message(model, 1)
    assert not result.get("is_error")
    assert json.loads(result["content"]) == {"module": "monthly_surplus", "run_id": run["id"], "output": "2000"}
    assert [m["role"] for m in model.calls[1]["messages"]] == ["user", "assistant", "tool"]


def test_a_result_backs_the_inputs_of_the_next_run(ask_agent, conn):
    script = [run_module(), run_module("months_to_goal", {"target": "100000", "monthly_saving": "2000"}),
              say_text("It takes 50 months.")]
    _, person = ask_agent(script, question="I earn 5000, spend 3000 and want to reach 100000.")
    assert person.asked == ["It takes 50 months."] and len(rows(conn, "calc_runs")) == 2


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


def test_a_missing_expectation_is_refused_by_the_gate(ask_agent):
    model, _ = ask_agent([run_module(expected=""), say_text("Sorry.")])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == NO_EXPECTATION.format(name="monthly_surplus")


def test_a_module_whose_files_changed_is_refused(ask_agent, modules_dir):
    (modules_dir / "monthly_surplus" / "module.py").write_text(h.WRONG_SURPLUS_PY, encoding="utf-8")
    model, _ = ask_agent([run_module(), say_text("It cannot run.")])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == h.FILES_CHANGED.format(name="monthly_surplus")


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


def test_saving_a_name_again_replaces_it(ask_agent, conn):
    script = [save_input("monthly_income", "5000", "first"), save_input("monthly_income", "5000.50", "second"),
              say_text("Noted.")]
    ask_agent(script, question="My income is 5000, no, 5000.50.")
    [row] = rows(conn, "inputs")
    assert json.loads(row["value"]) == "5000.50" and row["note"] == "second"


def test_a_saved_input_appears_in_the_next_sessions_system_prompt(ask_agent, agent, conn, brief):
    ask_agent([save_input("monthly_income", "5000", "said by the person"), say_text("Noted.")])
    model, person = ScriptedModel([say_text("Hello again.")]), Person("/quit")
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id="next-session",
                    question="Hi", today=DAY)
    saved = model.calls[0]["system"].split("[saved inputs]\n")[1]
    assert "monthly_income" in saved and "5000" in saved and "said by the person" in saved


def test_a_saved_input_backs_numbers_in_the_next_session(ask_agent, agent, conn, brief):
    ask_agent([save_input("monthly_income", "5000", "n"), say_text("Noted.")])
    model, person = ScriptedModel([say_text("Your income is 5,000.")]), Person("/quit")
    agent.run_agent(model=model, conn=conn, brief=brief, ask=person.ask, say=person.say, session_id="next-session",
                    question="What do you know about me?", today=DAY)
    assert person.asked == ["Your income is 5,000."]


@pytest.mark.parametrize("name", ["Monthly Income", "monthly-income", "1st", "", "Income"])
def test_a_name_must_be_snake_case(ask_agent, conn, name):
    model, _ = ask_agent([save_input(name, "5000", "n"), say_text("Sorry.")])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == BAD_NAME
    assert rows(conn, "inputs") == []


def test_a_value_must_not_be_empty(ask_agent, conn):
    model, _ = ask_agent([save_input("monthly_income", "", "n"), say_text("Sorry.")])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == EMPTY_VALUE
    assert rows(conn, "inputs") == []


def test_a_value_nobody_gave_is_refused(ask_agent, conn):
    arguments = {"name": "monthly_income", "value": "9876", "note": "worked out"}
    model, _ = ask_agent([tool("save_input", arguments), say_text("Sorry.")])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == INPUTS_UNBACKED.format(numbers="9876")
    [(_, actor, payload)] = events(conn, "ask.correction")
    assert actor == "harness" and payload["reason"] == "save_input" and payload["numbers"] == ["9876"]
    assert json.loads(payload["text"]) == arguments
    assert rows(conn, "inputs") == [] and events(conn, "ask.input_saved") == []


def test_a_value_that_is_not_a_number_is_fine(ask_agent, conn):
    ask_agent([save_input("pay_day", "the last Friday", "n"), say_text("Noted.")])
    assert json.loads(rows(conn, "inputs")[0]["value"]) == "the last Friday"


# ---- other tool calls ------------------------------------------------------------------------

def test_another_tool_is_an_error(ask_agent):
    model, _ = ask_agent([tool("frobnicate", {}), say_text("Sorry.")])
    result = tool_message(model, 1)
    assert result["is_error"] is True and result["content"] == "There is no tool called frobnicate here."


def test_several_calls_in_one_reply_are_handled_in_order_and_added_together(ask_agent):
    script = [tools(("save_input", {"name": "monthly_income", "value": "5000", "note": "n"}),
                    ("frobnicate", {}),
                    ("run_module", {"module": "monthly_surplus", "inputs": {"income": "5000", "spending": "3000"},
                                    "assumptions": [], "expected": "about 2,000"})),
              say_text("Done.")]
    model, _ = ask_agent(script)
    messages = model.calls[1]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "tool", "tool", "tool"]
    assert [m["tool_call_id"] for m in messages[2:]] == [c["id"] for c in messages[1]["tool_calls"]]
    assert messages[2]["content"] == SAVED
    assert messages[3]["content"] == "There is no tool called frobnicate here."
    assert json.loads(messages[4]["content"])["output"] == "2000"


# ---- events ----------------------------------------------------------------------------------

def test_every_event_carries_the_session_id(ask_agent, conn):
    ask_agent([run_module(), say_text("It gives 2,000.")])
    assert {r["session_id"] for r in conn.execute("SELECT session_id FROM events WHERE kind LIKE 'ask.%'")} == {SESSION}
