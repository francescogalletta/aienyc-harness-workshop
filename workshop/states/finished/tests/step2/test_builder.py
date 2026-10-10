"""SPEC 5.7: the builder, from the brief to a registered module. The model is scripted, the person is a list of answers."""
import json

import pytest

import step2_helpers as h
from step2_helpers import (DRAFT_BRIEF, NAME_TAKEN, NO_BRIEF, ONE_CALL, RESERVED_ID, PLAN_QUESTION, REASON_SPEC, SPEC_REJECTED,
                           STEP_HEADER, USE_TOOL, built, events, make_brief, months_script, months_spec, only_step,
                           payloads, propose_examples, propose_spec, rows, say_text, saved_spec, sections,
                           surplus_examples, surplus_script, surplus_spec, tools, write_module)

S1 = {"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""}
S3 = {"step": "s3", "outcome": "built", "module": "months_to_goal", "reason": ""}


def bullets(content, header):
    """The lines after a fixed first line, which must be `- ` bullets."""
    lines = [line for line in content.splitlines() if line.strip()]
    assert lines[0] == header
    assert lines[1:] and all(line.startswith("- ") for line in lines[1:]), lines
    return [line[2:] for line in lines[1:]]


def tool_messages(model, call_index):
    return [m for m in model.calls[call_index]["messages"] if m["role"] == "tool"]


# ---- the fixed strings and schemas -----------------------------------------------------------

FIXED_STRINGS = [
    "NO_BRIEF", "DRAFT_BRIEF", "RESERVED_ID", "NO_STEP", "STEP_HEADER", "WRITING_SPEC", "WRITING_EXAMPLES", "WRITING_CODE", "READING_REPLY",
    "USE_TOOL", "ONE_CALL", "SPEC_REJECTED", "NAME_TAKEN", "CANNOT_REUSE", "PLAN_QUESTION", "PLAN_FEEDBACK",
    "PLAN_KEPT", "EXAMPLES_REJECTED", "EXAMPLES_INTRO", "CONFIRM_EXAMPLE", "CONFIRM_ANSWER", "NOTE_KEPT",
    "NOT_UNDERSTOOD", "CODE_REJECTED", "RUNNING_TESTS", "TESTS_FAILED", "EXAMPLE_FAILED", "EXAMPLES_DISAGREE",
    "DISAGREEMENT", "REASON_SPEC", "REASON_SKIPPED", "REASON_EXAMPLES", "REASON_CONFIRMED", "REASON_CODE",
    "REASON_STOPPED", "ACCEPT_WORDS", "KIND_WORDS"]


# ---- load_brief ------------------------------------------------------------------------------


def save_with_ids(save_confirmed_brief, *ids, status="confirmed"):
    """Save a brief whose process holds a step of kind calculation for each id."""
    steps = [{**make_brief()["process"][0], "id": step_id} for step_id in ids]
    save_confirmed_brief(make_brief(process=steps), status=status)


@pytest.mark.parametrize("ids, first", [
    (["s1", "added_1"], "added_1")])
def test_load_brief_refuses_a_step_id_that_starts_with_added(builder, tmp_path, save_confirmed_brief, ids, first):
    save_with_ids(save_confirmed_brief, *ids)
    with pytest.raises(ValueError) as error:
        builder.load_brief(tmp_path / "brief")
    assert str(error.value) == RESERVED_ID.format(id=first)


# ---- a step built at the first try -----------------------------------------------------------

def test_a_step_built_at_the_first_try_takes_exactly_three_model_calls(build):
    results, model, _ = build(surplus_script(), built(), brief=only_step("s1"))
    assert results == [S1]
    assert len(model.calls) == 3


def test_each_phase_is_a_conversation_of_its_own(build):
    _, model, _ = build(surplus_script(), built(), brief=only_step("s1"))
    spec_call, examples_call, code_call = model.calls
    for call, prompt, names, schemas in [
            (spec_call, "spec_writer.md", ["propose_spec", "reuse_module"], [h.SPEC_SCHEMA, h.REUSE_SCHEMA]),
            (examples_call, "example_writer.md", ["propose_examples"], [h.EXAMPLES_SCHEMA]),
            (code_call, "module_writer.md", ["write_module"], [h.CODE_SCHEMA])]:
        assert call["system"].strip() == h.prompt_text(prompt).strip()
        assert [t.name for t in call["tools"]] == names
        assert [h.without_descriptions(t.input_schema) for t in call["tools"]] == schemas
        assert [m["role"] for m in call["messages"]] == ["user"]


def test_the_files_of_a_built_module(build, conn, modules_dir):
    build(surplus_script(), built(), brief=only_step("s1"))
    folder = modules_dir / "monthly_surplus"
    assert sorted(p.name for p in folder.iterdir() if p.is_file()) == ["golden.json", "module.py", "spec.json", "tests.py"]
    assert (folder / "module.py").read_text(encoding="utf-8") == h.SURPLUS_PY
    assert (folder / "tests.py").read_text(encoding="utf-8") == h.SURPLUS_TESTS
    assert (folder / "spec.json").read_text(encoding="utf-8") == h.dump(saved_spec(surplus_spec(), "s1"))
    assert (folder / "golden.json").read_text(encoding="utf-8") == h.dump(h.golden_of(surplus_examples()))
    assert not (modules_dir / "_build" / "monthly_surplus").exists()          # moved, not copied


# ---- the events of a build -------------------------------------------------------------------

def test_the_events_of_a_build_in_order(build, conn):
    build(surplus_script(), built(), brief=only_step("s1"))
    assert h.kinds(conn, "calc.") == ["calc.spec_proposed", "calc.plan_decision", "calc.examples_proposed",
                                      "calc.golden_decision", "calc.golden_decision", "calc.golden_decision",
                                      "calc.code_written", "calc.tests_run", "calc.module_registered"]


# ---- which steps -----------------------------------------------------------------------------

def test_calculation_steps_are_built_in_brief_order_and_other_steps_are_left_alone(build, conn):
    results, model, person = build(surplus_script() + months_script(), built(2))
    assert results == [S1, S3]
    assert len(model.calls) == 6
    assert [t for t in person.told if t.startswith("Step ")] == [
        "Step s1: Work out the monthly surplus", "Step s3: Work out the months to reach the target"]


# ---- phase 1: the spec -----------------------------------------------------------------------


def test_a_new_module_may_not_take_the_name_of_a_registered_one(build, conn):
    h.install_surplus(conn, step_id="old_step")
    script = [propose_spec(), propose_spec(name="savings_gap"), propose_examples(), write_module()]
    results, model, _ = build(script, built(), brief=only_step("s1"))
    [result] = tool_messages(model, 1)
    assert NAME_TAKEN.format(name="monthly_surplus") in bullets(result["content"], SPEC_REJECTED)
    assert results[0]["module"] == "savings_gap"


def test_three_refused_specs_end_the_step_and_the_next_step_goes_ahead(build, conn):
    bad = propose_spec(name="Bad Name")
    script = [bad, say_text("no tool"), bad, *months_script()]
    results, model, person = build(script, built())
    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_SPEC}, S3]
    assert len(model.calls) == 3 + 3
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_SPEC}]
    assert events(conn, "calc.step_not_built")[0][1] == "harness"
    assert "Step s3: Work out the months to reach the target" in person.told


def test_a_step_that_is_not_built_leaves_nothing_behind(build, conn, modules_dir):
    bad = propose_spec(name="Bad Name")
    build([bad, bad, bad], brief=only_step("s1"))
    assert rows(conn, "modules") == [] and rows(conn, "step_modules") == []
    assert not (modules_dir / "monthly_surplus").exists()


