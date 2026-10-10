"""SPEC 6.5: `run_scenario` runs one scenario in a scratch folder, with the scripted model."""
import hashlib
import os
from pathlib import Path

import pytest

import step3_helpers as s3
from step3_helpers import ask_script
from harness.model import ScriptedModel


@pytest.fixture(autouse=True)
def scratch(replay_scratch):
    """Every test here runs from the repository root and has what it leaves in my/var/replay taken away."""
    return replay_scratch


def run(replay, example, scenario=None, *, script=None, keep=False, model=None, name=None):
    folder = example(scenarios={}) if callable(example) else example
    scenario = scenario or s3.ask_scenario()
    model = model or ScriptedModel(script if script is not None else ask_script())
    return replay.run_scenario(scenario, example_dir=folder, model=model, keep=keep)


def kept_events(result, **options):
    return s3.stored_events(Path(result["folder"]) / "harness.db", **options)


def tree(folder):
    """{relative path: digest} of every file under a folder."""
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(folder).rglob("*")) if p.is_file()}


# ---- the result ------------------------------------------------------------------------------------------------------

def test_a_scenario_that_goes_well_passes(replay, example):
    result = run(replay, example)
    assert result["scenario"] == "upfront" and result["passed"] is True and result["error"] is None
    assert result["folder"] is None
    assert len(result["checks"]) == 4 and all(check["passed"] for check in result["checks"])


def test_a_check_that_fails_fails_the_scenario_but_is_not_an_error(replay, example):
    scenario = s3.ask_scenario(expect={"shown": ["9,999"]})
    result = run(replay, example, scenario)
    assert result["passed"] is False and result["error"] is None
    assert result["checks"] == [{"what": "shows 9,999", "passed": False, "seen": "in none of 1 replies"}]


# ---- the scratch folder -----------------------------------------------------------------------------------------------


# ---- the environment --------------------------------------------------------------------------------------------------

class Spy(ScriptedModel):
    """Notes the three settings and the working database while the model is asked."""

    def complete(self, **kwargs):
        self.seen = {name: os.environ.get(name) for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR")}
        return super().complete(**kwargs)


# ---- the session --------------------------------------------------------------------------------------------------------


def test_the_session_ends_with_the_checked_event(replay, example):
    result = run(replay, example, keep=True)
    last = kept_events(result)[-1]
    assert last["kind"] == "replay.checked" and last["actor"] == "harness"
    assert last["payload"]["scenario"] == "upfront" and last["payload"]["passed"] is True
    assert last["payload"]["checks"] == result["checks"]


# ---- a build scenario ------------------------------------------------------------------------------------------------


# ---- errors --------------------------------------------------------------------------------------------------------------
