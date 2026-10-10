"""SPEC 6.3: the checks `adopt` makes on each folder, in their order, with their reasons."""
import json

import pytest

import step3_helpers as s3
from step3_helpers import (ADOPT_BAD_EXAMPLES, ADOPT_BAD_SPEC, ADOPT_MISSING, ADOPT_NO_STEP, ADOPT_STEP_TAKEN,
                           dump, h, listing, refused_line, renamed_files, result, run_adopt, with_spec)

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
    assert list(event[2]) == ["module", "step", "reason"]
    assert event[2]["step"] == outcome["step"]
    after = [len(h.events(conn)), len(h.rows(conn, "test_runs")), len(h.rows(conn, "modules"))]
    assert after == [before[0] + 1, before[1], before[2]]          # one event, no test run, nothing registered
    return outcome, folder


# ---- the four files ----------------------------------------------------------------------------------

@pytest.mark.parametrize("missing", [("spec.json",), ("golden.json",), ("module.py",), ("tests.py",),
                                     ("golden.json", "tests.py"), ("spec.json", "module.py", "tests.py"), FILES])
def test_missing_files_are_listed_in_the_order_of_5_4(conn, brief, modules_dir, missing):
    files = {name: text for name, text in h.surplus_files("s1").items() if name not in missing}
    outcome, _ = refused(conn, brief, modules_dir, files)
    assert outcome["reason"] == ADOPT_MISSING.format(files=", ".join(missing))
    if "spec.json" in missing:
        assert outcome["step"] is None


def test_an_empty_folder_misses_all_four(conn, brief, modules_dir):
    (modules_dir / "empty").mkdir(parents=True)
    results, person = run_adopt(conn, brief)
    assert results == [result("empty", None, "not_adopted", "missing files: spec.json, golden.json, module.py, tests.py")]
    assert person.told == [refused_line("empty", "missing files: spec.json, golden.json, module.py, tests.py")]


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


@pytest.mark.parametrize("fault", sorted(BAD_SPECS))
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


@pytest.mark.parametrize("fault", sorted(BAD_EXAMPLES))
def test_golden_json_must_be_a_list_of_at_least_two_objects(conn, brief, modules_dir, fault):
    outcome, _ = refused(conn, brief, modules_dir, {**h.surplus_files("s1"), "golden.json": BAD_EXAMPLES[fault]})
    assert outcome["reason"] == ADOPT_BAD_EXAMPLES == "golden.json does not hold at least 2 worked examples"
    assert outcome["step"] == "s1"                                        # the spec was read


# ---- the step ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("step_id", ["ghost", "s2", "S1", "s1 ", "added_0", "added_01", "added_", "added_x", "added_-1",
                                     "added_1.5", "added_1a", "xadded_1"])
def test_the_step_must_be_a_calculation_step_of_the_process_or_an_added_id(conn, brief, modules_dir, step_id):
    files = with_spec(h.surplus_files("s1"), step_id=step_id)
    outcome, _ = refused(conn, brief, modules_dir, files)
    assert outcome["reason"] == ADOPT_NO_STEP.format(step=step_id) == f"the process has no calculation step '{step_id}'"
    assert outcome["step"] == step_id


def test_a_judgment_step_is_not_a_calculation_step(conn, brief, modules_dir):
    assert next(s for s in brief["process"] if s["id"] == "s2")["kind"] == "judgment"
    outcome, _ = refused(conn, brief, modules_dir, with_spec(h.surplus_files("s1"), step_id="s2"))
    assert outcome["reason"] == "the process has no calculation step 's2'"


@pytest.mark.parametrize("step_id", ["added_1", "added_7", "added_10", "added_999"])
def test_an_added_id_is_accepted_even_when_no_such_step_is_known(adopt, conn, brief, modules_dir, step_id):
    s3.put_module(modules_dir, with_spec(h.surplus_files("s1"), step_id=step_id))
    results, person = run_adopt(conn, brief, "no")
    assert person.told[1] == listing("monthly_surplus", step_id)
    assert results[0]["reason"] == s3.REASON_DECLINED


def test_an_added_step_that_exists_in_the_database_is_accepted_too(conn, brief, modules_dir):
    h.add_new_step(conn)
    s3.put_module(modules_dir, with_spec(h.surplus_files("s1"), step_id="added_1"))
    _, person = run_adopt(conn, brief, "no")
    assert person.told[1] == "  monthly_surplus for step added_1 (not in the brief): 3 worked examples (accepted, accepted, accepted)"


# ---- the step must be free --------------------------------------------------------------------------------------------

def test_a_step_that_has_another_working_module_is_not_taken_over(conn, brief, modules_dir):
    h.install_surplus(conn, "s1")
    outcome, _ = refused(conn, brief, modules_dir, renamed_files(h.surplus_files("s1"), "other_surplus"),
                         name="other_surplus")
    assert outcome["reason"] == ADOPT_STEP_TAKEN.format(step="s1", other="monthly_surplus")
    assert outcome["reason"] == "step s1 already has the module 'monthly_surplus'"
    assert outcome["step"] == "s1"


def test_the_step_is_shown_with_its_label_when_it_is_an_added_step(conn, brief, modules_dir):
    h.add_new_step(conn)
    h.install_yearly(conn, "added_1")
    outcome, _ = refused(conn, brief, modules_dir, renamed_files(h.yearly_files("added_1"), "other_yearly"),
                         name="other_yearly")
    assert outcome["reason"] == "step added_1 (not in the brief) already has the module 'yearly_cost'"


@pytest.mark.parametrize("damage", ["changed", "missing"])
def test_a_module_whose_files_are_not_unchanged_does_not_hold_its_step(adopt, conn, brief, modules_dir, damage):
    h.install_surplus(conn, "s1")
    if damage == "changed":
        (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    else:
        (modules_dir / "monthly_surplus" / "tests.py").unlink()
    s3.put_module(modules_dir, renamed_files(h.surplus_files("s1"), "z_surplus"))
    # monthly_surplus is a candidate itself, and sorts first; z_surplus is the later folder for step s1.
    results, person = run_adopt(conn, brief, "no")
    assert [r["module"] for r in results] == ["monthly_surplus", "z_surplus"]
    if damage == "changed":
        assert results[0]["reason"] == s3.REASON_DECLINED
        assert results[1]["reason"] == ADOPT_STEP_TAKEN.format(step="s1", other="monthly_surplus")
    else:
        assert results[0]["reason"] == ADOPT_MISSING.format(files="tests.py")      # it fails its own check first
        assert results[1]["reason"] == s3.REASON_DECLINED


def test_the_changed_module_itself_is_not_another_module(adopt, conn, brief, modules_dir):
    h.install_surplus(conn, "s1")
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    results, _ = run_adopt(conn, brief, "no")
    assert results[0]["reason"] == s3.REASON_DECLINED


def test_of_two_folders_for_one_step_the_first_by_name_wins(conn, brief, modules_dir):
    s3.put_module(modules_dir, renamed_files(h.surplus_files("s1"), "a_surplus"))
    s3.put_module(modules_dir, renamed_files(h.surplus_files("s1"), "b_surplus"))
    results, person = run_adopt(conn, brief, "yes")
    taken = "step s1 already has the module 'a_surplus'"
    assert results == [result("a_surplus", "s1"), result("b_surplus", "s1", "not_adopted", taken)]
    assert person.told == [refused_line("b_surplus", taken), s3.ADOPT_INTRO, listing("a_surplus", "s1"),
                           s3.adopted_line("a_surplus", "s1")]
    assert h.payloads(conn, "calc.adopt_decision")[0]["modules"] == ["a_surplus"]
    assert [k for k, _, _ in h.events(conn)][:2] == ["calc.adopt_refused", "calc.adopt_decision"]


def test_an_earlier_folder_that_failed_a_check_does_not_hold_the_step(conn, brief, modules_dir):
    s3.put_module(modules_dir, {**renamed_files(h.surplus_files("s1"), "a_surplus"), "golden.json": "[]"})
    s3.put_module(modules_dir, renamed_files(h.surplus_files("s1"), "b_surplus"))
    results, _ = run_adopt(conn, brief, "yes")
    assert [(r["module"], r["outcome"]) for r in results] == [("a_surplus", "not_adopted"), ("b_surplus", "adopted")]
    assert results[0]["reason"] == ADOPT_BAD_EXAMPLES


def test_an_earlier_folder_that_passed_the_checks_holds_the_step_even_if_its_tests_fail(conn, brief, modules_dir):
    s3.put_module(modules_dir, {**renamed_files(h.surplus_files("s1"), "a_surplus"), "module.py": h.WRONG_SURPLUS_PY})
    s3.put_module(modules_dir, renamed_files(h.surplus_files("s1"), "b_surplus"))
    results, _ = run_adopt(conn, brief, "yes")
    assert results == [result("a_surplus", "s1", "not_adopted", s3.REASON_TESTS),
                       result("b_surplus", "s1", "not_adopted", "step s1 already has the module 'a_surplus'")]


# ---- the order of the checks -------------------------------------------------------------------------------------------

def test_missing_files_come_before_everything_else(conn, brief, modules_dir):
    files = {"spec.json": "{ not json", "module.py": h.SURPLUS_PY, "tests.py": h.SURPLUS_TESTS}
    outcome, _ = refused(conn, brief, modules_dir, files)
    assert outcome["reason"] == ADOPT_MISSING.format(files="golden.json")


def test_a_bad_spec_comes_before_bad_examples(conn, brief, modules_dir):
    files = {**h.surplus_files("s1"), "spec.json": BAD_SPECS["wrong_name"], "golden.json": "[]"}
    outcome, _ = refused(conn, brief, modules_dir, files)
    assert outcome["reason"] == ADOPT_BAD_SPEC


def test_bad_examples_come_before_the_step(conn, brief, modules_dir):
    files = {**with_spec(h.surplus_files("s1"), step_id="ghost"), "golden.json": "[]"}
    outcome, _ = refused(conn, brief, modules_dir, files)
    assert outcome["reason"] == ADOPT_BAD_EXAMPLES


def test_the_step_comes_before_the_step_being_taken(conn, brief, modules_dir):
    h.install_surplus(conn, "s1")
    files = with_spec(renamed_files(h.surplus_files("s1"), "other"), step_id="s2")
    outcome, _ = refused(conn, brief, modules_dir, files, name="other")
    assert outcome["reason"] == ADOPT_NO_STEP.format(step="s2")


def test_nothing_is_asked_when_every_folder_is_refused(conn, brief, modules_dir):
    h.write_files(modules_dir / "a", {"module.py": "x = 1\n"})
    h.write_files(modules_dir / "b", {"module.py": "x = 1\n"})
    results, person = run_adopt(conn, brief)                   # a question would fail: the person has no answers
    assert [r["outcome"] for r in results] == ["not_adopted", "not_adopted"]
    assert person.asked == [] and s3.ADOPT_INTRO not in person.told
    assert [k for k, _, _ in h.events(conn)] == ["calc.adopt_refused", "calc.adopt_refused"]
    assert [p["module"] for p in h.payloads(conn, "calc.adopt_refused")] == ["a", "b"]
