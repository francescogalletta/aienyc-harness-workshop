"""SPEC 6.3: a calculation missing from the plan is built at once, without asking. The person is told in the
chat, and a new calculation is a step marked "not in the plan"."""
import json
from pathlib import Path

from harness.calc.notes import list_notes
from harness.needs_you.layer import LAYER
from layer4_helpers import (assistant, build_turns, call, chat_of, events, number, problems, reply, request,
                            run, say, step_of, tax_turns, triple_turns)

ANALYST = Path(__file__).resolve().parents[2] / "harness" / "needs_you" / "analyst.md"
TOTAL_SPEC = {"name": "total", "description": "adds two amounts", "method": "arithmetic", "formula": "a + b",
              "inputs": [number("a"), number("b")], "output": {"type": "number", "description": "the total"}}
TOTAL_EXAMPLES = [{"inputs": {"a": str(a), "b": str(b)}, "expected": str(a + b), "working": f"{a} + {b} = {a + b}"}
                  for a, b in ((1, 2), (0, 5), (40, 60))]
TOTAL_CODE = ("def calculate(a, b):\n    return a + b\n",
              "from decimal import Decimal\nfrom module import calculate\n\n\ndef test_adds():\n"
              "    assert calculate(a=Decimal('1'), b=Decimal('2')) == Decimal('3')\n")


def test_a_calculation_the_plan_has_no_step_for_is_built_without_asking(open_session):
    session = open_session([request("new", name="Triple an amount"), *triple_turns(),
                            run("triple", {"amount": 7}), reply("Three times 7 is 21.")])
    state = say(session, "What is three times 7?")
    assert state["waiting"] is None and not session.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    step = step_of(state, "added_1")
    assert (step["in_plan"], step["name"], step["kind"], step["build"]["status"]) == (
        False, "Triple an amount", "calculation", "built")
    assert state["steps"][-1]["id"] == "added_1" and step["number"] == len(state["steps"])
    *_, told = [m for m in chat_of(state, "harness") if m["step"] == "added_1"]
    assert "Triple an amount" in told["text"] and told["kind"] == "text"
    assert int(told["id"][1:]) < int(assistant(state)[-1]["id"][1:])          # told before the answer
    result = json.loads(session.script.calls[-2]["messages"][-1]["content"])
    assert (result["outcome"], result["module"], result["spec"]["step_id"]) == ("built", "triple", "added_1")
    (figure,) = [f for f in assistant(state)[-1]["figures"] if f["text"] == "21"]
    assert figure["step"] == "added_1"
    assert '"id": "added_1"' in session.script.calls[-1]["system"]
    assert events(session, "you.module_requested")[0]["outcome"] == "built"
    assert problems(state, strict=True) == []


def test_a_step_of_the_plan_without_a_working_module_is_built_and_the_person_is_told(open_session):
    session = open_session([request("step", target="c3", works_out="tax on the double", gives="the tax",
                                    formula="double x 2"), *tax_turns(), reply("The tax step is ready.")])
    state = say(session, "Can you work out the tax?")
    assert step_of(state, "c3")["build"]["status"] == "built" and step_of(state, "c3")["in_plan"]
    assert not [s for s in state["steps"] if s["id"].startswith("added_")]
    *_, told = chat_of(state, "harness")
    assert told["step"] == "c3" and "Tax" in told["text"]
    assert problems(state, strict=True) == []


def test_a_build_that_fails_is_told_and_the_analyst_says_what_cannot_be_answered(open_session):
    bad_spec = call("propose_spec", name="triple")
    session = open_session([request("new"), bad_spec, bad_spec, bad_spec, reply("I could not build that.")])
    state = say(session, "What is three times 7?")
    step = step_of(state, "added_1")
    assert step["build"]["status"] == "not_built" and step["build"]["reason"] and step["needs_you"]
    *_, told = chat_of(state, "harness")
    assert told["step"] == "added_1" and "could not" in told["text"]
    assert json.loads(session.script.calls[-1]["messages"][-1]["content"])["outcome"] == "not_built"
    assert events(session, "you.module_requested")[0]["outcome"] == "not_built"


def test_requests_that_do_not_meet_the_checks_are_sent_back_and_build_nothing(open_session):
    session = open_session([request("step", target="zz"), request("step", target="c1"), request("bogus"),
                            request("new", why=" "), request("new", works_out="what happens in 31 days"),
                            request("replace", target="nothing"), reply("I could not.")])
    state = say(session, "What is three times 7?")
    assert chat_of(state, "harness") == [] and not [s for s in state["steps"] if not s["in_plan"]]
    assert len(events(session, "you.request_refused")) == 5 and events(session, "ask.correction")[0]["reason"] == "request_module"
    assert not events(session, "you.module_requested")


def test_at_most_two_builds_are_asked_for_by_one_message(open_session):
    second = call("request_module", case="new", name="Tax on the double", works_out="tax on the double",
                  from_what="the double", gives="the tax", formula="double x 2", why="the person asked")
    session = open_session([request("new"), *triple_turns(), second, *tax_turns(), request("new"),
                            reply("That is all I can build now.")])
    state = say(session, "What is three times 7, and the tax?")
    assert [s["id"] for s in state["steps"] if not s["in_plan"]] == ["added_1", "added_2"]
    assert len(events(session, "you.module_requested")) == 2 and len(events(session, "you.request_refused")) == 1


def test_a_module_that_does_not_fit_is_built_again_and_the_words_are_kept_as_a_note(open_session):
    session = open_session([request("replace", target="total", works_out="the total of a list of amounts",
                                    from_what="a list of costs", gives="the total", formula="a + b"),
                            *build_turns(TOTAL_SPEC, TOTAL_EXAMPLES, TOTAL_CODE), reply("The total module is rebuilt.")])
    state = say(session, "I only have a list of costs")
    assert step_of(state, "c1")["build"]["status"] == "built" and step_of(state, "c1")["build"]["module"] == "total"
    assert any("list of costs" in note["text"] and note["step"] == "c1" for note in list_notes(session.conn))
    assert events(session, "build.started")[-1]["rebuild"] == "total"
    *_, told = chat_of(state, "harness")
    assert told["step"] == "c1"


def test_a_new_step_without_a_short_name_is_named_from_what_it_works_out(open_session):
    long_text = "the amount that is three times the amount of the first payment less the deposit already paid"
    session = open_session([request("new", works_out=long_text), *triple_turns(), reply("Done.")])
    state = say(session, "Please work that out")
    name = step_of(state, "added_1")["name"]
    assert 0 < len(name) <= 61 and long_text.startswith(name.rstrip("…").rstrip())


def test_the_build_is_reported_as_activity_on_the_new_step_while_it_runs(open_session):
    seen = []
    session = open_session([request("new"), *triple_turns(), reply("Done.")])
    original = session.script.complete

    def watching(**sent):
        seen.append(session.state()["activity"])
        return original(**sent)

    session.script.complete = watching
    say(session, "Please work that out")
    building = [entry for entry in seen if entry and entry[0]["what"] == "build"]
    assert len(building) == 4 and all(entry[0]["step"] == "added_1" for entry in building)


def test_the_analyst_is_offered_the_layers_tools_and_its_part_of_the_prompt(open_session):
    session = open_session([reply("Hello")])
    state = say(session, "Hello")
    first = session.script.calls[0]
    assert {spec.name for spec in first["tools"]} >= {"ask_decision", "request_module", "run_module"}
    assert ANALYST.read_text(encoding="utf-8").strip() in first["system"].split("## What you know")[0]
    for step in state["steps"]:
        assert isinstance(step["unconfirmed"], list) and "calls" in step
    assert state["threads"] == [] and all(m["decision"] is None and m["notice"] is None for m in state["chat"])
    assert problems(state, strict=True) == []


def test_the_expectations_for_marks_and_added_steps(open_session):
    session = open_session([request("new"), *triple_turns(), run("triple", {"amount": 7}, ["Seven is meant."]),
                            reply("Three times 7 is 21.")])
    say(session, "What is three times 7?")
    marks, added = LAYER.expects["marks"], LAYER.expects["added"]
    assert marks.validate({"min": 1, "max": 1}) is None and marks.validate({"lots": 1}) and marks.validate({})
    assert marks.check({"min": 1, "max": 1}, session)["passed"] and not marks.check({"max": 0}, session)["passed"]
    assert added.validate(1) is None and added.validate("1") and added.validate(-1)
    assert added.check(1, session)["passed"] and not added.check(2, session)["passed"]


def test_the_chat_says_a_build_has_begun_before_it_starts(open_session):
    from harness import db
    session = open_session([request("new", name="Triple an amount"), *triple_turns(),
                            run("triple", {"amount": 7}), reply("Three times 7 is 21.")])
    state = say(session, "What is three times 7?")
    first, *_ = [m for m in chat_of(state, "harness") if m["step"] == "added_1"]
    assert "Triple an amount" in first["text"]
    told = next(row for row in db.list_events(session.conn, kind="core.message")
                if json.loads(row["payload"])["id"] == first["id"])
    started = next(row for row in db.list_events(session.conn, kind="build.started"))
    assert told["id"] < started["id"]


def test_an_added_step_is_connected_to_what_fed_its_run_or_placed_near_the_step_that_asked(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), request("new", name="Triple an amount"),
                            *triple_turns(), run("triple", {"amount": 350}), reply("Three times 350 is 1,050.")])
    state = say(session, "A is 100 and B is 250. What is three times the total?")
    step = step_of(state, "added_1")
    assert step["needs"] == ["c1"] and step["inputs"] == [] and step["near"] == "c1"
    assert {"from": "c1", "to": "added_1"} in state["edges"]
    assert problems(state, strict=True) == []


def test_an_added_step_takes_a_saved_input_as_a_pill(open_session):
    session = open_session([call("save_input", name="amount_a", value="7", note="said"), request("new"),
                            *triple_turns(), run("triple", {"amount": 7}), reply("Three times 7 is 21.")])
    state = say(session, "Amount A is 7. What is three times it?", step="c2")
    step = step_of(state, "added_1")
    assert step["needs"] == ["in:amount_a"] and step["inputs"] == ["in:amount_a"] and step["near"] == "c2"
    assert "added_1" in state["inputs"]["in:amount_a"]["steps"] and state["inputs"]["in:amount_a"]["used"]
    assert not [edge for edge in state["edges"] if edge["to"] == "added_1"]


def test_an_added_step_nothing_fed_stays_unconnected(open_session):
    session = open_session([request("new"), *triple_turns(), run("triple", {"amount": 7}), reply("It is 21.")])
    state = say(session, "What is three times 7?")
    step = step_of(state, "added_1")
    assert step["needs"] == [] and step["near"] is None
    assert events(session, "you.module_requested")[0]["near"] is None
