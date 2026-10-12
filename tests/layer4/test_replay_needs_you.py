"""SPEC 2.6 at layer 4: replay of a scripted person who confirms, corrects, chooses and opens side threads, and
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


# --- The acts of the decision history: branch, accept, decline, close (SPEC 2.6) ---

CHIP = {"kind": "value", "label": "A", "text": "10"}
JOIN_LINES = [ASK, {"act": "branch", "chip": CHIP, "text": "Make it: a is 15, not 10."}, {"act": "accept"}]


def test_the_branch_acts_are_checked_when_the_scenario_is_read():
    for change, expected in [({"lines": [{"act": "branch", "text": "why", "chip": {"kind": "number"}}]}, "chip kind"),
                             ({"lines": [{"act": "branch", "text": "why", "chip": {"kind": "value", "size": 1}}]},
                              "does not take 'size'"),
                             ({"lines": [{"act": "branch", "text": "why", "chip": "A"}]}, "chip must be an object"),
                             ({"lines": [{"act": "branch", "text": "why", "step": "c1", "chip": CHIP}]}, "not both"),
                             ({"lines": [{"act": "branch", "step": "c1"}]}, "needs 'text'"),
                             ({"lines": [{"act": "branch", "text": "why", "step": "zz"}]}, "'zz' is not a step"),
                             ({"lines": [{"act": "accept", "text": "yes"}]}, "does not take 'text'"),
                             ({"expect": {"branches": {"joined": -1}}}, "expect.branches"),
                             ({"expect": {"branches": {"nodes": ["nothing"]}}}, "expect.branches")]:
        errors = replay.validate_scenario(scenario(**change), stem="s", brief=small_plan(), layers=4)
        assert any(expected in error for error in errors), (change, errors)
    for act in ("branch", "accept", "decline", "close"):
        errors = replay.validate_scenario(scenario(layer=3, lines=[{"act": act, "text": "x"}]),
                                          stem="s", brief=small_plan(), layers=4)
        assert any("needs layer 4 or above" in error for error in errors), act
    good = scenario(lines=[ASK, {"act": "branch", "chip": CHIP, "text": "Why?"}, {"act": "decline"},
                           {"act": "branch", "step": "c1", "text": "What is a total?"}, {"act": "close"}],
                    expect={"branches": {"joined": 0, "dead": 2}})
    assert replay.validate_scenario(good, stem="s", brief=small_plan(), layers=4) == []


def test_the_branch_acts_are_resolved_from_the_state_never_from_a_fixed_id():
    act = replay._action_for
    older = {"id": "m1", "chips": [{"kind": "value", "label": "A", "text": "10", "subject": {"kind": "value", "run": "r1"}}]}
    newer = {"id": "m3", "chips": [{"kind": "value", "label": "A", "text": "10", "subject": {"kind": "value", "run": "r3"}},
                                   {"kind": "result", "label": "Total", "text": "30", "subject": {"kind": "result"}}]}
    state = {"chat": [older, newer], "threads": [
        {"id": "t2", "kind": "review", "outcome": "open", "proposal": None},
        {"id": "t9", "kind": "side", "outcome": "open", "proposal": {"id": "p3", "status": "pending"}},
        {"id": "t10", "kind": "side", "outcome": "dead", "proposal": {"id": "p4", "status": "declined"}},
        {"id": "t11", "kind": "side", "outcome": "open", "proposal": {"id": "p5", "status": "pending"}}]}
    chip = {"kind": "value", "label": " a ", "text": "10"}                        # case and spacing do not matter
    assert act({"act": "branch", "chip": chip, "text": "No"}, state) == (
        "side", {"text": "No", "subject": {"kind": "value", "run": "r3"}})        # the newest chip that matches
    assert act({"act": "branch", "chip": {"kind": "result"}, "text": "No"}, state)[1]["subject"] == {"kind": "result"}
    assert act({"act": "branch", "step": "c1", "text": "Why"}, state) == ("side", {"text": "Why", "step": "c1"})
    assert act({"act": "branch", "text": "Why"}, state) == ("side", {"text": "Why"})
    assert act({"act": "accept"}, state) == ("accept_proposal", {"proposal": "p5"})     # p5 is ahead of p3, though t9 < t11
    assert act({"act": "decline"}, state) == ("decline_proposal", {"proposal": "p5"})
    assert act({"act": "close"}, state) == ("close_branch", {"thread": "t11"})         # t10 is dead, t2 is a review
    for line, state in [({"act": "branch", "chip": {"kind": "value", "label": "B"}, "text": "No"}, state),
                        ({"act": "branch", "chip": {"kind": "decision"}, "text": "No"}, state),
                        ({"act": "accept"}, {"threads": [{"id": "t1", "kind": "side", "outcome": "open", "proposal": None}]}),
                        ({"act": "decline"}, {"threads": []}),
                        ({"act": "close"}, {"threads": [{"id": "t1", "kind": "side", "outcome": "dead", "proposal": None}]})]:
        with pytest.raises(replay.ReplayError):
            act(line, state)


class Routed:
    """The side assistant's calls go to `side`, every other call to `main`."""

    def __init__(self, main, side):
        self.main, self.side = ScriptedModel(list(main)), ScriptedModel(list(side))

    def complete(self, *, system, messages, tools=()):
        target = self.side if system.startswith(SIDE_PROMPT) else self.main
        return target.complete(system=system, messages=messages, tools=tools)


def play_routed(found, example, main, side):
    return replay.run_scenario(found, example_dir=example, model_factory=lambda: Routed(main, side),
                               write=lambda text: None)


PROPOSE = {"tool_calls": [{"name": "propose_change", "arguments": {
    "kind": "value", "input": "a", "value": "15", "step": "", "words": "a is 15, not 10"}}]}


def test_a_branch_from_a_chip_is_accepted_and_joins_the_trunk(example):
    found = scenario(lines=JOIN_LINES, expect={
        "runs": [{"module": "total", "inputs": {"a": "10", "b": "20"}}, {"module": "total", "inputs": {"a": "15", "b": "20"}}],
        "branches": {"joined": 1, "dead": 0, "nodes": ["value"]}})
    result = play_routed(found, example, TOTAL, [PROPOSE, reply("I proposed 15 for a.")])
    assert result["passed"], result


def test_a_declined_proposal_leaves_the_branch_dead_and_runs_nothing_again(example):
    found = scenario(lines=[ASK, {"act": "branch", "chip": CHIP, "text": "Make it: a is 15, not 10."}, {"act": "decline"}],
                     expect={"branches": {"joined": 0, "dead": 1}, "side_threads": 1})
    result = play_routed(found, example, TOTAL, [PROPOSE, reply("I proposed 15 for a.")])
    assert result["passed"], result
    assert [check["passed"] for check in result["checks"]] == [True, True]


def test_a_branch_on_a_step_that_is_closed_is_dead_with_no_decision(example):
    found = scenario(lines=[{"act": "branch", "step": "c1", "text": "What is a total?"}, {"act": "close"}],
                     expect={"side_threads": 1, "branches": {"joined": 0, "dead": 1, "nodes": []}})
    result = play_routed(found, example, [], [reply("A total is the sum of the amounts.")])
    assert result["passed"], result


def test_an_act_with_nothing_to_act_on_stops_the_scenario_with_that_reason(example):
    for lines, reason in [([ASK, {"act": "accept"}], "no pending proposal"),
                          ([ASK, {"act": "close"}], "no open side branch"),
                          ([ASK, {"act": "branch", "chip": {"kind": "value", "label": "Nothing"}, "text": "Why?"}],
                           "no value chip")]:
        result = play_routed(scenario(lines=lines), example, TOTAL, [])
        assert not result["passed"] and reason in result["error"], (lines, result["error"])
