"""SPEC 2.6 at step 2: the `build` act and the `steps` expectation of replay."""
from pathlib import Path

import pytest

from harness import replay
from harness.model import ScriptedModel
from layer2_helpers import double_turns, small_plan, write_built_modules, write_plan


@pytest.fixture(autouse=True)
def scratch(monkeypatch, tmp_path):
    """Replay's scratch folders go to the test's own place."""
    monkeypatch.setattr(replay, "REPLAY_DIR", tmp_path / "replay")


def build_scenario(**more):
    found = {"name": "b", "layer": 2, "kind": "build", "without": ["c2"], "lines": [],
             "expect": {"steps": {"c2": "built", "c1": "kept"}}}
    found.update(more)
    return found


def test_the_steps_expectation_is_there_from_layer_2_and_not_before():
    assert "steps" not in replay.expectations(1) and "steps" in replay.expectations(2)


def test_a_scenario_with_a_mistake_in_its_steps_is_refused_with_the_problem_named():
    for change, expected in [({"expect": {"steps": {"zz": "built"}}}, "'zz' is not a calculation step"),
                             ({"expect": {"steps": {"c1": "dusty"}}}, "expect.steps"),
                             ({"layer": 1, "expect": {"steps": {"c1": "kept"}}}, "unknown key: steps")]:
        errors = replay.validate_scenario(build_scenario(**change), stem="b", brief=small_plan(), layers=2)
        assert any(expected in error for error in errors), (change, errors)


def test_a_build_scenario_builds_what_was_left_out_and_keeps_the_rest(tmp_path):
    folder = tmp_path / "build"
    write_plan(folder / "brief")
    write_built_modules(folder / "modules")
    assert replay.validate_scenario(build_scenario(), stem="b", brief=small_plan(), layers=2) == []
    model = ScriptedModel(double_turns())
    result = replay.run_scenario(build_scenario(), example_dir=folder, keep=True, model_factory=lambda: model,
                                 write=lambda text: None)
    assert result["passed"], result
    assert (Path(result["folder"]) / "modules" / "double").is_dir()
    assert len(list((folder / "modules").iterdir())) == 2                           # the example itself is not written


def test_a_step_that_was_not_built_fails_its_expectation(tmp_path):
    folder = tmp_path / "build"
    write_plan(folder / "brief")
    write_built_modules(folder / "modules")
    model = ScriptedModel([])                                            # the model has nothing to build with
    result = replay.run_scenario(build_scenario(), example_dir=folder, model_factory=lambda: model,
                                 write=lambda text: None)
    assert not result["passed"] and "c2" in result["checks"][0]["seen"]
