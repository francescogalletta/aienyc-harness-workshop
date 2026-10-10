"""SPEC 5.13: the checks `adopt` makes on each folder, in their order, with their reasons."""
import json

import pytest

import step2_helpers as h
from step2_adopt_helpers import (ADOPT_BAD_EXAMPLES, ADOPT_BAD_SPEC, ADOPT_MISSING, ADOPT_NO_STEP,
                                 ADOPT_STEP_TAKEN, dump, refused_line, renamed_files, run_adopt, with_spec)

FILES = ("spec.json", "golden.json", "module.py", "tests.py")


def refused(conn, brief, modules_dir, files, name="monthly_surplus"):
    """Adopt one folder that holds `files` (a dict, or raw text per file name). Returns (result, folder).

    Checks that the folder was refused, said so, recorded it, and that nothing else changed.
    """
    folder = h.write_files(modules_dir / name, files)
    before = [len(h.events(conn)), len(h.rows(conn, "test_runs")), len(h.rows(conn, "modules"))]
    results, person = run_adopt(conn, brief)             # nobody is asked: a refused folder is never adoptable
    [outcome] = results
    assert outcome["outcome"] == "not_adopted" and outcome["module"] == name
    assert person.log == [("say", refused_line(name, outcome["reason"]))]
    [event] = h.events(conn, "calc.adopt_refused")
    assert event[1] == "harness"
    assert event[2]["module"] == name and event[2]["reason"] == outcome["reason"]
    assert event[2]["step"] == outcome["step"]
    after = [len(h.events(conn)), len(h.rows(conn, "test_runs")), len(h.rows(conn, "modules"))]
    assert after == [before[0] + 1, before[1], before[2]]          # one event, no test run, nothing registered
    return outcome, folder


# ---- the four files ----------------------------------------------------------------------------------

@pytest.mark.parametrize("missing", [("golden.json", "tests.py")])
def test_missing_files_are_listed_in_the_order_of_5_4(conn, brief, modules_dir, missing):
    files = {name: text for name, text in h.surplus_files("s1").items() if name not in missing}
    outcome, _ = refused(conn, brief, modules_dir, files)
    assert outcome["reason"] == ADOPT_MISSING.format(files=", ".join(missing))
    if "spec.json" in missing:
        assert outcome["step"] is None


# ---- the spec --------------------------------------------------------------------------------------------

def spec_with(**changes):
    return dump({**json.loads(h.surplus_files("s1")["spec.json"]), **changes})


BAD_SPECS = {
    "not_json": "{ not json",
    "empty_file": "",
    "a_list": "[]",
    "an_empty_object": "{}",
    "wrong_name": spec_with(name="monthly_savings"),
    "name_not_snake_case": spec_with(name="Monthly Surplus"),
    "no_inputs": spec_with(inputs=[]),
    "bad_output_type": spec_with(output={"type": "money", "description": "x"}),
    "step_id_empty": spec_with(step_id=""),
    "description_missing": dump({k: v for k, v in json.loads(h.surplus_files("s1")["spec.json"]).items()
                                 if k != "description"}),
}


@pytest.mark.parametrize("fault", ["wrong_name"])
def test_a_spec_that_is_not_valid_for_the_folder(conn, brief, modules_dir, fault):
    outcome, _ = refused(conn, brief, modules_dir, {**h.surplus_files("s1"), "spec.json": BAD_SPECS[fault]})
    assert outcome["reason"] == ADOPT_BAD_SPEC
    if fault in ("not_json", "empty_file"):
        assert outcome["step"] is None                                    # the spec could not be read


# ---- the worked examples -----------------------------------------------------------------------------------

BAD_EXAMPLES = {
    "not_json": "{ not json",
    "an_object": "{}",
    "empty_list": "[]",
    "only_one": dump([{"inputs": {"income": "1", "spending": "1"}, "expected": "0"}]),
    "not_objects": dump(["a", "b"]),
    "one_object_and_a_number": dump([{"inputs": {}, "expected": "0"}, 5]),
    "text": '"two examples"',
}


@pytest.mark.parametrize("fault", ["only_one"])
def test_golden_json_must_be_a_list_of_at_least_two_objects(conn, brief, modules_dir, fault):
    outcome, _ = refused(conn, brief, modules_dir, {**h.surplus_files("s1"), "golden.json": BAD_EXAMPLES[fault]})
    assert outcome["reason"] == ADOPT_BAD_EXAMPLES == "golden.json does not hold at least 2 worked examples"
    assert outcome["step"] == "s1"                                        # the spec was read


# ---- the step ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("step_id", ["ghost"])
def test_the_step_must_be_a_calculation_step_of_the_process_or_an_added_id(conn, brief, modules_dir, step_id):
    files = with_spec(h.surplus_files("s1"), step_id=step_id)
    outcome, _ = refused(conn, brief, modules_dir, files)
    assert outcome["reason"] == ADOPT_NO_STEP.format(step=step_id) == f"the process has no calculation step '{step_id}'"
    assert outcome["step"] == step_id


# ---- the step must be free --------------------------------------------------------------------------------------------

def test_a_step_that_has_another_working_module_is_not_taken_over(conn, brief, modules_dir):
    h.install_surplus(conn, "s1")
    outcome, _ = refused(conn, brief, modules_dir, renamed_files(h.surplus_files("s1"), "other_surplus"),
                         name="other_surplus")
    assert outcome["reason"] == ADOPT_STEP_TAKEN.format(step="s1", other="monthly_surplus")
    assert outcome["reason"] == "step s1 already has the module 'monthly_surplus'"
    assert outcome["step"] == "s1"


# ---- the order of the checks -------------------------------------------------------------------------------------------
