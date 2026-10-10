"""SPEC 2.6: scenarios, their validation, and replay of a scripted person on a Session: what the core owns.

Replay is shared code that acts on what the layers register. These tests run it on made-up layers
(`layer0_helpers.made_up_layers`), so they hold with only the core present. What a real layer's keys and acts
mean is tested in that layer's folder: `test_replay_build.py` (layer 2), `test_replay_answers.py` (3),
`test_replay_needs_you.py` (4) and `test_replay_review.py` (5).
"""
import argparse
import dataclasses
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from harness import replay
from harness.core import NotNow
from harness.model import ScriptedModel
from layer0_helpers import SETTLE, install_made_up_layers, made_up_layers

HI = "hello there"
BRIEF = {"process": [{"id": "c1", "kind": "calculation"}, {"id": "c2", "kind": "calculation"},
                     {"id": "j1", "kind": "judgment"}]}


@pytest.fixture(autouse=True)
def tree(monkeypatch, tmp_path):
    """Made-up layers 1 to 5 in the tree, and replay's scratch folders in the test's own place."""
    monkeypatch.setattr(replay, "REPLAY_DIR", tmp_path / "replay")
    return install_made_up_layers(monkeypatch)


@pytest.fixture
def example(tmp_path):
    """An example folder: a brief of c1, c2 and j1, and a module folder for each calculation."""
    folder = tmp_path / "ex"
    (folder / "brief").mkdir(parents=True)
    (folder / "brief" / "domain_brief.json").write_text(json.dumps(BRIEF), encoding="utf-8")
    for name, step in (("m1", "c1"), ("m2", "c2")):
        (folder / "modules" / name).mkdir(parents=True)
        (folder / "modules" / name / "spec.json").write_text(json.dumps({"step_id": step}), encoding="utf-8")
        (folder / "modules" / name / "module.py").write_text("# a module\n", encoding="utf-8")
    return folder


def scenario(layer=3, **more):
    found = {"name": "s", "layer": layer, "kind": "ask", "lines": [HI], "expect": {"said": ["heard: hello"]}}
    found.update(more)
    return found


def play(found, example, **options):
    options.setdefault("write", lambda text: None)
    return replay.run_scenario(found, example_dir=example, model_factory=lambda: ScriptedModel([]), **options)


# --- The scenario format ---

MISTAKES = [
    ({"extra": 1}, "unknown key: extra"),
    ({"name": "other"}, "name must be"),
    ({"layer": 6}, "layer must be"),
    ({"kind": "chat"}, "kind must be"),
    ({"lines": []}, "at least one line"),
    ({"kind": "build", "today": "2027-01-15"}, "today is only for ask"),
    ({"today": "15 January"}, "today must be"),
    ({"review": "yes"}, "review must be"),
    ({"lines": [{"act": "wave"}]}, "unknown act 'wave'"),
    ({"lines": [{"act": "choose"}]}, "needs 'option'"),
    ({"lines": [{"act": "use"}]}, "needs layer 5"),
    ({"layer": 1, "kind": "build", "lines": []}, "needs layer 2 or above"),
    ({"lines": [{"act": "say", "text": "hi", "step": "zz"}]}, "'zz' is not a step"),
    ({"lines": [{"act": "build", "text": "now"}]}, "does not take 'text'"),
    ({"lines": [{"act": "say", "text": " "}]}, "non-empty text"),
    ({"without": ["j1"]}, "not a calculation step"),
    ({"expect": {}}, "at least one expectation"),
    ({"expect": {"nosuch": 1}}, "unknown key: nosuch"),
    ({"expect": {"said": [1]}}, "expect.said: must be a list of words"),
    ({"layer": 2, "expect": {"late": ["x"]}}, "unknown key: late"),
]


def test_a_scenario_with_a_mistake_is_refused_with_the_problem_named():
    for change, expected in MISTAKES:
        errors = replay.validate_scenario(scenario(**change), stem="s", brief=BRIEF, layers=5)
        assert any(expected in error for error in errors), (change, errors)


def test_a_sound_scenario_has_no_problem_and_a_missing_key_is_named():
    assert replay.validate_scenario(scenario(), stem="s", brief=BRIEF, layers=5) == []
    found = scenario()
    del found["expect"]
    assert replay.validate_scenario(found, stem="s", brief=BRIEF, layers=5) == ["missing: expect"]
    assert replay.validate_scenario([], stem="s", brief=BRIEF) == ["the scenario must be an object"]


def test_the_expectations_come_from_the_layers_up_to_the_scenarios():
    assert set(replay.expectations(0)) == set()
    assert set(replay.expectations(1)) == {"said"}
    assert set(replay.expectations(3)) == {"said", "counted", "late"}
    assert set(replay.expectations(5)) == {"said", "counted", "late", "later", "latest"}
    assert replay.expectations(2)["counted"].validate(2) is None
    assert replay.expectations(2)["counted"].validate("2")


def test_a_scenario_is_checked_only_against_the_layers_present():
    found = scenario(layer=4, expect={"later": ["x"]})
    assert replay.validate_scenario(found, stem="s", brief=BRIEF, layers=5) == []
    assert any("unknown key: later" in error for error in replay.validate_scenario(found, stem="s", brief=BRIEF, layers=3))


def test_loading_skips_layers_above_the_enabled_ones_and_names_the_file_of_a_problem(example, monkeypatch):
    folder = example / "scenarios"
    folder.mkdir()
    (folder / "a.json").write_text(json.dumps(scenario(layer=2, name="a", kind="build", lines=[],
                                                       expect={"counted": 1})), encoding="utf-8")
    (folder / "b.json").write_text(json.dumps(scenario(layer=4, name="b")), encoding="utf-8")
    monkeypatch.setenv("HARNESS_LAYERS", "3")
    found, skipped = replay.load_scenarios(example)
    assert [each["name"] for each in found] == ["a"] and skipped == [{"name": "b", "layer": 4}]
    (folder / "a.json").write_text(json.dumps(scenario(layer=3, name="a", lines=[{"act": "wave"}])), encoding="utf-8")
    with pytest.raises(ValueError, match=r"a\.json: lines: line 1: unknown act"):
        replay.load_scenarios(example)
    (folder / "a.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match=r"a\.json: not valid JSON"):
        replay.load_scenarios(example)
    with pytest.raises(ValueError, match="There is no scenario 'zzz'.*a, b"):
        replay.load_scenarios(example, "zzz")


def test_each_act_the_core_owns_is_the_action_a_person_would_take():
    state = {"chat": [], "waiting": None, "threads": []}
    act = replay._action_for
    assert act("hello", state) == ("say", {"text": "hello"})
    assert act({"act": "say", "text": "hello", "step": "c1"}, state) == ("say", {"text": "hello", "step": "c1"})
    assert act({"act": "say", "text": "hello"}, state) == ("say", {"text": "hello", "step": None})
    assert act({"act": "build"}, state) == ("build", {})


# --- Playing a scenario ---

def watching(tree, monkeypatch):
    """Record, when the session loads, the settings and the day it was opened with."""
    seen = []

    def loaded(core):
        seen.append({**{name: os.environ.get(name) for name in ("HARNESS_LAYERS", "HARNESS_REVIEW", "HARNESS_DB")},
                     "today": core.memory.get("today")})

    tree[0] = dataclasses.replace(tree[0], hooks={"loaded": loaded})
    install_made_up_layers(monkeypatch, tree)
    return seen


def test_a_scenario_is_played_at_its_layer_and_day_and_every_expectation_gives_a_line(example, tree, monkeypatch):
    seen = watching(tree, monkeypatch)
    found = scenario(layer=2, today="2027-01-15", expect={"said": ["heard: hello"], "counted": 2})
    before = os.environ.get("HARNESS_LAYERS")
    result = play(found, example)
    assert result["passed"] and result["error"] is None
    assert [check["passed"] for check in result["checks"]] == [True, True]
    assert all(check["what"] and check["seen"] for check in result["checks"])
    [opened] = seen
    assert opened["HARNESS_LAYERS"] == "2" and opened["HARNESS_REVIEW"] == "off"
    assert str(opened["today"]) == "2027-01-15"
    assert os.environ.get("HARNESS_LAYERS") == before and os.environ.get("HARNESS_DB") != opened["HARNESS_DB"]
    assert not Path(opened["HARNESS_DB"]).parent.exists() and result["folder"] is None     # the scratch copy is gone


def test_review_is_switched_on_only_when_the_scenario_asks_for_it(example, tree, monkeypatch):
    seen = watching(tree, monkeypatch)
    for found in (scenario(), scenario(review=True)):
        play(found, example)
    assert [each["HARNESS_REVIEW"] for each in seen] == ["off", "auto"]


def test_a_failed_expectation_fails_the_scenario_and_says_what_was_seen(example):
    found = scenario(expect={"said": ["something else"], "counted": 0})
    result = play(found, example)
    assert not result["passed"] and result["error"] is None
    assert [check["passed"] for check in result["checks"]] == [False, True]
    assert "something else" in result["checks"][0]["what"] and "messages" in result["checks"][0]["seen"]


def test_an_expectation_that_cannot_be_checked_is_a_failed_check(example, tree, monkeypatch):
    def broken(value, session):
        raise RuntimeError("no way\nto know")

    tree[0] = dataclasses.replace(tree[0], expects={"said": dataclasses.replace(tree[0].expects["said"], check=broken)})
    install_made_up_layers(monkeypatch, tree)
    result = play(scenario(), example)
    assert not result["passed"] and result["checks"][0]["seen"] == "RuntimeError: no way to know"


def test_keep_leaves_the_scratch_copy_with_the_events_of_the_run(example):
    result = play(scenario(), example, keep=True)
    folder = Path(result["folder"])
    assert (folder / "brief" / "domain_brief.json").is_file() and (folder / "modules" / "m1").is_dir()
    kinds = [row[0] for row in sqlite3.connect(folder / "harness.db").execute("SELECT kind FROM events")]
    assert kinds.count("replay.scenario") == 1 and kinds.count("replay.checked") == 1


def test_a_build_scenario_builds_what_was_left_out_and_keeps_the_rest(example):
    found = {"name": "b", "layer": 2, "kind": "build", "without": ["c2"], "lines": [],
             "expect": {"said": ["built"]}}
    assert replay.validate_scenario(found, stem="b", brief=BRIEF, layers=5) == []
    result = play(found, example, keep=True)
    assert result["passed"], result
    assert [path.name for path in (Path(result["folder"]) / "modules").iterdir()] == ["m1"]
    assert len(list((example / "modules").iterdir())) == 2                            # the example itself is not written


def test_a_line_the_harness_refuses_stops_the_scenario_but_the_checks_still_run(example, tree, monkeypatch):
    def refuse(core, payload):
        raise NotNow("not now")

    tree[1] = dataclasses.replace(tree[1], actions={"build": refuse})
    install_made_up_layers(monkeypatch, tree)
    result = play(scenario(layer=2, lines=[HI, {"act": "build"}, "never said"]), example)
    assert not result["passed"] and "did not take line 2 (build): not now" in result["error"]
    assert result["checks"] and result["checks"][0]["passed"]           # what happened before is still reported


def test_a_lane_that_does_not_finish_is_reported_as_stuck(example, tree, monkeypatch):
    release = threading.Event()

    def slow(core, message):
        return lambda work, message: release.wait(SETTLE)

    tree[0] = dataclasses.replace(tree[0], route=slow)
    install_made_up_layers(monkeypatch, tree)
    try:
        result = play(scenario(), example, timeout=0.5)
    finally:
        release.set()
    assert not result["passed"] and "still working" in result["error"]


def test_a_failed_job_is_reported_not_swallowed(example, tree, monkeypatch):
    def broken(core, message):
        def handle(work, message):
            raise RuntimeError("broke")
        return handle

    tree[0] = dataclasses.replace(tree[0], route=broken)
    install_made_up_layers(monkeypatch, tree)
    result = play(scenario(), example)
    assert not result["passed"] and result["error"].startswith("a job failed")


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
    (folder / "scenarios").mkdir(parents=True)
    good = scenario(layer=2, name="good", lines=[HI, {"act": "build"}],
                    expect={"said": ["heard: hello", "built"], "counted": 2})
    (folder / "scenarios" / "good.json").write_text(json.dumps(good), encoding="utf-8")
    later = scenario(layer=3, name="later")
    (folder / "scenarios" / "later.json").write_text(json.dumps(later), encoding="utf-8")
    script = tmp_path / "script.json"
    script.write_text("[]", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HARNESS_SCRIPT", str(script))
    monkeypatch.setenv("HARNESS_LAYERS", "2")
    assert command("ex", scenario_name="good") == 0
    output = capsys.readouterr().out
    assert output.count("  ok  ") == 2 and "PASS ex/good (layer 2)" in output
    assert command("ex") == 0                                  # the layer 3 scenario is skipped, and says so
    assert "skipped ex/later" in capsys.readouterr().out
    good["expect"]["said"] = ["something else"]
    (folder / "scenarios" / "good.json").write_text(json.dumps(good), encoding="utf-8")
    assert command("ex", scenario_name="good") == 1
    assert "  FAIL" in capsys.readouterr().out
