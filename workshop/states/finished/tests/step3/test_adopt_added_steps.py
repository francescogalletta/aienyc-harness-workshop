"""SPEC 6.3 (step 3.3) and 6.6: an added step is re-created when its module is adopted, and `add_step` can keep an id."""
import json


import step3_helpers as s3
from step3_helpers import ADOPTED_STEP, h, result, run_adopt

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


def test_the_module_is_mapped_to_the_re_created_step_and_the_process_holds_it(adopt, registry, added, conn, brief, modules_dir):
    s3.yearly_folder(modules_dir, "added_1")
    run_adopt(conn, brief, "yes")
    assert registry.step_map(conn) == {"added_1": "yearly_cost"}
    assert [s["id"] for s in added.process_steps(conn, brief)] == ["s1", "s2", "s3", "added_1"]


# ---- a module that fails never leaves a step behind ----------------------------------------------------------


# ---- add_step with a step_id (SPEC 6.6) ------------------------------------------------------------------------

def add(conn, **options):
    from harness.calc import added
    return added.add_step(conn, name="n", formula="f", needs="x", produces="p", reason="r", session_id=SESSION,
                          **options)
