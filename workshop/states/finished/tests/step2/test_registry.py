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


# ---- validate_spec ---------------------------------------------------------------------------

def test_a_good_spec_has_no_problems(registry):
    assert registry.validate_spec(good_spec()) == []


def test_each_absent_key_is_named_in_order(registry):
    assert registry.validate_spec({}) == [f"missing: {key}" for key in (
        "name", "description", "step_id", "method", "formula", "inputs", "output")]
    spec = good_spec()
    del spec["formula"], spec["name"]
    assert registry.validate_spec(spec) == ["missing: name", "missing: formula"]


# ---- input_problems --------------------------------------------------------------------------


def test_missing_inputs_are_named_in_spec_order(registry):
    assert registry.input_problems(surplus_spec(), {}) == ["missing input 'income'", "missing input 'spending'"]


# ---- fingerprint -----------------------------------------------------------------------------

def test_the_fingerprint_is_the_sha256_of_the_four_files(registry, tmp_path):
    folder = write_files(tmp_path / "m", surplus_files())
    assert registry.fingerprint(folder) == expected_fingerprint(folder)
    assert len(registry.fingerprint(folder)) == 64


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


def test_check_3_the_spec_must_pass_validate_spec(registry, conn):
    assert refuses(registry, conn, **{"spec.json": dump(good_spec(name="Bad Name"))})


@pytest.mark.parametrize("golden", [surplus_examples()[:1]])
def test_check_4_at_least_two_examples(registry, conn, golden):
    assert refuses(registry, conn, **{"golden.json": dump(golden_of(golden))})


def test_check_5_the_test_run_must_have_passed(registry, conn):
    assert refuses(registry, conn, run_passed=False)


def test_check_5_the_test_run_must_be_for_these_files(registry, conn):
    assert refuses(registry, conn, run_fingerprint="0" * 64)


@pytest.mark.parametrize("first, second", [
    ("unsafe", "spec"),
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
