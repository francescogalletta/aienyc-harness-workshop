"""SPEC 5.2: figures that lead to steps, the last run of each step, saved inputs on the plan's inputs."""
import json

from harness.answers.figures import figures, input_backing
from layer3_helpers import assistant, events, reply, run, save, say, step_of
from state_shape import problems


def valid(state):
    assert problems(state) == []
    return state


def test_figures_read_a_text_with_the_number_check_and_map_them_to_a_step_an_input_or_nothing():
    text = "Total 350 for 2026-10-10 and 4,000, step 1."
    sources = [("person", None, "I have 4,000"), ("today", None, "2026-10-10"), ("run", 7, "350")]
    found = figures(text, sources, step_of_run=lambda run_id: {7: "c1"}.get(run_id))
    assert [(each["text"], each["step"], each["run"]) for each in found] == [
        ("350", "c1", "r7"), ("2026-10-10", None, None), ("4,000", None, None), ("1", None, None)]
    assert all(text[each["start"]:each["end"]] == each["text"] for each in found)
    saved = [("in:a", "4000"), (None, "350")]
    assert input_backing("4,000", saved) == "in:a" and input_backing("350", saved) is None
    only = figures("4,000", [("input", None, "4000")], input_of=lambda written: input_backing(written, saved))
    assert only[0]["input"] == "in:a" and only[0]["step"] is None


def test_every_figure_of_an_answer_leads_to_the_step_that_produced_it(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), run("double", {"total": 350}),
                            reply("The total (step 1) is 350 and doubled it is 700.")])
    state = valid(say(session, "A is 100 and B is 250"))
    message = assistant(state)[-1]
    by_text = {each["text"]: each for each in message["figures"]}
    assert (by_text["350"]["step"], by_text["350"]["run"]) == ("c1", "r1")
    assert (by_text["700"]["step"], by_text["700"]["run"]) == ("c2", "r2")
    assert by_text["1"]["step"] is None
    assert all(message["text"][each["start"]:each["end"]] == each["text"] for each in message["figures"])


def test_a_figure_from_a_saved_input_names_the_plan_input(open_session):
    session = open_session([save("amount_a", 4000), save("some_other_thing", 777), reply("Amount A is 4,000 and the other is 777.")])
    state = valid(say(session, "A is 4,000 and the other thing is 777"))
    by_text = {each["text"]: each for each in assistant(state)[-1]["figures"]}
    assert by_text["4,000"]["input"] == "in:amount_a" and by_text["4,000"]["step"] is None
    assert by_text["777"]["input"] is None


def test_a_number_the_person_gave_to_a_module_leads_to_no_step(open_session):
    session = open_session([run("total", {"a": 4000, "b": 250}), reply("With 4,000 and 250 the total is 4,250.")])
    state = valid(say(session, "A is 4,000 and B is 250"))
    by_text = {each["text"]: each for each in assistant(state)[-1]["figures"]}
    assert by_text["4,000"]["step"] is None and by_text["4,250"]["step"] == "c1"


def test_a_range_is_two_runs_and_each_number_leads_to_its_run(open_session):
    session = open_session([run("total", {"a": 100, "b": 50}, expected="the low case"),
                            run("total", {"a": 200, "b": 50}, expected="the high case"),
                            reply("Low case 150, high case 250.")])
    state = valid(say(session, "A is 100 or 200, and B is 50"))
    by_text = {each["text"]: each for each in assistant(state)[-1]["figures"]}
    assert (by_text["150"]["step"], by_text["150"]["run"]) == ("c1", "r1")
    assert (by_text["250"]["step"], by_text["250"]["run"]) == ("c1", "r2")
    assert step_of(state, "c1")["last_run"]["run"] == "r2"


def test_before_any_answer_no_step_has_a_run_and_no_input_a_value(open_session):
    state = valid(open_session([]).state())
    assert all(step["last_run"] is None for step in state["steps"])
    assert all(entry["value"] is None and entry["used"] is False for entry in state["inputs"].values())


def test_the_steps_of_the_last_answer_show_what_went_in_and_what_came_out(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}, assumptions=["B stays as it is."]),
                            reply("The total is 350.")])
    state = valid(say(session, "A is 100 and B is 250"))
    first, other = step_of(state, "c1"), step_of(state, "c2")
    shown = first["last_run"]
    assert shown["run"] == "r1" and shown["message"] == assistant(state)[-1]["id"] and shown["in_last_answer"]
    assert shown["inputs"] == {"a": "100", "b": "250"} and shown["output"] == "350"
    assert shown["assumptions"] == ["B stays as it is."]
    assert first["line"] == {"text": "→ 350", "kind": "result"}
    assert other["last_run"] is None and other["line"]["kind"] == "tested"
    assert step_of(state, "c3")["last_run"] is None and step_of(state, "j1")["last_run"] is None


def test_the_evidence_of_a_run_names_the_test_run_it_relied_on(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), reply("The total is 350.")])
    state = say(session, "A is 100 and B is 250")
    shown = step_of(state, "c1")["last_run"]
    assert shown["ts"].startswith("20")
    relied = session.conn.execute("SELECT * FROM test_runs WHERE id = ?", (shown["test_run"],)).fetchone()
    assert relied["module"] == "total" and relied["passed"] and relied["reason"] == "gate"
    assert events(session, "calc.run")[0]["test_run_id"] == shown["test_run"]


def test_inputs_of_the_steps_in_the_last_answer_are_used_and_show_their_saved_value(open_session):
    session = open_session([save("amount_a", 100), run("total", {"a": 100, "b": 250}), reply("The total is 350.")])
    state = valid(say(session, "A is 100 and B is 250"))
    assert state["inputs"]["in:amount_a"]["value"] == "100" and state["inputs"]["in:amount_b"]["value"] is None
    assert all(entry["used"] for entry in state["inputs"].values())


def test_a_reply_that_ran_nothing_leaves_the_last_answer_as_it_was(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), reply("The total is 350."), reply("Anything else?")])
    first = say(session, "A is 100 and B is 250")
    state = valid(say(session, "Thanks"))
    shown = step_of(state, "c1")["last_run"]
    assert shown["in_last_answer"] and shown["message"] == assistant(first)[-1]["id"]
    assert step_of(state, "c1")["line"]["kind"] == "result" and all(entry["used"] for entry in state["inputs"].values())


def test_a_newer_answer_replaces_the_steps_that_are_lit(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), reply("The total is 350."),
                            run("double", {"total": 350}), reply("Doubled: 700.")])
    say(session, "A is 100 and B is 250")
    state = valid(say(session, "Double it"))
    assert not step_of(state, "c1")["last_run"]["in_last_answer"] and step_of(state, "c2")["last_run"]["in_last_answer"]
    assert step_of(state, "c1")["line"]["kind"] == "tested"
    assert not any(entry["used"] for entry in state["inputs"].values())


def test_when_two_runs_produced_the_same_number_the_latest_of_this_turn_wins(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), run("double", {"total": 175}),
                            reply("Both come to 350.")])
    state = valid(say(session, "A is 100 and B is 250, or half of that, 175"))
    assert [(f["step"], f["run"]) for f in assistant(state)[-1]["figures"] if f["text"] == "350"] == [("c2", "r2")]


def test_a_run_of_this_turn_wins_over_an_earlier_turns(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), reply("The total is 350."),
                            run("total", {"a": 200, "b": 150}), reply("Still 350.")])
    say(session, "A is 100 and B is 250")
    state = valid(say(session, "And with A at 200 and B at 150?"))
    (figure,) = [f for f in assistant(state)[-1]["figures"] if f["text"] == "350"]
    assert (figure["step"], figure["run"]) == ("c1", "r2")


def test_a_number_a_later_step_was_only_given_leads_to_the_step_that_produced_it(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), reply("The total is 350."),
                            run("double", {"total": 350}), reply("From 350, doubled: 700.")])
    say(session, "A is 100 and B is 250")
    state = valid(say(session, "Double it"))
    by_text = {f["text"]: f for f in assistant(state)[-1]["figures"]}
    assert (by_text["350"]["step"], by_text["350"]["run"]) == ("c1", "r1")
    assert (by_text["700"]["step"], by_text["700"]["run"]) == ("c2", "r2")


def test_a_step_the_last_answer_cites_is_in_it_whenever_it_ran(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), reply("The total is 350."),
                            run("double", {"total": 350}), reply("From 350, doubled: 700."),
                            reply("The total was 350.")])
    say(session, "A is 100 and B is 250")
    say(session, "Double it")
    state = valid(say(session, "What was the total again?"))
    first, second = step_of(state, "c1"), step_of(state, "c2")
    assert first["last_run"]["in_last_answer"] and first["last_run"]["run"] == "r1"
    assert first["line"] == {"text": "→ 350", "kind": "result"}
    assert not second["last_run"]["in_last_answer"] and second["line"]["kind"] == "tested"
    assert all(entry["used"] for entry in state["inputs"].values())


def test_a_step_gives_its_recent_runs_newest_first_with_how_they_are_shown(open_session):
    script = [run("total", {"a": n, "b": "0.125"}) for n in range(1, 8)] + [reply("Done.")]
    state = valid(say(open_session(script), "Add 0.125 to each of one to seven"))
    runs = step_of(state, "c1")["runs"]
    assert [each["run"] for each in runs] == ["r7", "r6", "r5", "r4", "r3"]
    assert runs[0]["output"] == "7.125" and runs[0]["shown"] == {
        "inputs": [["a", {"text": "7"}], ["b", {"text": "0.125"}]], "output": {"text": "7.13"}}
    assert step_of(state, "c1")["last_run"]["shown"] == runs[0]["shown"]
    assert step_of(state, "c2")["runs"] == [] and step_of(state, "j1")["runs"] == []


def test_a_withheld_answer_still_shows_the_runs_it_was_made_from(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), reply("It is 999."), reply("Surely 999.")])
    state = valid(say(session, "A is 100 and B is 250"))
    shown = step_of(state, "c1")["last_run"]
    assert shown["in_last_answer"] and shown["message"] == assistant(state)[-1]["id"]
    assert assistant(state)[-1]["kind"] == "withheld"


def test_the_state_is_the_same_after_a_restart(open_session):
    session = open_session([save("amount_a", 100), run("total", {"a": 100, "b": 250}), reply("The total is 350.")])
    before = say(session, "A is 100 and B is 250")
    after = valid(open_session([]).state())
    assert step_of(after, "c1")["last_run"] == step_of(before, "c1")["last_run"]
    assert after["inputs"] == before["inputs"] and json.dumps(after["chat"]) == json.dumps(before["chat"])
