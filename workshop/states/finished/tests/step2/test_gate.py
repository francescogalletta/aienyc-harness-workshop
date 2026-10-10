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


# ---- run_tests -------------------------------------------------------------------------------


# ---- call: the way through -------------------------------------------------------------------

def test_a_call_runs_the_module_and_returns_the_result(gate, conn, modules_dir):
    install_surplus(conn)
    result = call(gate, conn)
    assert set(result) == {"run_id", "module", "output", "test_run_id", "fingerprint"}
    assert result["module"] == "monthly_surplus" and result["output"] == "1999.5"
    assert result["fingerprint"] == expected_fingerprint(modules_dir / "monthly_surplus")


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


# ---- call: the refusals, one by one ----------------------------------------------------------

def test_refused_when_not_registered(gate, conn):
    assert refusal(gate, conn, name="ghost") == NOT_REGISTERED.format(name="ghost")


def test_refused_when_the_files_have_changed(gate, conn, modules_dir):
    install_surplus(conn)
    (modules_dir / "monthly_surplus" / "module.py").write_text(WRONG_SURPLUS_PY, encoding="utf-8")
    assert refusal(gate, conn) == FILES_CHANGED.format(name="monthly_surplus")


@pytest.mark.parametrize("assumptions, expected", [
    ("one sentence", EXPECTATION), ([], "   "),
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


def test_refused_when_the_tests_fail_right_now(gate, conn, modules_dir):
    """The files are the registered ones, but they do not pass: put in the registry without the checks."""
    folder = write_files(modules_dir / "monthly_surplus",
                         surplus_files(module_py=WRONG_SURPLUS_PY, tests_py=WRONG_SURPLUS_TESTS))
    insert_registered(conn, folder, "s1")
    assert refusal(gate, conn) == TESTS_FAIL.format(name="monthly_surplus")
    [gate_run] = [r for r in rows(conn, "test_runs") if r["reason"] == "gate"]
    assert gate_run["passed"] == 0


# ---- call: the order of the checks -----------------------------------------------------------


def test_the_expectation_comes_before_the_inputs(gate, conn):
    install_surplus(conn)
    assert refusal(gate, conn, inputs={}, expected="") == NO_EXPECTATION.format(name="monthly_surplus")


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


