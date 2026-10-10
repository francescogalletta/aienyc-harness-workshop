"""SPEC 5.6: the gate is the only way a calculation runs."""
import json
import subprocess

import pytest

import step2_helpers as h
from harness import db
from step2_helpers import (BAD_INPUTS, FILES_CHANGED, NO_EXPECTATION, NOT_REGISTERED, RUN_FAILED, SESSION,
                           SLOW_MONTHS_PY, SURPLUS_TESTS, TESTS_FAIL, WRONG_SURPLUS_PY, WRONG_SURPLUS_TESTS, events,
                           expected_fingerprint, insert_registered, install, install_months, install_surplus,
                           months_files, payloads, rows, surplus_files, write_files)

GOOD_INPUTS = {"income": "5000", "spending": 3000.5}
EXPECTATION = "about 2,000, because income is above spending"


def call(gate, conn, name="monthly_surplus", inputs=None, assumptions=(), expected=EXPECTATION):
    return gate.call(conn, name, GOOD_INPUTS if inputs is None else inputs,
                     assumptions=[] if assumptions == () else assumptions, expected=expected, session_id=SESSION)


def refusal(gate, conn, **kwargs):
    """The reason a call is refused; also checks it was recorded as the event."""
    inputs = kwargs.get("inputs", GOOD_INPUTS)
    before = len(rows(conn, "calc_runs"))
    with pytest.raises(gate.Refused) as refused:
        call(gate, conn, **kwargs)
    reason = str(refused.value)
    [(_, actor, payload)] = events(conn, "calc.refused")[-1:]
    assert actor == "harness" and payload == {"module": kwargs.get("name", "monthly_surplus"), "reason": reason,
                                              "inputs": inputs}
    assert len(rows(conn, "calc_runs")) == before
    return reason


def test_the_timeout_is_thirty_seconds(gate):
    assert gate.TIMEOUT == 30


@pytest.mark.parametrize("name", ["NOT_REGISTERED", "FILES_CHANGED", "NO_EXPECTATION", "BAD_INPUTS", "TESTS_FAIL",
                                  "RUN_FAILED"])
def test_the_fixed_strings(gate, name):
    assert getattr(gate, name) == getattr(h, name)


def test_refused_is_an_exception(gate):
    assert issubclass(gate.Refused, Exception)


# ---- run_tests -------------------------------------------------------------------------------

def test_run_tests_passing(gate, conn, modules_dir):
    install_surplus(conn)
    folder = modules_dir / "monthly_surplus"
    result = gate.run_tests(conn, "monthly_surplus", reason="status", session_id=SESSION)
    assert set(result) == {"test_run_id", "passed", "fingerprint", "report"}
    assert result["passed"] is True and result["fingerprint"] == expected_fingerprint(folder)
    assert result["report"]["passed"] is True
    assert [t["name"] for t in result["report"]["tests"]] == ["test_a_shortfall", "test_a_surplus"]
    assert [g["index"] for g in result["report"]["golden"]] == [1, 2, 3]


def test_run_tests_records_a_row_and_an_event(gate, conn):
    install_surplus(conn)
    result = gate.run_tests(conn, "monthly_surplus", reason="status", session_id="the-session")
    row = [r for r in rows(conn, "test_runs") if r["id"] == result["test_run_id"]][0]
    assert (row["module"], row["reason"], row["passed"], row["fingerprint"]) == (
        "monthly_surplus", "status", 1, result["fingerprint"])
    assert json.loads(row["report"]) == result["report"]
    [(kind, actor, payload)] = [e for e in events(conn, "calc.tests_run") if e[2]["reason"] == "status"]
    assert actor == "harness"
    assert payload == {"module": "monthly_surplus", "test_run_id": result["test_run_id"], "reason": "status",
                       "passed": True, "fingerprint": result["fingerprint"]}
    assert db.list_events(conn, kind="calc.tests_run")[-1]["session_id"] == "the-session"


@pytest.mark.parametrize("reason", ["build", "gate", "status", "adopt"])
def test_run_tests_records_the_reason_it_is_given(gate, conn, reason):
    """SPEC 5.5 and 6.6: a test run's reason is build, gate or status, and also adopt."""
    install_surplus(conn)
    result = gate.run_tests(conn, "monthly_surplus", reason=reason, session_id=SESSION)
    [row] = [r for r in rows(conn, "test_runs") if r["id"] == result["test_run_id"]]
    assert row["reason"] == reason
    assert [p["reason"] for p in payloads(conn, "calc.tests_run")][-1] == reason


def test_run_tests_fails_when_a_worked_example_fails(gate, conn, modules_dir):
    write_files(modules_dir / "monthly_surplus", surplus_files(module_py=WRONG_SURPLUS_PY, tests_py=WRONG_SURPLUS_TESTS))
    result = gate.run_tests(conn, "monthly_surplus", reason="build", session_id=SESSION)
    assert result["passed"] is False and result["report"]["passed"] is False
    assert rows(conn, "test_runs")[0]["passed"] == 0


def test_run_tests_can_test_another_folder(gate, conn, tmp_path):
    staging = write_files(tmp_path / "elsewhere", surplus_files())
    result = gate.run_tests(conn, "monthly_surplus", reason="build", session_id=SESSION, folder=staging)
    assert result["passed"] is True and result["fingerprint"] == expected_fingerprint(staging)


def test_run_tests_with_missing_files_does_not_start_the_runner(gate, conn, modules_dir, monkeypatch):
    folder = write_files(modules_dir / "monthly_surplus", surplus_files())
    (folder / "tests.py").unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("the runner must not be started")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = gate.run_tests(conn, "monthly_surplus", reason="gate", session_id=SESSION)
    assert result["passed"] is False
    assert result["report"] == {"tests": [], "golden": [], "passed": False, "error": "files missing"}
    assert rows(conn, "test_runs")[0]["fingerprint"] == ""


def test_run_tests_gives_the_runners_own_error_when_it_has_no_report(gate, conn, modules_dir):
    write_files(modules_dir / "monthly_surplus", surplus_files(module_py="raise ValueError('broken at import')\n"))
    report = gate.run_tests(conn, "monthly_surplus", reason="build", session_id=SESSION)["report"]
    assert report == {"tests": [], "golden": [], "passed": False, "error": "ValueError: broken at import"}


def test_run_tests_when_the_runner_gives_no_readable_answer(gate, conn, modules_dir):
    dying = "import sys\nsys.stderr.write('it died\\nwith two lines')\nraise SystemExit(3)\n"
    write_files(modules_dir / "monthly_surplus", surplus_files(module_py=dying))
    report = gate.run_tests(conn, "monthly_surplus", reason="build", session_id=SESSION)["report"]
    assert report["passed"] is False and report["tests"] == [] and report["golden"] == []
    assert report["error"].startswith("the runner gave no readable answer: ")
    assert "it died" in report["error"] and "with two lines" in report["error"] and "\n" not in report["error"]


def test_run_tests_that_take_too_long_are_stopped(gate, conn, modules_dir, monkeypatch):
    monkeypatch.setattr(gate, "TIMEOUT", 1)
    forever = SURPLUS_TESTS + "\n\ndef test_forever():\n    for _ in range(10 ** 12):\n        pass\n"
    write_files(modules_dir / "monthly_surplus", surplus_files(tests_py=forever))
    result = gate.run_tests(conn, "monthly_surplus", reason="build", session_id=SESSION)
    assert result["passed"] is False
    assert result["report"]["tests"] == [] and "did not finish within" in result["report"]["error"]
    assert result["report"]["error"].startswith("the tests did not finish within ")


# ---- call: the way through -------------------------------------------------------------------

def test_a_call_runs_the_module_and_returns_the_result(gate, conn, modules_dir):
    install_surplus(conn)
    result = call(gate, conn)
    assert set(result) == {"run_id", "module", "output", "test_run_id", "fingerprint"}
    assert result["module"] == "monthly_surplus" and result["output"] == "1999.5"
    assert result["fingerprint"] == expected_fingerprint(modules_dir / "monthly_surplus")


def test_a_call_makes_a_fresh_test_run_for_the_gate(gate, conn):
    install_surplus(conn)
    result = call(gate, conn)
    gate_runs = [r for r in rows(conn, "test_runs") if r["reason"] == "gate"]
    assert [r["id"] for r in gate_runs] == [result["test_run_id"]]
    assert gate_runs[0]["passed"] == 1 and gate_runs[0]["fingerprint"] == result["fingerprint"]


def test_a_call_records_a_calc_run_exactly_as_given(gate, conn):
    install_surplus(conn)
    result = call(gate, conn, assumptions=["Income is steady."], expected="a bit under 2,000")
    [row] = rows(conn, "calc_runs")
    assert row["id"] == result["run_id"] and row["session_id"] == SESSION and row["module"] == "monthly_surplus"
    assert json.loads(row["inputs"]) == GOOD_INPUTS               # not converted, not completed
    assert json.loads(row["assumptions"]) == ["Income is steady."]
    assert row["expected"] == "a bit under 2,000"
    assert json.loads(row["output"]) == "1999.5"
    assert row["fingerprint"] == result["fingerprint"] and row["test_run_id"] == result["test_run_id"]


def test_a_call_records_an_event(gate, conn):
    install_surplus(conn)
    result = call(gate, conn)
    assert events(conn, "calc.run") == [("calc.run", "harness", {
        "module": "monthly_surplus", "run_id": result["run_id"], "test_run_id": result["test_run_id"],
        "inputs": GOOD_INPUTS, "output": "1999.5"})]


def test_assumptions_may_be_empty(gate, conn):
    install_surplus(conn)
    assert call(gate, conn, assumptions=[])["output"] == "1999.5"


# ---- call: the refusals, one by one ----------------------------------------------------------

def test_refused_when_not_registered(gate, conn):
    assert refusal(gate, conn, name="ghost") == NOT_REGISTERED.format(name="ghost")


def test_refused_when_the_files_have_changed(gate, conn, modules_dir):
    install_surplus(conn)
    (modules_dir / "monthly_surplus" / "module.py").write_text(WRONG_SURPLUS_PY, encoding="utf-8")
    assert refusal(gate, conn) == FILES_CHANGED.format(name="monthly_surplus")


def test_refused_when_a_file_is_missing(gate, conn, modules_dir):
    install_surplus(conn)
    (modules_dir / "monthly_surplus" / "tests.py").unlink()
    assert refusal(gate, conn) == FILES_CHANGED.format(name="monthly_surplus")


@pytest.mark.parametrize("assumptions, expected", [
    ("one sentence", EXPECTATION), (None, EXPECTATION), ([1, 2], EXPECTATION), ([["nested"]], EXPECTATION),
    ([], ""), ([], None), ([], 5), ([], "   "), ([], " \n\t "),
])
def test_refused_without_an_expectation(gate, conn, assumptions, expected):
    install_surplus(conn)
    with pytest.raises(gate.Refused) as refused:
        gate.call(conn, "monthly_surplus", GOOD_INPUTS, assumptions=assumptions, expected=expected, session_id=SESSION)
    assert str(refused.value) == NO_EXPECTATION.format(name="monthly_surplus")
    assert events(conn, "calc.refused")[-1][2]["reason"] == str(refused.value)


def test_refused_when_the_inputs_do_not_fit(gate, conn):
    install_surplus(conn)
    inputs = {"income": "abc", "other": "1"}
    reason = refusal(gate, conn, inputs=inputs)
    assert reason == BAD_INPUTS.format(name="monthly_surplus", problems="; ".join([
        "missing input 'spending'", "unexpected input 'other'", "input 'income': expected a number, got 'abc'"]))


def test_refused_when_the_inputs_are_not_an_object(gate, conn):
    install_surplus(conn)
    assert refusal(gate, conn, inputs=["5000"]) == BAD_INPUTS.format(
        name="monthly_surplus", problems="the inputs must be an object")


def test_refused_when_the_tests_fail_right_now(gate, conn, modules_dir):
    """The files are the registered ones, but they do not pass: put in the registry without the checks."""
    folder = write_files(modules_dir / "monthly_surplus",
                         surplus_files(module_py=WRONG_SURPLUS_PY, tests_py=WRONG_SURPLUS_TESTS))
    insert_registered(conn, folder, "s1")
    assert refusal(gate, conn) == TESTS_FAIL.format(name="monthly_surplus")
    [gate_run] = [r for r in rows(conn, "test_runs") if r["reason"] == "gate"]
    assert gate_run["passed"] == 0


# ---- call: the order of the checks -----------------------------------------------------------

def test_not_registered_comes_before_everything(gate, conn):
    reason = refusal(gate, conn, name="ghost", inputs=[], assumptions="x", expected="")
    assert reason == NOT_REGISTERED.format(name="ghost")


def test_changed_files_come_before_the_expectation(gate, conn, modules_dir):
    install_surplus(conn)
    (modules_dir / "monthly_surplus" / "module.py").write_text(WRONG_SURPLUS_PY, encoding="utf-8")
    assert refusal(gate, conn, inputs={}, expected="") == FILES_CHANGED.format(name="monthly_surplus")


def test_the_expectation_comes_before_the_inputs(gate, conn):
    install_surplus(conn)
    assert refusal(gate, conn, inputs={}, expected="") == NO_EXPECTATION.format(name="monthly_surplus")


def test_the_inputs_come_before_the_tests_and_cost_no_test_run(gate, conn, modules_dir):
    folder = write_files(modules_dir / "monthly_surplus",
                         surplus_files(module_py=WRONG_SURPLUS_PY, tests_py=WRONG_SURPLUS_TESTS))
    insert_registered(conn, folder, "s1")
    reason = refusal(gate, conn, inputs={})
    assert reason.startswith(BAD_INPUTS.format(name="monthly_surplus", problems=""))
    assert [r for r in rows(conn, "test_runs") if r["reason"] == "gate"] == []


# ---- call: a module that fails when it runs --------------------------------------------------

def test_a_module_that_raises_is_a_refusal_with_its_own_event(gate, conn):
    install(conn, months_files(), "s3")
    with pytest.raises(gate.Refused) as refused:
        gate.call(conn, "months_to_goal", {"target": "100", "monthly_saving": "0"},
                  assumptions=[], expected="a number of months", session_id=SESSION)
    error = "ValueError: monthly_saving must be above zero"
    assert str(refused.value) == RUN_FAILED.format(name="months_to_goal", error=error)
    assert payloads(conn, "calc.run_failed") == [
        {"module": "months_to_goal", "error": error, "inputs": {"target": "100", "monthly_saving": "0"}}]
    assert events(conn, "calc.run_failed")[0][1] == "harness"
    assert events(conn, "calc.refused") == []                   # a failed run is not a refusal event
    assert rows(conn, "calc_runs") == [] and events(conn, "calc.run") == []


def test_a_module_that_takes_too_long_is_a_refusal(gate, conn, monkeypatch):
    install(conn, months_files(module_py=SLOW_MONTHS_PY), "s3")
    monkeypatch.setattr(gate, "TIMEOUT", 1)
    with pytest.raises(gate.Refused) as refused:
        gate.call(conn, "months_to_goal", {"target": "100", "monthly_saving": "1"},
                  assumptions=[], expected="a number of months", session_id=SESSION)
    assert str(refused.value) == RUN_FAILED.format(name="months_to_goal",
                                                   error="the module did not finish within 1 seconds")
    assert events(conn, "calc.refused") == []
    assert len(payloads(conn, "calc.run_failed")) == 1 and rows(conn, "calc_runs") == []


def test_every_call_of_a_good_module_leaves_its_own_rows(gate, conn):
    install_surplus(conn)
    install_months(conn)
    first = call(gate, conn)
    second = call(gate, conn)
    assert first["run_id"] != second["run_id"] and first["test_run_id"] != second["test_run_id"]
    assert len(rows(conn, "calc_runs")) == 2


def test_a_module_folder_keeps_to_its_four_files_after_every_runner_process(gate, conn, modules_dir):
    install_surplus(conn)
    folder = modules_dir / "monthly_surplus"
    gate.run_tests(conn, "monthly_surplus", reason="status", session_id=SESSION)
    call(gate, conn)
    assert sorted(p.name for p in folder.iterdir()) == ["golden.json", "module.py", "spec.json", "tests.py"]
