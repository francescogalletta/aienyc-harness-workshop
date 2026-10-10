"""SPEC 2.6 at step 4: replay of a scripted person who confirms, corrects, chooses and opens side threads, and
the expectation keys `decisions`, `marks`, `added` and `side_threads`."""
import time

import pytest

from harness import replay
from harness.model import ScriptedModel
from layer4_helpers import ASK, TOTAL, play, point_replay_at, reply, run, scenario, small_plan, world_folder

SIDE_PROMPT = "You help one person understand"


@pytest.fixture(autouse=True)
def scratch(monkeypatch, tmp_path):
    point_replay_at(monkeypatch, tmp_path)


@pytest.fixture
def example(tmp_path):
    return world_folder(tmp_path)


def test_the_expectations_come_from_the_layers_up_to_the_scenarios():
    assert "decisions" not in replay.expectations(3)
    assert {"decisions", "marks", "added", "side_threads"} <= set(replay.expectations(4))
    assert "challenges" not in replay.expectations(4)
    for value in ({"max": 0, "confirmed": 1, "corrected": 1}, {"min": 1}):
        assert replay.expectations(4)["marks"].validate(value) is None
    assert replay.expectations(4)["marks"].validate({"confirmed": -1})


def test_a_scenario_with_a_mistake_in_its_acts_or_expectations_is_refused_with_the_problem_named():
    for change, expected in [({"lines": [{"act": "side", "text": "hi", "step": "zz"}]}, "'zz' is not a step"),
                             ({"lines": [{"act": "side", "text": "hi", "reply": True, "step": "c1"}]}, "has its step already"),
                             ({"lines": [{"act": "confirm", "text": "x"}]}, "does not take 'text'"),
                             ({"lines": [{"act": "choose", "option": 0}]}, "option must be a whole number"),
                             ({"expect": {"decisions": [{"step": "zz"}]}}, "'zz' is not a step"),
                             ({"expect": {"marks": {"confirmed": -1}}}, "expect.marks")]:
        errors = replay.validate_scenario(scenario(**change), stem="s", brief=small_plan(), layers=4)
        assert any(expected in error for error in errors), (change, errors)
    for act in ("confirm", "correct", "choose", "side"):
        errors = replay.validate_scenario(scenario(layer=3, lines=[{"act": act, "text": "x", "option": 1}]),
                                          stem="s", brief=small_plan(), layers=4)
        assert any("needs layer 4 or above" in error for error in errors), act


def test_each_act_is_the_action_a_person_would_take_on_the_current_state():
    notice = {"id": "m4", "notice": {"status": "open"}}
    old = {"id": "m2", "notice": {"status": "confirmed"}}
    state = {"chat": [old, notice], "waiting": {"kind": "decision", "decision": "d3", "step": "j1"},
             "threads": [{"id": "t1", "kind": "side", "challenge": None},
                         {"id": "t5", "kind": "side", "challenge": None}]}
    act = replay._action_for
    assert act("hello", state) == ("say", {"text": "hello"})
    assert act({"act": "confirm"}, state) == ("confirm_assumptions", {"message": "m4"})
    assert act({"act": "correct", "text": "no"}, state) == ("say", {"text": "no", "notice": "m4"})
    settled = {**state, "chat": [old]}                      # "Change it" is there under a confirmed notice too
    assert act({"act": "correct", "text": "no"}, settled) == ("say", {"text": "no", "notice": "m2"})
    assert act({"act": "choose", "option": 2}, state) == ("choose", {"decision": "d3", "option": 2})
    assert act({"act": "side", "text": "why"}, state) == ("side", {"text": "why"})
    assert act({"act": "side", "text": "why", "step": "c1"}, state) == ("side", {"text": "why", "step": "c1"})
    assert act({"act": "side", "text": "more", "reply": True}, state) == ("side", {"text": "more", "thread": "t5"})
    quiet = {"chat": [old], "waiting": None, "threads": []}
    for line in ({"act": "confirm"}, {"act": "choose", "option": 1}, {"act": "side", "text": "x", "reply": True}):
        with pytest.raises(replay.ReplayError):
            act(line, quiet)
    with pytest.raises(replay.ReplayError):
        act({"act": "confirm"}, settled)                    # nothing open to confirm
    with pytest.raises(replay.ReplayError):
        act({"act": "correct", "text": "no"}, {"chat": [], "waiting": None, "threads": []})


def test_a_line_the_harness_refuses_stops_the_scenario_but_the_checks_still_run(example):
    found = scenario(lines=[ASK, {"act": "confirm"}])
    result = play(found, example, TOTAL)
    assert not result["passed"] and "no open notice" in result["error"]
    assert result["checks"] and result["checks"][0]["passed"]           # what happened before is still reported


def test_a_confirmation_clears_the_mark_and_a_correction_runs_the_answer_again(example):
    script = [run("total", {"a": 10, "b": 20}, assumptions=["Amount B stays as it is."]), reply("The total is 30."),
              run("total", {"a": 10, "b": 25}, assumptions=["Amount A stays at 10."]), reply("The total is 35.")]
    found = scenario(lines=[ASK, {"act": "confirm"}, {"act": "correct", "text": "No, amount B is 25, not 20."}],
                     expect={"runs": [{"module": "total", "inputs": {"a": "10", "b": "25"}}],
                             "marks": {"min": 1, "max": 1, "corrected": 1, "confirmed": 1}})
    result = play(found, example, script)
    assert result["passed"], result


def test_a_decision_is_answered_by_option_and_shows_its_figures(example):
    script = [run("total", {"a": 10, "b": 20}),
              {"tool_calls": [{"name": "ask_decision", "arguments": {
                  "step": "j1", "question": "The total is 30. Is it enough?", "options": ["Yes", "No"], "runs": [1]}}]},
              reply("Noted.")]
    found = scenario(lines=[ASK, {"act": "choose", "option": 2}], expect={
        "decisions": [{"step": "j1", "choice": "2"}], "shown": ["30"]})
    result = play(found, example, script)
    assert result["passed"], result


def test_a_side_thread_can_be_opened_while_the_main_answer_is_still_being_worked_out(example):
    finished = []

    class Staged:
        def __init__(self):
            self.main = ScriptedModel(TOTAL)

        def complete(self, *, system, messages, tools=()):
            if system.startswith(SIDE_PROMPT):
                finished.append("side")
                return ScriptedModel([{"text": "A total is the sum of the amounts."}]).complete(
                    system=system, messages=messages)
            time.sleep(1.0)
            finished.append("main")
            return self.main.complete(system=system, messages=messages, tools=tools)

    found = scenario(lines=[ASK, {"act": "side", "text": "What is a total?", "settle": False}],
                     expect={"side_threads": 1, "runs": [{"module": "total"}]})
    result = replay.run_scenario(found, example_dir=example, model_factory=Staged, write=lambda text: None)
    assert result["passed"], result
    assert finished[0] == "side"                  # answered while the main lane was still busy
