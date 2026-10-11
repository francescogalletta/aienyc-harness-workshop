"""SPEC 5.4 / ARCHITECTURE.md 12.7: chips on every message, built by the harness from its runs, never by the model;
`store_input` and `tell_analyst`."""
import json

from harness.answers import agent
from harness.answers.layer import run_chips
from layer3_helpers import assistant, events, reply, run, save, say
from state_shape import problems


def chips_of(state, n=-1):
    return assistant(state)[n]["chips"]


def shape(chips):
    return [(chip["kind"], chip["label"], chip["text"]) for chip in chips]


def test_every_message_has_chips_and_one_with_no_runs_has_none(open_session):
    session = open_session([reply("What is amount A?")])
    state = say(session, "How much is the total?")
    assert [message["chips"] for message in state["chat"]] == [[], []]
    assert problems(state) == []


def test_an_answer_gets_value_chips_then_result_chips_from_its_runs(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), run("double", {"total": 350}),
                            reply("The total is 350 and doubled 700.")])
    state = say(session, "A is 100 and B is 250")
    assert problems(state) == []
    chips = chips_of(state)
    assert shape(chips) == [("value", "A", "100"), ("value", "B", "250"),            # total 350 was made by run 1
                            ("result", "Total", "350"), ("result", "Double", "700")]
    assert all(chip["status"] is None for chip in chips)
    assert chips[0]["subject"] == {"kind": "value", "run": "r1", "key": "a", "value": "100", "input": None, "step": "c1"}
    assert chips[3]["subject"] == {"kind": "result", "run": "r2", "step": "c2", "value": "700"}


def test_a_value_chip_is_labelled_with_the_plan_input_and_points_at_it(open_session, tmp_path):
    session = open_session([run("double", {"total": 350}), reply("Doubled it is 700.")])
    path = tmp_path / "brief" / "domain_brief.json"
    plan = json.loads(path.read_text())
    plan["inputs"][1]["name"] = "TOTAL"                    # the id in:total, the key of the module's input
    path.write_text(json.dumps(plan))
    state = say(session, "The total is 350")
    value = chips_of(state)[0]
    assert (value["label"], value["text"], value["subject"]["input"], value["subject"]["step"]) == ("TOTAL", "350", "in:total", "c2")


def test_a_value_is_one_chip_however_often_it_is_given_and_today_is_none(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), run("total", {"a": 100, "b": 250}), reply("It is 350.")])
    chips = chips_of(say(session, "A is 100 and B is 250"))
    assert [chip["kind"] for chip in chips] == ["value", "value", "result", "result"]
    rows = {1: {"module": "none", "inputs": json.dumps({"day": "2026-10-10", "costs": [1, 2, 3], "n": 4}),
                "output": "5", "assumptions": "[]"}}
    found = run_chips([1], rows, {"steps": [], "inputs": {}}, session.conn, "2026-10-10")
    assert shape(found) == [("value", "Costs", "3 values"), ("value", "N", "4")]     # no step: no result chip


def test_an_assumption_is_one_chip_between_the_values_and_the_results(open_session):
    note = "The amounts are in euros."
    session = open_session([run("total", {"a": 100, "b": 250}, [note]), run("total", {"a": 100, "b": 250}, [note.lower()]),
                            reply("It is 350.")])
    chips = chips_of(say(session, "A is 100 and B is 250"))
    assert [chip["kind"] for chip in chips] == ["value", "value", "assumption", "result", "result"]
    assumption = chips[2]
    assert (assumption["label"], assumption["text"], assumption["status"]) == ("", note, None)
    assert assumption["subject"] == {"kind": "assumption", "run": "r1", "step": "c1", "text": note, "assumption": None}


def test_a_withheld_reply_keeps_the_chips_of_its_runs(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), reply("It is 999."), reply("It is 999.")])
    state = say(session, "A is 100 and B is 250")
    message = assistant(state)[-1]
    assert message["kind"] == "withheld"
    assert shape(message["chips"])[-1] == ("result", "Total", "350")


def test_chip_runs_of_a_join_notice_replace_its_runs(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), run("double", {"total": 350}), reply("Doubled it is 700.")])
    state = say(session, "A is 100 and B is 250")
    message = assistant(state)[-1]
    row = session.conn.execute("SELECT data FROM messages WHERE id = ?", (int(message["id"][1:]),)).fetchone()
    data = {**json.loads(row["data"]), "_chip_runs": [2]}
    session.conn.execute("UPDATE messages SET data = ? WHERE id = ?", (json.dumps(data), int(message["id"][1:])))
    session.conn.commit()
    assert shape(chips_of(session.state())) == [("value", "Total", "350"), ("result", "Double", "700")]


def test_store_input_is_what_save_input_writes_and_replaces_by_name(open_session):
    session = open_session([save("amount_a", 100), reply("Saved.")])
    say(session, "A is 100")
    agent.store_input(session.conn, "amount_a", "120", "on a branch", session.conversation)
    agent.store_input(session.conn, "amount_b", "5", "x", session.conversation)
    assert agent.saved_inputs(session.conn) == {"amount_a": {"value": "120", "note": "on a branch"},
                                                "amount_b": {"value": "5", "note": "x"}}
    assert events(session, "ask.input_saved")[0]["value"] == "100"          # the tool still records its event
    assert session.state()["inputs"]["in:amount_a"]["value"] == "120"


def test_tell_analyst_puts_a_line_with_the_next_message_once(open_session):
    session = open_session([reply("One?"), reply("Two?"), reply("Three?")])
    say(session, "first")
    agent.tell_analyst(session, "[harness] Decided on a branch: amount A is 150.")
    say(session, "second")
    say(session, "third")
    last = [call["messages"][-1]["content"] for call in session.script.calls]
    assert last[0] == "first"
    assert last[1].startswith("second") and "[harness] Decided on a branch: amount A is 150." in last[1]
    assert last[2] == "third"
