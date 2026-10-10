"""SPEC 5.7: `build_step`, the whole pipeline for one step, and `build`, which calls it for each step of the process."""
import json

import pytest

import step2_helpers as h
from step2_helpers import (NO_STEP, REASON_CODE, REASON_SKIPPED, REASON_STOPPED, STEP_HEADER, built, events, months_script,
                           only_step, payloads, propose_examples, propose_spec, respond, reuse_module, rows, sections,
                           surplus_script, write_module, yearly_script)

S1 = {"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""}
S3 = {"step": "s3", "outcome": "built", "module": "months_to_goal", "reason": ""}
ADDED = {"step": "added_1", "outcome": "built", "module": "yearly_cost", "reason": ""}


def stopped(step):
    return {"step": step, "outcome": "not_built", "module": None, "reason": REASON_STOPPED}


# ---- calling build_step ----------------------------------------------------------------------


def test_a_built_step_returns_its_result(build_one):
    result, model, _ = build_one(surplus_script(), built())
    assert result == S1 and len(model.calls) == 3


# ---- /quit is caught by build_step -------------------------------------------------------------

STOPS = [
    ([propose_spec()], ["/quit"]),
]
STOP_IDS = ["at the plan check"]


@pytest.mark.parametrize("script, answers", STOPS, ids=STOP_IDS)
def test_quit_ends_the_step_as_not_built_and_does_not_raise(build_one, conn, registry, script, answers):
    result, _, _ = build_one(script, answers)
    assert result == stopped("s1")
    assert registry.list_modules(conn) == [] and registry.step_map(conn) == {}


# ---- an added step is a step like any other ----------------------------------------------------


# ---- build: the steps of the process ----------------------------------------------------------

def test_build_handles_the_brief_steps_and_then_the_added_steps(build, conn):
    step = h.add_new_step(conn)
    script = surplus_script() + months_script() + yearly_script()
    results, model, person = build(script, built(3))
    assert results == [S1, S3, ADDED] and len(model.calls) == 9
    assert [t for t in person.told if t.startswith("Step ")] == [
        "Step s1: Work out the monthly surplus", "Step s3: Work out the months to reach the target",
        f"Step added_1 (not in the brief): {step['name']}"]


# ---- build stops its list on REASON_STOPPED ------------------------------------------------------


# ---- build calls build_step ------------------------------------------------------------------


