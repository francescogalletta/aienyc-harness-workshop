"""SPEC 5.4 and 5.5: modules on disk, the spec checks, the fingerprint and the registry."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from harness import db
from harness.calc.safety import check_code
from step2_helpers import (SESSION, add_test_run, dump, events, expected_fingerprint, golden_of, months_files,
                           rows, saved_spec, surplus_examples, surplus_files, surplus_spec, write_files)


def good_spec(**changes):
    return {**saved_spec(surplus_spec(), "s1"), **changes}


# ---- configuration and tables ----------------------------------------------------------------

def test_the_modules_folder_setting(monkeypatch, tmp_path):
    from harness.config import load_config

    assert load_config().modules_dir == tmp_path / "modules"
    monkeypatch.delenv("HARNESS_MODULES_DIR")
    assert load_config().modules_dir == Path("my/modules")


def test_module_dir_follows_the_setting_at_the_time_of_the_call(registry, monkeypatch, tmp_path):
    assert registry.module_dir("savings") == tmp_path / "modules" / "savings"
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "elsewhere"))
    assert registry.module_dir("savings") == tmp_path / "elsewhere" / "savings"


def test_the_migration_creates_the_five_tables(conn):
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"test_runs", "modules", "step_modules", "calc_runs", "inputs"} <= tables
    assert "0003_calc.sql" in db.applied_migrations(conn)


# ---- validate_spec ---------------------------------------------------------------------------

def test_a_good_spec_has_no_problems(registry):
    assert registry.validate_spec(good_spec()) == []


def test_a_spec_that_is_not_an_object(registry):
    assert registry.validate_spec([]) == ["the spec must be an object"]
    assert registry.validate_spec("spec") == ["the spec must be an object"]


def test_each_absent_key_is_named_in_order(registry):
    assert registry.validate_spec({}) == [f"missing: {key}" for key in (
        "name", "description", "step_id", "method", "formula", "inputs", "output")]
    spec = good_spec()
    del spec["formula"], spec["name"]
    assert registry.validate_spec(spec) == ["missing: name", "missing: formula"]


def test_a_stage_that_finds_errors_stops_before_the_next(registry):
    spec = good_spec(name="Not Valid")
    del spec["output"]
    assert registry.validate_spec(spec) == ["missing: output"]


@pytest.mark.parametrize("name", ["Upper", "1abc", "has space", "", "a" * 41, "ünder", "_start"])
def test_a_bad_name(registry, name):
    problems = registry.validate_spec(good_spec(name=name))
    assert problems and any("name" in p for p in problems)


@pytest.mark.parametrize("name", ["a", "a" * 40, "monthly_surplus", "x1_y2"])
def test_a_good_name(registry, name):
    assert registry.validate_spec(good_spec(name=name)) == []


@pytest.mark.parametrize("key", ["description", "step_id", "method", "formula"])
@pytest.mark.parametrize("bad", ["", "   ", 5, None, ["text"]])
def test_these_keys_must_be_non_empty_strings(registry, key, bad):
    problems = registry.validate_spec(good_spec(**{key: bad}))
    assert problems and any(key in p for p in problems)


@pytest.mark.parametrize("bad", [[], "income", None, {"name": "income"}])
def test_inputs_must_be_a_non_empty_list(registry, bad):
    problems = registry.validate_spec(good_spec(inputs=bad))
    assert problems and any("inputs" in p for p in problems)


@pytest.mark.parametrize("bad", [
    "income", {"name": "a", "type": "number"}, {"name": "a", "description": "d"}, {"type": "number", "description": "d"},
])
def test_an_input_must_be_an_object_with_name_type_and_description(registry, bad):
    problems = registry.validate_spec(good_spec(inputs=[bad]))
    assert problems and any("input" in p for p in problems)


@pytest.mark.parametrize("name", ["Income", "1st", "has space", "", "class", "for", "None", "lambda"])
def test_an_input_name_must_be_snake_case_and_not_a_keyword(registry, name):
    inputs = [{"name": name, "type": "number", "description": "d"}]
    problems = registry.validate_spec(good_spec(inputs=inputs))
    assert any(f"'{name}'" in p and "name" in p for p in problems)


def test_input_names_must_be_unique(registry):
    inputs = [{"name": "a", "type": "number", "description": "d"}, {"name": "a", "type": "text", "description": "d"}]
    assert any("unique" in p for p in registry.validate_spec(good_spec(inputs=inputs)))


def test_an_input_type_must_be_one_of_the_types(registry):
    inputs = [{"name": "income", "type": "money", "description": "d"}]
    assert any("'income'" in p and "type" in p for p in registry.validate_spec(good_spec(inputs=inputs)))


@pytest.mark.parametrize("bad", ["", "  ", 3])
def test_an_input_description_must_be_a_non_empty_string(registry, bad):
    inputs = [{"name": "income", "type": "number", "description": bad}]
    assert any("'income'" in p and "description" in p for p in registry.validate_spec(good_spec(inputs=inputs)))


@pytest.mark.parametrize("bad", ["number", None, {"type": "money", "description": "d"}, {"type": "number"},
                                 {"type": "number", "description": ""}, {"description": "d"}])
def test_the_output_must_have_a_type_and_a_description(registry, bad):
    problems = registry.validate_spec(good_spec(output=bad))
    assert problems and any("output" in p for p in problems)


# ---- input_problems --------------------------------------------------------------------------

def test_inputs_that_fit(registry):
    assert registry.input_problems(surplus_spec(), {"income": "5000", "spending": 3000.5}) == []


def test_inputs_that_are_not_an_object(registry):
    assert registry.input_problems(surplus_spec(), ["5000"]) == ["the inputs must be an object"]


def test_missing_inputs_are_named_in_spec_order(registry):
    assert registry.input_problems(surplus_spec(), {}) == ["missing input 'income'", "missing input 'spending'"]


def test_extra_inputs_are_named_in_the_order_given(registry):
    problems = registry.input_problems(surplus_spec(), {"zeta": "1", "income": "1", "spending": "1", "alpha": "2"})
    assert problems == ["unexpected input 'zeta'", "unexpected input 'alpha'"]


def test_a_value_that_does_not_fit_gives_the_reason_of_from_json(registry):
    problems = registry.input_problems(surplus_spec(), {"income": "abc", "spending": "1"})
    assert problems == ["input 'income': expected a number, got 'abc'"]


def test_problems_come_missing_then_unexpected_then_bad_values(registry):
    spec = surplus_spec(inputs=[{"name": "a", "type": "number", "description": "d"},
                                {"name": "b", "type": "integer", "description": "d"},
                                {"name": "c", "type": "date", "description": "d"},
                                {"name": "d", "type": "number", "description": "d"}])
    problems = registry.input_problems(spec, {"z": "1", "d": "x", "y": "2", "b": "x"})
    assert problems[:4] == ["missing input 'a'", "missing input 'c'", "unexpected input 'z'", "unexpected input 'y'"]
    assert problems[4].startswith("input 'b': ") and problems[5].startswith("input 'd': ")
    assert len(problems) == 6


# ---- fingerprint -----------------------------------------------------------------------------

def test_the_fingerprint_is_the_sha256_of_the_four_files(registry, tmp_path):
    folder = write_files(tmp_path / "m", surplus_files())
    assert registry.fingerprint(folder) == expected_fingerprint(folder)
    assert len(registry.fingerprint(folder)) == 64


def test_the_fingerprint_does_not_depend_on_the_folder(registry, tmp_path):
    first = write_files(tmp_path / "one", surplus_files())
    second = write_files(tmp_path / "deeper" / "two", surplus_files())
    assert registry.fingerprint(first) == registry.fingerprint(second)


@pytest.mark.parametrize("name", ["spec.json", "golden.json", "module.py", "tests.py"])
def test_changing_any_file_changes_the_fingerprint(registry, tmp_path, name):
    folder = write_files(tmp_path / "m", surplus_files())
    before = registry.fingerprint(folder)
    (folder / name).write_text((folder / name).read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert registry.fingerprint(folder) != before


def test_other_files_in_the_folder_are_not_part_of_it(registry, tmp_path):
    folder = write_files(tmp_path / "m", surplus_files())
    before = registry.fingerprint(folder)
    (folder / "notes.txt").write_text("not part of it", encoding="utf-8")
    assert registry.fingerprint(folder) == before


def test_the_fingerprint_is_none_when_the_folder_or_a_file_is_missing(registry, tmp_path):
    assert registry.fingerprint(tmp_path / "nowhere") is None
    folder = write_files(tmp_path / "m", surplus_files())
    (folder / "golden.json").unlink()
    assert registry.fingerprint(folder) is None


# ---- reading the registry --------------------------------------------------------------------

def register_surplus(registry, conn, step_id="s1", files=None, name="monthly_surplus"):
    """Write the files, add a passing test run by hand and register."""
    folder = write_files(registry.module_dir(name), files or surplus_files(step_id))
    run_id = add_test_run(conn, name, expected_fingerprint(folder))
    return registry.register(conn, name, step_id=step_id, test_run_id=run_id, session_id=SESSION), run_id


def test_nothing_is_registered_to_begin_with(registry, conn):
    assert registry.get_module(conn, "monthly_surplus") is None
    assert registry.list_modules(conn) == []
    assert registry.step_map(conn) == {}


def test_a_registered_module_as_get_module_gives_it(registry, conn):
    fingerprint, run_id = register_surplus(registry, conn)
    module = registry.get_module(conn, "monthly_surplus")
    assert set(module) == {"name", "fingerprint", "spec", "test_run_id", "registered_at", "steps"}
    assert module["name"] == "monthly_surplus" and module["fingerprint"] == fingerprint
    assert module["spec"] == saved_spec(surplus_spec(), "s1")
    assert module["test_run_id"] == run_id and module["steps"] == ["s1"]


def test_list_modules_is_ordered_by_name_and_steps_are_sorted(registry, conn):
    register_surplus(registry, conn, "s1")
    register_surplus(registry, conn, "s2", files=months_files("s2"), name="months_to_goal")
    registry.map_step(conn, "s9", "monthly_surplus")
    registry.map_step(conn, "s3", "monthly_surplus")
    modules = registry.list_modules(conn)
    assert [m["name"] for m in modules] == ["monthly_surplus", "months_to_goal"]
    assert modules[0]["steps"] == ["s1", "s3", "s9"] and modules[1]["steps"] == ["s2"]


def test_step_map_is_ordered_by_step_id(registry, conn):
    register_surplus(registry, conn, "s2")
    register_surplus(registry, conn, "s10", files=months_files("s10"), name="months_to_goal")
    registry.map_step(conn, "s1", "months_to_goal")
    mapping = registry.step_map(conn)
    assert mapping == {"s1": "months_to_goal", "s10": "months_to_goal", "s2": "monthly_surplus"}
    assert list(mapping) == sorted(mapping)


def test_file_status(registry, conn):
    register_surplus(registry, conn)
    folder = registry.module_dir("monthly_surplus")
    assert registry.file_status(conn, "monthly_surplus") == "unchanged"
    (folder / "module.py").write_text("# edited\n" + (folder / "module.py").read_text(encoding="utf-8"), encoding="utf-8")
    assert registry.file_status(conn, "monthly_surplus") == "changed"
    (folder / "tests.py").unlink()
    assert registry.file_status(conn, "monthly_surplus") == "missing"


def test_file_status_of_an_unregistered_name_is_an_error(registry, conn):
    with pytest.raises(ValueError):
        registry.file_status(conn, "nothing")


def test_map_step_inserts_or_replaces_and_records_no_event(registry, conn):
    register_surplus(registry, conn, "s1")
    register_surplus(registry, conn, "s2", files=months_files("s2"), name="months_to_goal")
    before = len(db.list_events(conn))
    registry.map_step(conn, "s5", "monthly_surplus")
    registry.map_step(conn, "s5", "months_to_goal")
    assert registry.step_map(conn)["s5"] == "months_to_goal"
    assert len(db.list_events(conn)) == before


def test_map_step_needs_a_registered_module(registry, conn):
    with pytest.raises(ValueError):
        registry.map_step(conn, "s1", "nothing")


# ---- register --------------------------------------------------------------------------------

def test_register_returns_the_fingerprint_and_writes_the_rows(registry, conn):
    fingerprint, run_id = register_surplus(registry, conn)
    folder = registry.module_dir("monthly_surplus")
    assert fingerprint == expected_fingerprint(folder)
    [row] = rows(conn, "modules")
    assert row["name"] == "monthly_surplus" and row["fingerprint"] == fingerprint
    assert json.loads(row["spec"]) == saved_spec(surplus_spec(), "s1")
    assert row["test_run_id"] == run_id and row["session_id"] == SESSION
    assert datetime.fromisoformat(row["registered_at"]).utcoffset() == timedelta(0)
    assert rows(conn, "step_modules") == [{"step_id": "s1", "module": "monthly_surplus"}]


def test_register_records_an_event(registry, conn):
    fingerprint, run_id = register_surplus(registry, conn)
    assert events(conn, "calc.module_registered") == [("calc.module_registered", "harness", {
        "module": "monthly_surplus", "step": "s1", "fingerprint": fingerprint, "test_run_id": run_id})]


def test_register_again_replaces_the_row_and_keeps_the_history(registry, conn):
    register_surplus(registry, conn, "s1")
    registry.map_step(conn, "s7", "monthly_surplus")
    old_run = rows(conn, "test_runs")[0]
    folder = registry.module_dir("monthly_surplus")
    (folder / "tests.py").write_text((folder / "tests.py").read_text(encoding="utf-8") + "\n# new\n", encoding="utf-8")
    run_id = add_test_run(conn, "monthly_surplus", expected_fingerprint(folder))
    fingerprint = registry.register(conn, "monthly_surplus", step_id="s1", test_run_id=run_id, session_id="later")
    module = registry.get_module(conn, "monthly_surplus")
    assert module["fingerprint"] == fingerprint and module["test_run_id"] == run_id
    assert module["steps"] == ["s1", "s7"]                      # the other step's mapping survives the rebuild
    assert len(rows(conn, "modules")) == 1
    assert old_run in rows(conn, "test_runs")


def test_register_maps_the_step_to_the_module_even_when_another_had_it(registry, conn):
    register_surplus(registry, conn, "s1")
    register_surplus(registry, conn, "s1", files=months_files("s1"), name="months_to_goal")
    assert registry.step_map(conn) == {"s1": "months_to_goal"}


def refuses(registry, conn, run_passed=True, run_name="monthly_surplus", run_fingerprint=None, step_id="s1", **files):
    """Try to register surplus files with the given faults. Return the reason."""
    folder = write_files(registry.module_dir("monthly_surplus"), {**surplus_files(), **files})
    run_id = add_test_run(conn, run_name, run_fingerprint or expected_fingerprint(folder), passed=run_passed)
    with pytest.raises(ValueError) as error:
        registry.register(conn, "monthly_surplus", step_id=step_id, test_run_id=run_id, session_id=SESSION)
    assert rows(conn, "modules") == [] and rows(conn, "step_modules") == []
    return str(error.value)


def test_check_1_all_four_files_must_be_there(registry, conn):
    folder = write_files(registry.module_dir("monthly_surplus"), surplus_files())
    run_id = add_test_run(conn, "monthly_surplus", expected_fingerprint(folder))
    (folder / "golden.json").unlink()
    with pytest.raises(ValueError):
        registry.register(conn, "monthly_surplus", step_id="s1", test_run_id=run_id, session_id=SESSION)
    assert registry.get_module(conn, "monthly_surplus") is None


def test_check_2_unsafe_module_code_is_refused(registry, conn):
    assert refuses(registry, conn, **{"module.py": "import os\n" + surplus_files()["module.py"]})


def test_check_2_unsafe_test_code_is_refused_but_importing_module_is_fine(registry, conn):
    assert check_code(surplus_files()["tests.py"], also_allow=("module",)) == []
    assert refuses(registry, conn, **{"tests.py": surplus_files()["tests.py"] + "\nimport os\n"})


def test_check_3_the_spec_must_pass_validate_spec(registry, conn):
    assert refuses(registry, conn, **{"spec.json": dump(good_spec(name="Bad Name"))})


def test_check_3_the_spec_name_must_be_the_module_name(registry, conn):
    assert refuses(registry, conn, **{"spec.json": dump(good_spec(name="another_name"))})


@pytest.mark.parametrize("golden", [[], surplus_examples()[:1]])
def test_check_4_at_least_two_examples(registry, conn, golden):
    assert refuses(registry, conn, **{"golden.json": dump(golden_of(golden))})


def test_check_4_golden_must_be_a_list(registry, conn):
    assert refuses(registry, conn, **{"golden.json": dump({"examples": golden_of(surplus_examples())})})


def test_check_5_the_test_run_must_have_passed(registry, conn):
    assert refuses(registry, conn, run_passed=False)


def test_check_5_the_test_run_must_be_for_this_module(registry, conn):
    assert refuses(registry, conn, run_name="another_module")


def test_check_5_the_test_run_must_be_for_these_files(registry, conn):
    assert refuses(registry, conn, run_fingerprint="0" * 64)


def test_check_5_the_test_run_must_exist(registry, conn):
    write_files(registry.module_dir("monthly_surplus"), surplus_files())
    with pytest.raises(ValueError):
        registry.register(conn, "monthly_surplus", step_id="s1", test_run_id=999, session_id=SESSION)
    assert registry.get_module(conn, "monthly_surplus") is None


@pytest.mark.parametrize("first, second", [
    ("files", "unsafe"), ("unsafe", "spec"), ("spec", "golden"), ("golden", "run"),
])
def test_the_checks_run_in_order(registry, conn, tmp_path, first, second):
    """With two faults, the reason is the earlier one's: the same as when only the earlier is present."""
    def faults(*names):
        files = surplus_files()
        if "unsafe" in names:
            files["module.py"] = "import os\n" + files["module.py"]
        if "spec" in names:
            files["spec.json"] = dump(good_spec(name="another_name"))
        if "golden" in names:
            files["golden.json"] = dump(golden_of(surplus_examples()[:1]))
        folder = write_files(registry.module_dir("monthly_surplus"), files)
        if "files" in names:
            (folder / "tests.py").unlink()
        fingerprint = "0" * 64 if "run" in names else (expected_fingerprint(folder) if "files" not in names else "x")
        run_id = add_test_run(conn, "monthly_surplus", fingerprint)
        with pytest.raises(ValueError) as error:
            registry.register(conn, "monthly_surplus", step_id="s1", test_run_id=run_id, session_id=SESSION)
        return str(error.value)

    both = faults(first, second)
    assert both == faults(first)
    assert both != faults(second)
