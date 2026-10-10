"""SPEC 5.7: reuse, kept steps, rebuilds, and a failed rebuild that leaves the working module alone."""
import json

import pytest

import step2_helpers as h
from step2_helpers import (CANNOT_REUSE, built, NOT_REGISTERED, NO_STEP, REASON_CODE, REASON_SPEC, REASON_SKIPPED, REASON_STOPPED, events,
                           only_step, payloads, propose_examples, propose_spec, reuse_module, rows, saved_spec,
                           sections, surplus_script, surplus_spec, write_module)

NEW_EXAMPLES = [
    {"inputs": {"income": "900", "spending": "400"}, "expected": "500", "working": "900 less 400 leaves 500"},
    {"inputs": {"income": "10", "spending": "20"}, "expected": "-10", "working": "10 less 20 is minus 10"},
    {"inputs": {"income": "7.50", "spending": "2.25"}, "expected": "5.25", "working": "7.50 less 2.25 leaves 5.25"},
]


def edit(folder, name="module.py"):
    """Change a registered module's file, so that its fingerprint no longer matches."""
    path = folder / name
    path.write_text("# edited by hand\n" + path.read_text(encoding="utf-8"), encoding="utf-8")


def tool_results(model, call_index):
    return [m for m in model.calls[call_index]["messages"] if m["role"] == "tool"]


# ---- reuse -----------------------------------------------------------------------------------

def test_a_step_can_reuse_a_registered_module_in_one_model_call(build, conn, registry):
    h.install_surplus(conn, step_id="old_step")
    results, model, person = build([reuse_module("monthly_surplus", "Same job.")], brief=only_step("s1"))
    assert results == [{"step": "s1", "outcome": "reused", "module": "monthly_surplus", "reason": ""}]
    assert len(model.calls) == 1 and person.asked == []
    assert registry.step_map(conn) == {"old_step": "monthly_surplus", "s1": "monthly_surplus"}
    assert events(conn, "calc.module_reused") == [("calc.module_reused", "agent", {
        "step": "s1", "module": "monthly_surplus", "reason": "Same job."})]
    assert person.told[0] == "Step s1: Work out the monthly surplus"


# ---- steps that already have a module --------------------------------------------------------

def test_a_step_with_an_unchanged_module_is_kept_and_no_model_is_called(build, conn):
    h.install_surplus(conn, step_id="s1")
    h.install_months(conn, step_id="s3")
    results, model, person = build([])
    assert results == [{"step": "s1", "outcome": "kept", "module": "monthly_surplus", "reason": ""},
                       {"step": "s3", "outcome": "kept", "module": "months_to_goal", "reason": ""}]
    assert model.calls == [] and person.asked == []
    assert events(conn, "calc.step_not_built") == []
    assert [t for t in person.told if t.startswith("Step ")] == [
        "Step s1: Work out the monthly surplus", "Step s3: Work out the months to reach the target"]


# ---- rebuild=NAME ----------------------------------------------------------------------------


# ---- a failed rebuild ------------------------------------------------------------------------

WRONG = write_module(h.WRONG_SURPLUS_PY, h.WRONG_SURPLUS_TESTS)


@pytest.mark.parametrize("script, answers, reason", [
    ([propose_spec(), propose_examples(NEW_EXAMPLES), WRONG, WRONG, WRONG], built(), REASON_CODE),
])
def test_a_failed_rebuild_leaves_the_registered_module_exactly_as_it_was(build, conn, registry, modules_dir,
                                                                          script, answers, reason):
    h.install_surplus(conn, step_id="s1")
    folder = modules_dir / "monthly_surplus"
    files, module, mapping = h.snapshot(folder), registry.get_module(conn, "monthly_surplus"), registry.step_map(conn)
    modules_before = rows(conn, "modules")

    results, _, _ = build(script, answers, rebuild="monthly_surplus")

    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": reason}]
    assert h.snapshot(folder) == files
    assert registry.get_module(conn, "monthly_surplus") == module
    assert registry.step_map(conn) == mapping and rows(conn, "modules") == modules_before
    assert registry.file_status(conn, "monthly_surplus") == "unchanged"
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": reason}]


