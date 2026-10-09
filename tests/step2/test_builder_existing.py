"""SPEC 5.7: reuse, kept steps, rebuilds, and a failed rebuild that leaves the working module alone."""
import json

import pytest

import step2_helpers as h
from step2_helpers import (CANNOT_REUSE, built, NOT_REGISTERED, REASON_CODE, REASON_SPEC, REASON_SKIPPED, REASON_STOPPED, events,
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


def test_a_registered_module_is_shown_to_the_spec_writer(build, conn):
    h.install_surplus(conn, step_id="old_step")
    _, model, _ = build([reuse_module("monthly_surplus")], brief=only_step("s1"))
    content = model.calls[0]["messages"][0]["content"]
    assert "[registered modules]\n" in content and "monthly_surplus" in content.split("[registered modules]\n")[1]


def test_a_module_that_cannot_be_reused_is_explained_and_counts_as_an_attempt(build, conn, modules_dir):
    h.install_months(conn, step_id="old_step")
    edit(modules_dir / "months_to_goal")
    script = [reuse_module("ghost"), reuse_module("months_to_goal"), *surplus_script()]
    results, model, _ = build(script, built(), brief=only_step("s1"))
    first = tool_results(model, 1)
    second = tool_results(model, 2)
    assert [m["content"] for m in first] == [CANNOT_REUSE.format(name="ghost")] and first[0]["is_error"] is True
    assert [m["content"] for m in second] == [CANNOT_REUSE.format(name="ghost"), CANNOT_REUSE.format(name="months_to_goal")]
    assert results[0]["outcome"] == "built" and events(conn, "calc.module_reused") == []


def test_reuse_does_not_change_what_was_registered(build, conn, registry):
    h.install_surplus(conn, step_id="old_step")
    before = registry.get_module(conn, "monthly_surplus")
    build([reuse_module("monthly_surplus")], brief=only_step("s1"))
    after = registry.get_module(conn, "monthly_surplus")
    assert {**after, "steps": before["steps"]} == before and after["steps"] == ["old_step", "s1"]


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


def test_a_kept_step_does_not_stop_the_next_one_being_built(build, conn):
    h.install_surplus(conn, step_id="s1")
    results, model, _ = build(h.months_script(), built())
    assert [(r["step"], r["outcome"]) for r in results] == [("s1", "kept"), ("s3", "built")]
    assert len(model.calls) == 3


@pytest.mark.parametrize("damage", ["edit", "delete"])
def test_a_plain_build_rebuilds_a_module_whose_files_changed_or_are_missing(build, conn, registry, modules_dir, gate, damage):
    h.install_surplus(conn, step_id="s1")
    folder = modules_dir / "monthly_surplus"
    old = registry.get_module(conn, "monthly_surplus")
    old_run = gate.call(conn, "monthly_surplus", {"income": "5", "spending": "3"}, assumptions=[],
                        expected="about 2", session_id="before")
    if damage == "edit":
        edit(folder)
    else:
        (folder / "tests.py").unlink()

    script = [propose_spec(name="something_else"), propose_examples(NEW_EXAMPLES), write_module()]
    results, model, _ = build(script, built(), brief=only_step("s1"))

    assert results == [{"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""}]
    assert [t.name for t in model.calls[0]["tools"]] == ["propose_spec"]            # no reuse_module on a rebuild
    new = registry.get_module(conn, "monthly_surplus")
    assert new["fingerprint"] != old["fingerprint"] and new["fingerprint"] == h.expected_fingerprint(folder)
    assert registry.file_status(conn, "monthly_surplus") == "unchanged"
    assert new["spec"]["name"] == "monthly_surplus"                                  # set by the harness
    assert json.loads((folder / "golden.json").read_text(encoding="utf-8")) == h.golden_of(NEW_EXAMPLES)
    assert registry.step_map(conn) == {"s1": "monthly_surplus"}
    # History is never lost: the old runs still name the old fingerprint.
    assert any(r["fingerprint"] == old["fingerprint"] for r in rows(conn, "test_runs"))
    [run] = rows(conn, "calc_runs")
    assert run["id"] == old_run["run_id"] and run["fingerprint"] == old["fingerprint"]
    assert gate.call(conn, "monthly_surplus", {"income": "9", "spending": "4"}, assumptions=[],
                     expected="about 5", session_id="after")["output"] == "5"


def test_the_spec_writer_sees_the_current_spec_and_not_the_module_it_is_replacing(build, conn, modules_dir):
    h.install_surplus(conn, step_id="s1")
    h.install_months(conn, step_id="other_step")
    edit(modules_dir / "monthly_surplus")
    brief = only_step("s1")
    _, model, _ = build(surplus_script(), built(), brief=brief)
    content = model.calls[0]["messages"][0]["content"]
    others = content.split("[registered modules]\n")[1].split("[current spec]\n")[0]
    assert "months_to_goal" in others and "monthly_surplus" not in others
    assert content.endswith("[current spec]\n" + json.dumps(saved_spec(surplus_spec(), "s1"), indent=2, ensure_ascii=False))


def test_the_first_message_of_a_rebuild_has_five_sections_in_order(build, conn, modules_dir):
    h.install_surplus(conn, step_id="s1")
    edit(modules_dir / "monthly_surplus")
    brief = only_step("s1")
    _, model, _ = build(surplus_script(), built(), brief=brief)
    assert model.calls[0]["messages"][0]["content"] == sections(
        ("step", brief["process"][0]), ("brief", brief), ("registered modules", []), ("notes", []),
        ("current spec", saved_spec(surplus_spec(), "s1")))


# ---- rebuild=NAME ----------------------------------------------------------------------------

def test_rebuild_handles_only_that_module_even_when_its_files_are_unchanged(build, conn):
    h.install_surplus(conn, step_id="s1")
    h.install_months(conn, step_id="s3")
    results, model, _ = build([propose_spec(), propose_examples(NEW_EXAMPLES), write_module()], built(),
                              rebuild="monthly_surplus")
    assert results == [{"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""}]
    assert len(model.calls) == 3 and [t.name for t in model.calls[0]["tools"]] == ["propose_spec"]


def test_rebuild_leaves_the_other_modules_alone(build, conn, modules_dir):
    h.install_surplus(conn, step_id="s1")
    h.install_months(conn, step_id="s3")
    untouched = h.snapshot(modules_dir / "months_to_goal")
    build([propose_spec(), propose_examples(NEW_EXAMPLES), write_module()], built(), rebuild="monthly_surplus")
    assert h.snapshot(modules_dir / "months_to_goal") == untouched


def test_rebuild_of_an_unregistered_module(build):
    with pytest.raises(ValueError) as error:
        build([], rebuild="ghost")
    assert str(error.value) == NOT_REGISTERED.format(name="ghost")


def test_rebuild_of_a_module_whose_step_is_not_in_the_brief(build, conn):
    h.install_surplus(conn, step_id="s1")
    with pytest.raises(ValueError) as error:
        build([], brief=only_step("s3"), rebuild="monthly_surplus")
    assert "'s1'" in str(error.value)


def test_the_step_of_a_rebuild_is_the_one_in_the_modules_spec(build, conn):
    h.install_surplus(conn, step_id="s3")                 # built for step s3, whatever the module does
    results, _, person = build([propose_spec(), propose_examples(NEW_EXAMPLES), write_module()], built(),
                               rebuild="monthly_surplus")
    assert results[0]["step"] == "s3" and results[0]["outcome"] == "built"
    assert person.told[0] == "Step s3: Work out the months to reach the target"


# ---- a failed rebuild ------------------------------------------------------------------------

WRONG = write_module(h.WRONG_SURPLUS_PY, h.WRONG_SURPLUS_TESTS)


@pytest.mark.parametrize("script, answers, reason", [
    ([propose_spec(description="")] * 3, [], REASON_SPEC),
    ([propose_spec(), propose_examples(NEW_EXAMPLES)], ["yes", "/accept", "/quit"], REASON_STOPPED),
    ([propose_spec()], ["/skip"], REASON_SKIPPED),
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


def test_a_failed_rebuild_of_a_changed_module_does_not_repair_it(build, conn, registry, modules_dir):
    h.install_surplus(conn, step_id="s1")
    edit(modules_dir / "monthly_surplus")
    files = h.snapshot(modules_dir / "monthly_surplus")
    results, _, _ = build([propose_spec(description="")] * 3, brief=only_step("s1"))
    assert results[0]["outcome"] == "not_built"
    assert h.snapshot(modules_dir / "monthly_surplus") == files
    assert registry.file_status(conn, "monthly_surplus") == "changed"
