"""SPEC 2.6 at step 3: replay of a scripted person on the answers layer: the keys `runs`, `shown` and
`max_withheld`, and a scenario played from the command."""
import argparse
import json
import os
import sqlite3
from pathlib import Path

import pytest

from harness import replay
from harness.model import ScriptedModel
from layer3_helpers import TOTAL, play, point_replay_at, reply, run, scenario, small_plan, world_folder, write_world


@pytest.fixture(autouse=True)
def scratch(monkeypatch, tmp_path):
    point_replay_at(monkeypatch, tmp_path)


@pytest.fixture
def example(tmp_path):
    return world_folder(tmp_path)


def test_the_expectations_come_from_the_layers_up_to_the_scenarios():
    assert "runs" not in replay.expectations(2) and "runs" in replay.expectations(3)
    assert {"runs", "shown", "max_withheld"} <= set(replay.expectations(3))
    assert "decisions" not in replay.expectations(3)


def test_a_scenario_with_a_mistake_in_its_answers_is_refused_with_the_problem_named():
    for change, expected in [({"expect": {"shown": ["9"]}}, "expect.shown"),
                             ({"expect": {"runs": [{"module": 5}]}}, "expect.runs"),
                             ({"expect": {"decisions": [{"step": "j1"}]}}, "unknown key: decisions")]:
        errors = replay.validate_scenario(scenario(layer=3, **change), stem="s", brief=small_plan(), layers=3)
        assert any(expected in error for error in errors), (change, errors)
    assert replay.validate_scenario(scenario(layer=3, expect={"runs": [{"module": "total"}], "shown": ["30"]}),
                                    stem="s", brief=small_plan(), layers=3) == []


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


def test_a_failed_job_is_reported_not_swallowed(example):
    result = play(scenario(layer=3), example, [])
    assert not result["passed"] and result["error"].startswith("a job failed")


# --- The command ---

def command(example_name, *, scenario_name=None, keep=False):
    return replay.replay_command(argparse.Namespace(example=example_name, scenario=scenario_name, keep=keep))


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
