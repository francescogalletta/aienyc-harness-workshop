"""SPEC 1.1 and 5.1: the number check on replies and on tool inputs; the tools."""
import json

from harness.answers import agent
from harness.calc.notes import add_note
from layer3_helpers import assistant, call, events, reply, run, save, say


def runs(session):
    return session.conn.execute("SELECT * FROM calc_runs ORDER BY id").fetchall()


def test_a_number_from_a_run_the_person_a_note_or_today_is_shown_without_correction(open_session):
    session = open_session([run("total", {"a": 4000, "b": 250}),
                            reply("The total (step 1) is 4,250. You told me 4,000. Today is 2026-10-10. The note says 3,300.")])
    add_note(session.conn, step_id="c1", text="Last year it came to 3,300", session_id="x")
    state = say(session, "A is 4,000 and B is 250")
    assert [message["kind"] for message in assistant(state)] == ["text"]
    assert not events(session, "ask.correction") and not events(session, "ask.withheld")


def test_a_number_nothing_backs_is_corrected_once_and_never_shown(open_session):
    session = open_session([reply("The total is 999."), reply("I would have to run the module for that.")])
    state = say(session, "What is the total?")
    assert [message["text"] for message in assistant(state)] == ["I would have to run the module for that."]
    assert [(each["reason"], each["numbers"]) for each in events(session, "ask.correction")] == [("reply", ["999"])]
    assert session.script.calls[1]["messages"][-1]["content"].startswith("[harness]")
    assert not events(session, "ask.withheld")


def test_a_second_unbacked_reply_is_withheld_and_the_model_is_told_next_time(open_session):
    session = open_session([reply("The total is 999."), reply("Really, 999."), reply("Sorry.")])
    state = say(session, "What is the total?")
    held = assistant(state)
    assert [(message["who"], message["kind"]) for message in held] == [("harness", "withheld")]
    assert len(events(session, "ask.withheld")) == 1 and not events(session, "ask.reply")
    say(session, "Well?")
    assert "[harness]" in session.script.calls[-1]["messages"][-1]["content"]


def test_a_model_that_adds_up_the_persons_figures_is_not_shown_the_sum(open_session):
    session = open_session([reply("Your amounts come to 350."), reply("A module would tell you that.")])
    state = say(session, "A is 100 and B is 250, what is the total?")
    assert "350" not in " ".join(message["text"] for message in assistant(state))


def test_the_result_of_one_run_can_go_into_the_next_run(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), run("double", {"total": 350}),
                            reply("Doubled it is 700.")])
    state = say(session, "A is 100 and B is 250")
    assert [row["module"] for row in runs(session)] == ["total", "double"]
    assert assistant(state)[-1]["kind"] == "text" and not events(session, "ask.correction")


def test_inputs_nobody_gave_are_refused_before_the_gate_and_the_model_hears_why(open_session):
    session = open_session([run("total", {"a": 100, "b": 999}), reply("What is amount B?")])
    say(session, "A is 100")
    assert runs(session) == []
    assert [each["reason"] for each in events(session, "ask.correction")] == ["run_module"]
    result = session.script.calls[1]["messages"][-1]
    assert result["role"] == "tool" and result["is_error"] and "999" in result["content"]


def test_assumptions_are_number_checked_too(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}, assumptions=["B stays at 777"]), reply("Which B?")])
    say(session, "A is 100 and B is 250")
    assert runs(session) == [] and events(session, "ask.correction")[0]["numbers"] == ["777"]


def test_a_module_that_is_refused_is_reported_and_not_worked_around(open_session):
    session = open_session([run("no_such_module", {"a": 1}), run("total", {"a": 1}), reply("I cannot do that yet.")])
    state = say(session, "Work out the tax")
    assert runs(session) == [] and len(events(session, "calc.refused")) == 2
    tools = [message for message in session.script.calls[2]["messages"] if message["role"] == "tool"]
    assert len(tools) == 2 and all(message["is_error"] for message in tools)
    assert assistant(state)[-1]["text"] == "I cannot do that yet."


def test_a_module_whose_step_changed_in_the_plan_is_refused(open_session, tmp_path):
    session = open_session([run("total", {"a": 1, "b": 2}), reply("It must be built again.")])
    path = tmp_path / "brief" / "domain_brief.json"
    plan = json.loads(path.read_text())
    plan["process"][0]["formula"] = "a + b + fee"
    path.write_text(json.dumps(plan))
    say(session, "Total please")
    assert runs(session) == [] and events(session, "calc.refused")


def test_save_input_keeps_a_value_and_a_later_one_replaces_it(open_session):
    session = open_session([save("amount_a", 100), reply("Saved."), save("amount_a", 120), reply("Changed.")])
    say(session, "A is 100")
    say(session, "No, A is 120")
    rows = session.conn.execute("SELECT name, value FROM inputs").fetchall()
    assert [(row["name"], json.loads(row["value"])) for row in rows] == [("amount_a", "120")]
    assert [each["value"] for each in events(session, "ask.input_saved")] == ["100", "120"]


def test_save_input_refuses_a_bad_name_an_empty_value_and_a_number_nobody_gave(open_session):
    session = open_session([save("Amount A", 100), save("amount_a", " "), save("amount_a", 5551), reply("Which?")])
    say(session, "A is 100")
    assert session.conn.execute("SELECT * FROM inputs").fetchall() == []
    errors = [message for message in session.script.calls[-1]["messages"] if message["role"] == "tool"]
    assert len(errors) == 3 and all(message["is_error"] for message in errors)
    assert [each["reason"] for each in events(session, "ask.correction")] == ["save_input"]


def test_change_plan_needs_words_the_person_typed_and_then_revises_the_plan(open_session, monkeypatch):
    seen = []
    monkeypatch.setattr(agent, "revise_plan", lambda work, **options: seen.append(options) or {"changed": ["c1"]})
    session = open_session([call("change_plan", step="c1", words="my own idea"),
                            call("change_plan", step="c1", words="the TOTAL must  include a fee"),
                            call("change_plan", step="", words="the total must include a fee"),
                            reply("The total changed, so it must be built again.")])
    say(session, "The total must include a fee")
    assert seen == [{"words": "the TOTAL must  include a fee", "step": "c1", "by": "person"},
                    {"words": "the total must include a fee", "step": None, "by": "person"}]
    results = [message for message in session.script.calls[-1]["messages"] if message["role"] == "tool"]
    assert [bool(message.get("is_error")) for message in results] == [True, False, False]
    assert len(events(session, "ask.plan_changed")) == 2


def test_a_tool_that_does_not_exist_is_an_error_for_the_model(open_session):
    session = open_session([call("request_module", why="x"), reply("I cannot.")])
    say(session, "Hello")
    assert session.script.calls[1]["messages"][-1]["is_error"]
