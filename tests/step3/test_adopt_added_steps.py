"""SPEC 6.3 (step 3.3) and 6.6: an added step is re-created when its module is adopted, and `add_step` can keep an id."""
import json

import pytest

import step3_helpers as s3
from step3_helpers import ADOPTED_STEP, adopted_line, h, refused_line, result, run_adopt, with_spec

SESSION = h.SESSION


def added_rows(conn):
    return h.rows(conn, "added_steps")


# ---- re-creating the step on adoption ----------------------------------------------------------------

def test_an_added_step_that_is_not_known_is_re_created_with_its_id(adopt, added, conn, brief, modules_dir):
    spec = json.loads(h.yearly_files("added_3")["spec.json"])
    s3.yearly_folder(modules_dir, "added_3")
    results, person = run_adopt(conn, brief, "yes", session_id="adopt-session")
    assert results == [result("yearly_cost", "added_3")]
    assert person.told[-1] == "yearly_cost -> added_3 (not in the brief) (adopted)"
    [row] = added_rows(conn)
    assert row["id"] == 3 and row["session_id"] == "adopt-session"
    assert (row["name"], row["formula"], row["needs"], row["produces"], row["reason"]) == (
        spec["description"], spec["formula"], "monthly", spec["output"]["description"],
        ADOPTED_STEP.format(module="yearly_cost"))
    assert added.list_added_steps(conn) == [{
        "id": "added_3", "name": spec["description"], "kind": "calculation", "method": "arithmetic",
        "formula": spec["formula"], "needs": ["monthly"], "produces": spec["output"]["description"],
        "reason": "Re-created from the module 'yearly_cost' when it was adopted."}]


def test_the_needs_are_the_input_names_with_spaces_joined_by_commas(adopt, added, conn, brief, modules_dir):
    s3.months_folder(modules_dir, "added_2")                      # inputs: target, monthly_saving
    run_adopt(conn, brief, "yes")
    [step] = added.list_added_steps(conn)
    assert step["needs"] == ["target, monthly saving"] and step["id"] == "added_2"


def test_the_events_in_order_when_the_step_is_re_created(adopt, conn, brief, modules_dir):
    s3.yearly_folder(modules_dir, "added_1")
    run_adopt(conn, brief, "yes")
    assert [k for k, _, _ in h.events(conn)] == [
        "calc.adopt_decision", "calc.tests_run", "calc.module_registered", "calc.step_added", "calc.module_adopted"]
    [(_, actor, payload)] = h.events(conn, "calc.step_added")
    assert actor == "harness" and payload["step"]["id"] == "added_1" and payload["step"]["method"] == "arithmetic"
    assert payload["step"]["reason"] == ADOPTED_STEP.format(module="yearly_cost")


def test_the_module_is_mapped_to_the_re_created_step_and_the_process_holds_it(adopt, registry, added, conn, brief, modules_dir):
    s3.yearly_folder(modules_dir, "added_1")
    run_adopt(conn, brief, "yes")
    assert registry.step_map(conn) == {"added_1": "yearly_cost"}
    assert [s["id"] for s in added.process_steps(conn, brief)] == ["s1", "s2", "s3", "added_1"]


def test_an_added_step_the_database_knows_is_used_as_it_is(adopt, added, conn, brief, modules_dir):
    known = h.add_new_step(conn, session_id="earlier")
    s3.yearly_folder(modules_dir, "added_1")
    results, _ = run_adopt(conn, brief, "yes")
    assert results == [result("yearly_cost", "added_1")]
    assert added.list_added_steps(conn) == [known]
    assert h.events(conn, "calc.step_added")[0][2] == {"step": known}              # only the one that was added before
    assert len(h.events(conn, "calc.step_added")) == 1
    assert "calc.module_adopted" in [k for k, _, _ in h.events(conn)]


def test_a_brief_step_is_never_re_created(adopt, conn, brief, modules_dir):
    s3.surplus_folder(modules_dir)
    run_adopt(conn, brief, "yes")
    assert added_rows(conn) == [] and h.events(conn, "calc.step_added") == []


def test_other_added_steps_do_not_stop_a_missing_one_from_being_re_created(adopt, added, conn, brief, modules_dir):
    h.add_new_step(conn)                                              # added_1 is known
    s3.yearly_folder(modules_dir, "added_4")                          # added_4 is not
    run_adopt(conn, brief, "yes")
    assert [s["id"] for s in added.list_added_steps(conn)] == ["added_1", "added_4"]
    assert [r["id"] for r in added_rows(conn)] == [1, 4]


def test_later_added_steps_are_numbered_after_the_highest_id_used(adopt, conn, brief, modules_dir):
    s3.yearly_folder(modules_dir, "added_7")
    run_adopt(conn, brief, "yes")
    assert h.add_new_step(conn)["id"] == "added_8"


def test_two_modules_for_two_added_steps(adopt, added, conn, brief, modules_dir):
    s3.yearly_folder(modules_dir, "added_2")
    s3.months_folder(modules_dir, "added_1")
    results, person = run_adopt(conn, brief, "yes")
    assert [(r["module"], r["step"], r["outcome"]) for r in results] == [
        ("months_to_goal", "added_1", "adopted"), ("yearly_cost", "added_2", "adopted")]
    assert sorted(s["id"] for s in added.list_added_steps(conn)) == ["added_1", "added_2"]
    assert [k for k, _, _ in h.events(conn)].count("calc.step_added") == 2


# ---- a module that fails never leaves a step behind ----------------------------------------------------------

def test_a_module_that_fails_its_tests_does_not_re_create_its_step(adopt, added, conn, brief, modules_dir):
    s3.put_module(modules_dir, {**h.yearly_files("added_5"), "module.py": "def calculate(monthly):\n    return monthly\n"})
    results, _ = run_adopt(conn, brief, "yes")
    assert results[0]["outcome"] == "not_adopted"
    assert added.list_added_steps(conn) == [] and h.events(conn, "calc.step_added") == []


def test_a_module_that_register_refuses_does_not_re_create_its_step(adopt, added, conn, brief, modules_dir):
    s3.put_module(modules_dir, {**h.yearly_files("added_5"), "module.py": "import os\n\n" + h.YEARLY_PY})
    results, _ = run_adopt(conn, brief, "yes")
    assert results[0]["outcome"] == "not_adopted"
    assert added.list_added_steps(conn) == []


def test_a_declined_adoption_re_creates_nothing(adopt, added, conn, brief, modules_dir):
    s3.yearly_folder(modules_dir, "added_5")
    run_adopt(conn, brief, "no")
    assert added.list_added_steps(conn) == []


# ---- add_step with a step_id (SPEC 6.6) ------------------------------------------------------------------------

def add(conn, **options):
    from harness.calc import added
    return added.add_step(conn, name="n", formula="f", needs="x", produces="p", reason="r", session_id=SESSION,
                          **options)


def test_add_step_keeps_a_given_id(conn):
    step = add(conn, step_id="added_5")
    assert step["id"] == "added_5" and step == h.added_step(5, name="n", formula="f", needs=["x"], produces="p", reason="r")
    assert [r["id"] for r in added_rows(conn)] == [5]
    assert h.events(conn, "calc.step_added") == [("calc.step_added", "harness", {"step": step})]


def test_without_a_step_id_the_numbering_is_as_before(conn):
    assert [add(conn)["id"] for _ in range(2)] == ["added_1", "added_2"]
    assert add(conn, step_id=None)["id"] == "added_3"


def test_later_steps_are_numbered_after_the_highest_id_used(conn):
    add(conn, step_id="added_5")
    assert add(conn)["id"] == "added_6"
    add(conn, step_id="added_2")                                       # a lower number does not lower the next one
    assert add(conn)["id"] == "added_7"


@pytest.mark.parametrize("step_id", ["added_0", "added_01", "added_", "added_x", "added_-1", "s1", "Added_1",
                                     "added_1a", "xadded_1", "", "added_ 1"])
def test_a_step_id_that_does_not_match_is_refused(conn, step_id):
    with pytest.raises(ValueError):
        add(conn, step_id=step_id)
    assert added_rows(conn) == [] and h.events(conn, "calc.step_added") == []


def test_a_step_id_that_is_taken_is_refused(conn):
    add(conn, step_id="added_5")
    with pytest.raises(ValueError):
        add(conn, step_id="added_5")
    assert [r["id"] for r in added_rows(conn)] == [5] and len(h.events(conn, "calc.step_added")) == 1


def test_a_step_id_equal_to_an_id_given_by_numbering_is_refused(conn):
    add(conn)
    with pytest.raises(ValueError):
        add(conn, step_id="added_1")

