"""SPEC 2.6: scenarios, their validation, and replay of a scripted person on a Session.

Replay is shared code: it acts on what the layers register, so these tests run scenarios at layers 2 to 5 of
the whole tree with a scripted model, on a small example written under `tmp_path`.
"""
import argparse
import json
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for layer in ("layer2", "layer3", "layer5"):
    sys.path.append(str(ROOT / "tests" / layer))

from layer2_helpers import double_turns, small_plan as plan_c1_c2  # noqa: E402
from layer3_helpers import MODULES, reply, run, small_plan, write_world  # noqa: E402
from layer5_helpers import SplitModel, challenge, report  # noqa: E402

from harness import replay  # noqa: E402
from harness.model import ScriptedModel  # noqa: E402

ASK = "what is 10 plus 20?"
SIDE_PROMPT = "You help one person understand"
SEEDED = sorted((ROOT / "examples").glob("*/scenarios/*.json"))


@pytest.fixture(autouse=True)
def scratch(monkeypatch, tmp_path):
    """Replay's scratch folders and the researcher go to the test's own place."""
    monkeypatch.setattr(replay, "REPLAY_DIR", tmp_path / "replay")
    monkeypatch.setenv("HARNESS_RESEARCHER", "reference")
    monkeypatch.setenv("HARNESS_REFERENCE", str(ROOT / "reference" / "terms.json"))


@pytest.fixture
def example(tmp_path):
    """A small example folder: the layer 3 test world (c1, c2 with modules, c3 without, j1 a judgment)."""
    folder = tmp_path / "ex"
    write_world(folder)
    return folder


def scenario(layer=4, **more):
    found = {"name": "s", "layer": layer, "kind": "ask", "lines": [ASK],
             "expect": {"runs": [{"module": "total", "inputs": {"a": "10", "b": "20"}}]}}
    found.update(more)
    return found


def play(found, example, script=(), **options):
    model = ScriptedModel(list(script))
    options.setdefault("write", lambda text: None)
    result = replay.run_scenario(found, example_dir=example, model_factory=lambda: model, **options)
    result["model"] = model
    return result


TOTAL = [run("total", {"a": 10, "b": 20}), reply("The total is 30.")]


# --- The scenario format ---

def test_every_seeded_scenario_validates_and_together_they_exercise_every_layer():
    layers = set()
    for path in SEEDED:
        value = json.loads(path.read_text(encoding="utf-8"))
        brief = replay.read_brief(path.parents[1])
        assert replay.validate_scenario(value, stem=path.stem, brief=brief, layers=5) == [], path
        layers.add(value["layer"])
    assert {path.parts[-3] for path in SEEDED} == {"wedding", "moving"}
    assert layers >= {2, 3, 4, 5}


MISTAKES = [
    ({"extra": 1}, "unknown key: extra"),
    ({"name": "other"}, "name must be"),
    ({"layer": 6}, "layer must be"),
    ({"kind": "chat"}, "kind must be"),
    ({"lines": []}, "at least one line"),
    ({"kind": "build", "today": "2027-01-15"}, "today is only for ask"),
    ({"today": "15 January"}, "today must be"),
    ({"lines": [{"act": "wave"}]}, "unknown act 'wave'"),
    ({"lines": [{"act": "choose"}]}, "needs 'option'"),
    ({"lines": [{"act": "use"}]}, "needs layer 5"),
    ({"lines": [{"act": "side", "text": "hi", "step": "zz"}]}, "'zz' is not a step"),
    ({"lines": [{"act": "build", "text": "now"}]}, "does not take 'text'"),
    ({"without": ["j1"]}, "not a calculation step"),
    ({"expect": {}}, "at least one expectation"),
    ({"expect": {"challenges": {"min": 1}}}, "unknown key: challenges"),
    ({"expect": {"shown": ["9"]}}, "expect.shown"),
    ({"expect": {"decisions": [{"step": "zz"}]}}, "'zz' is not a step"),
]


def test_a_scenario_with_a_mistake_is_refused_with_the_problem_named():
    for change, expected in MISTAKES:
        errors = replay.validate_scenario(scenario(**change), stem="s", brief=small_plan(), layers=5)
        assert any(expected in error for error in errors), (change, errors)


def test_the_expectations_come_from_the_layers_up_to_the_scenarios():
    assert "steps" not in replay.expectations(1) and "steps" in replay.expectations(2)
    assert "runs" in replay.expectations(3) and "decisions" not in replay.expectations(3)
    assert {"decisions", "marks", "added", "side_threads"} <= set(replay.expectations(4))
    assert "challenges" in replay.expectations(5)
    for value in ({"max": 0, "confirmed": 1, "corrected": 1}, {"min": 1}):
        assert replay.expectations(4)["marks"].validate(value) is None
    assert replay.expectations(4)["marks"].validate({"confirmed": -1})
    assert replay.expectations(5)["challenges"].validate({"min": 2, "used": 1, "dismissed": 1}) is None
    assert replay.expectations(5)["challenges"].validate({"used": "1"})


def test_loading_skips_layers_above_the_enabled_ones_and_names_the_file_of_a_problem(example, monkeypatch):
    folder = example / "scenarios"
    folder.mkdir()
    (folder / "a.json").write_text(json.dumps(scenario(layer=2, name="a", kind="build", lines=[],
                                                       expect={"steps": {"c1": "kept"}})), encoding="utf-8")
    (folder / "b.json").write_text(json.dumps(scenario(layer=4, name="b")), encoding="utf-8")
    monkeypatch.setenv("HARNESS_LAYERS", "3")
    found, skipped = replay.load_scenarios(example)
    assert [each["name"] for each in found] == ["a"] and skipped == [{"name": "b", "layer": 4}]
    (folder / "a.json").write_text(json.dumps(scenario(layer=3, name="a", lines=[{"act": "wave"}])), encoding="utf-8")
    with pytest.raises(ValueError, match=r"a\.json: lines: line 1: unknown act"):
        replay.load_scenarios(example)
    with pytest.raises(ValueError, match="There is no scenario 'zzz'.*a, b"):
        replay.load_scenarios(example, "zzz")


def test_each_act_is_the_action_a_person_would_take_on_the_current_state():
    notice = {"id": "m4", "notice": {"status": "open"}}
    old = {"id": "m2", "notice": {"status": "confirmed"}}
    state = {"chat": [old, notice], "waiting": {"kind": "decision", "decision": "d3", "step": "j1"},
             "threads": [{"id": "t1", "kind": "side", "challenge": None},
                         {"id": "t2", "kind": "review", "challenge": {"id": "c5", "kind": "question", "status": "open"}},
                         {"id": "t3", "kind": "review", "challenge": {"id": "c7", "kind": "challenge", "status": "open"}},
                         {"id": "t4", "kind": "review", "challenge": {"id": "c6", "kind": "challenge", "status": "used"}},
                         {"id": "t5", "kind": "side", "challenge": None}]}
    act = replay._action_for
    assert act("hello", state) == ("say", {"text": "hello"})
    assert act({"act": "confirm"}, state) == ("confirm_assumptions", {"message": "m4"})
    assert act({"act": "correct", "text": "no"}, state) == ("say", {"text": "no", "notice": "m4"})
    settled = {**state, "chat": [old]}                      # "Change it" is there under a confirmed notice too
    assert act({"act": "correct", "text": "no"}, settled) == ("say", {"text": "no", "notice": "m2"})
    assert act({"act": "choose", "option": 2}, state) == ("choose", {"decision": "d3", "option": 2})
    assert act({"act": "side", "text": "why"}, state) == ("side", {"text": "why"})
    assert act({"act": "side", "text": "more", "reply": True}, state) == ("side", {"text": "more", "thread": "t5"})
    assert act({"act": "use"}, state) == ("use_challenge", {"challenge": "c7"})            # a question cannot be used
    assert act({"act": "dismiss", "index": 2}, state) == ("dismiss_challenge", {"challenge": "c7"})
    for line in ({"act": "use", "index": 2}, {"act": "dismiss", "index": 3}):
        with pytest.raises(replay.ReplayError):
            act(line, state)
    quiet = {"chat": [old], "waiting": None, "threads": []}
    for line in ({"act": "confirm"}, {"act": "choose", "option": 1}, {"act": "side", "text": "x", "reply": True}):
        with pytest.raises(replay.ReplayError):
            act(line, quiet)
    with pytest.raises(replay.ReplayError):
        act({"act": "confirm"}, settled)                    # nothing open to confirm


# --- Playing a scenario ---

def test_a_scenario_is_played_at_its_layer_and_day_and_every_expectation_gives_a_line(example):
    seen = {}

    def factory():
        seen.update({name: os.environ.get(name) for name in ("HARNESS_LAYERS", "HARNESS_REVIEW")})
        seen["db"] = os.environ["HARNESS_DB"]
        return model

    model = ScriptedModel(TOTAL)
    found = scenario(layer=3, today="2027-01-15", expect={
        "runs": [{"module": "total", "inputs": {"a": "10", "b": "20"}}], "shown": ["30"], "max_withheld": 0})
    before = os.environ.get("HARNESS_LAYERS")
    result = replay.run_scenario(found, example_dir=example, model_factory=factory, write=lambda text: None)
    assert result["passed"] and result["error"] is None
    assert [check["passed"] for check in result["checks"]] == [True, True, True]
    assert all(check["what"] and check["seen"] for check in result["checks"])
    assert seen["HARNESS_LAYERS"] == "3" and seen["HARNESS_REVIEW"] == "off"
    assert "2027-01-15" in model.calls[0]["system"]
    assert os.environ.get("HARNESS_LAYERS") == before and os.environ.get("HARNESS_DB") != seen["db"]
    assert not Path(seen["db"]).parent.exists() and result["folder"] is None          # the scratch copy is gone


def test_a_failed_expectation_fails_the_scenario_and_says_what_was_seen(example):
    found = scenario(layer=3, expect={"runs": [{"module": "double"}], "max_withheld": 0})
    result = play(found, example, TOTAL)
    assert not result["passed"] and result["error"] is None
    assert [check["passed"] for check in result["checks"]] == [False, True]
    assert "total" in result["checks"][0]["seen"]


def test_keep_leaves_the_scratch_copy_with_the_events_of_the_run(example):
    result = play(scenario(layer=3), example, TOTAL, keep=True)
    folder = Path(result["folder"])
    assert (folder / "brief" / "domain_brief.json").is_file() and (folder / "modules" / "total").is_dir()
    kinds = [row[0] for row in sqlite3.connect(folder / "harness.db").execute("SELECT kind FROM events")]
    assert kinds.count("replay.scenario") == 1 and kinds.count("replay.checked") == 1


def test_a_build_scenario_builds_what_was_left_out_and_keeps_the_rest(tmp_path):
    folder = tmp_path / "build"
    (folder / "brief").mkdir(parents=True)
    (folder / "brief" / "domain_brief.json").write_text(json.dumps(plan_c1_c2()), encoding="utf-8")
    for name, files in MODULES.items():
        (folder / "modules" / name).mkdir(parents=True)
        for file, text in files.items():
            (folder / "modules" / name / file).write_text(text, encoding="utf-8")
    found = {"name": "b", "layer": 2, "kind": "build", "without": ["c2"], "lines": [],
             "expect": {"steps": {"c2": "built", "c1": "kept"}}}
    assert replay.validate_scenario(found, stem="b", brief=plan_c1_c2(), layers=5) == []
    result = play(found, folder, double_turns(), keep=True)
    assert result["passed"], result
    assert (Path(result["folder"]) / "modules" / "double").is_dir()
    assert len(list((folder / "modules").iterdir())) == 2                           # the example itself is not written


def test_a_line_the_harness_refuses_stops_the_scenario_but_the_checks_still_run(example):
    found = scenario(lines=[ASK, {"act": "confirm"}])
    result = play(found, example, TOTAL)
    assert not result["passed"] and "no open notice" in result["error"]
    assert result["checks"] and result["checks"][0]["passed"]           # what happened before is still reported


def test_a_lane_that_does_not_finish_is_reported_as_stuck(example):
    class Slow:
        def complete(self, **_):
            time.sleep(2.5)
            return ScriptedModel([{"text": "late"}]).complete(system="", messages=[])

    result = replay.run_scenario(scenario(layer=3), example_dir=example, model_factory=Slow, timeout=0.5,
                                 write=lambda text: None)
    assert not result["passed"] and "still working" in result["error"]


def test_a_failed_job_is_reported_not_swallowed(example):
    result = play(scenario(layer=3), example, [])
    assert not result["passed"] and result["error"].startswith("a job failed")


# --- The scripted person at layers 4 and 5 ---

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


def test_a_challenge_is_used_and_another_dismissed(example):
    model = SplitModel(analyst=[reply("Understood.")], reviewer=[report(
        challenge(step="c1", title="First"), challenge(step="c2", title="Second"))])
    found = scenario(layer=5, review=True, lines=[{"act": "use"}, {"act": "dismiss"}],
                     expect={"challenges": {"min": 2, "used": 1, "dismissed": 1}})
    result = replay.run_scenario(found, example_dir=example, model_factory=lambda: model, write=lambda text: None)
    assert result["passed"], result


# --- The command ---

def command(example_name, *, scenario_name=None, keep=False):
    return replay.replay_command(argparse.Namespace(example=example_name, scenario=scenario_name, keep=keep))


def test_the_command_names_what_it_cannot_find(monkeypatch, tmp_path, capsys):
    (tmp_path / "examples" / "ex" / "scenarios").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    assert command("nope") == 1 and "no example called 'nope'" in capsys.readouterr().err
    assert command("ex", scenario_name="zzz") == 1 and "no scenario 'zzz'" in capsys.readouterr().err
    assert command("ex") == 1 and "no scenarios" in capsys.readouterr().err


def test_the_command_prints_a_line_per_expectation_and_exits_by_the_result(monkeypatch, tmp_path, capsys):
    folder = tmp_path / "examples" / "ex"
    write_world(folder)
    (folder / "scenarios").mkdir()
    good = scenario(layer=3, name="good", expect={"runs": [{"module": "total"}], "shown": ["30"]})
    (folder / "scenarios" / "good.json").write_text(json.dumps(good), encoding="utf-8")
    later = scenario(layer=4, name="later")
    (folder / "scenarios" / "later.json").write_text(json.dumps(later), encoding="utf-8")
    script = tmp_path / "script.json"
    script.write_text(json.dumps(TOTAL), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HARNESS_SCRIPT", str(script))
    monkeypatch.setenv("HARNESS_LAYERS", "3")
    assert command("ex", scenario_name="good") == 0
    output = capsys.readouterr().out
    assert output.count("  ok  ") == 2 and "PASS ex/good (layer 3)" in output
    assert command("ex") == 0                                  # the layer 4 scenario is skipped, and says so
    assert "skipped ex/later" in capsys.readouterr().out
    script.write_text(json.dumps([reply("Nothing to run.")]), encoding="utf-8")
    assert command("ex", scenario_name="good") == 1
    assert "  FAIL" in capsys.readouterr().out
