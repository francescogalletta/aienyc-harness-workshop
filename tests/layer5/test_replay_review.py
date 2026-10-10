"""SPEC 2.6 at step 5: the `use` and `dismiss` acts and the `challenges` expectation, and the seeded scenarios
of both examples (which together need every layer)."""
import json
from pathlib import Path

import pytest

from harness import replay
from layer5_helpers import SplitModel, challenge, point_replay_at, reply, report, scenario, small_plan, world_folder

ROOT = Path(__file__).resolve().parents[2]
SEEDED = sorted((ROOT / "examples").glob("*/scenarios/*.json"))


@pytest.fixture(autouse=True)
def scratch(monkeypatch, tmp_path):
    point_replay_at(monkeypatch, tmp_path)


@pytest.fixture
def example(tmp_path):
    return world_folder(tmp_path)


def test_every_seeded_scenario_validates_and_together_they_exercise_every_layer():
    layers = set()
    for path in SEEDED:
        value = json.loads(path.read_text(encoding="utf-8"))
        brief = replay.read_brief(path.parents[1])
        assert replay.validate_scenario(value, stem=path.stem, brief=brief, layers=5) == [], path
        layers.add(value["layer"])
    assert {path.parts[-3] for path in SEEDED} == {"wedding", "moving"}
    assert layers >= {2, 3, 4, 5}


def test_the_challenges_expectation_is_there_from_layer_5_and_not_before():
    assert "challenges" not in replay.expectations(4) and "challenges" in replay.expectations(5)
    assert replay.expectations(5)["challenges"].validate({"min": 2, "used": 1, "dismissed": 1}) is None
    assert replay.expectations(5)["challenges"].validate({"used": "1"})
    errors = replay.validate_scenario(scenario(layer=4, expect={"challenges": {"min": 1}}),
                                      stem="s", brief=small_plan(), layers=5)
    assert any("unknown key: challenges" in error for error in errors)
    errors = replay.validate_scenario(scenario(layer=4, lines=["hi", {"act": "use"}]),
                                      stem="s", brief=small_plan(), layers=5)
    assert any("'use' needs layer 5" in error for error in errors)
    assert replay.validate_scenario(scenario(layer=5, lines=["hi", {"act": "use", "index": 2}, {"act": "dismiss"}],
                                             expect={"challenges": {"min": 1}}),
                                    stem="s", brief=small_plan(), layers=5) == []


def test_use_and_dismiss_are_the_action_on_the_open_challenge_a_person_means():
    state = {"chat": [], "waiting": None,
             "threads": [{"id": "t1", "kind": "side", "challenge": None},
                         {"id": "t2", "kind": "review", "challenge": {"id": "c5", "kind": "question", "status": "open"}},
                         {"id": "t3", "kind": "review", "challenge": {"id": "c7", "kind": "challenge", "status": "open"}},
                         {"id": "t4", "kind": "review", "challenge": {"id": "c6", "kind": "challenge", "status": "used"}}]}
    act = replay._action_for
    assert act({"act": "use"}, state) == ("use_challenge", {"challenge": "c7"})            # a question cannot be used
    assert act({"act": "dismiss"}, state) == ("dismiss_challenge", {"challenge": "c5"})
    assert act({"act": "dismiss", "index": 2}, state) == ("dismiss_challenge", {"challenge": "c7"})
    for line in ({"act": "use", "index": 2}, {"act": "dismiss", "index": 3}):
        with pytest.raises(replay.ReplayError):
            act(line, state)


def test_a_challenge_is_used_and_another_dismissed(example):
    model = SplitModel(analyst=[reply("Understood.")], reviewer=[report(
        challenge(step="c1", title="First"), challenge(step="c2", title="Second"))])
    found = scenario(layer=5, review=True, lines=[{"act": "use"}, {"act": "dismiss"}],
                     expect={"challenges": {"min": 2, "used": 1, "dismissed": 1}})
    result = replay.run_scenario(found, example_dir=example, model_factory=lambda: model, write=lambda text: None)
    assert result["passed"], result
