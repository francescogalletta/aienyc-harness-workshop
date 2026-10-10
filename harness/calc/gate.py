"""The gate: the only way a calculation runs (SPEC 4.4; version 1 5.6).

It refuses a module that is not registered, whose files have changed, whose
step changed in the plan (stale) or ended not built at its last build, whose
tests fail right now, or whose inputs do not fit its spec. Every test run,
calculation and refusal is recorded.
"""
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .. import db
from ..config import load_config
from ..grounding.brief import load_brief
from .registry import file_status, fingerprint, get_build, get_module, input_problems, module_dir, plan_fingerprint

TIMEOUT = 30        # seconds, for every runner process
RUNNER = Path(__file__).with_name("runner.py")

NOT_REGISTERED = "There is no registered module called '{name}'."
FILES_CHANGED = "The files of '{name}' are not the ones that passed their tests, so '{name}' must be built again."
STALE = "The step of '{name}' changed in the plan, so '{name}' must be built again."
NOT_BUILT = "The step of '{name}' is not built: its code and a worked example disagree, or it was left unfinished."
NO_EXPECTATION = ("Before running '{name}', give the assumptions (a list of sentences, which may be empty) "
                  "and say what you expect the result to be.")
BAD_INPUTS = "The inputs do not fit '{name}': {problems}"
TESTS_FAIL = "The tests of '{name}' do not pass right now, so it will not run."
RUN_FAILED = "'{name}' stopped with an error: {error}"


class Refused(Exception):
    """The gate will not run this calculation. The message says why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _run(folder, request: dict, what: str) -> dict:
    """Run the runner on a folder. Always returns an answer: {"ok": False, "error": ...} if it gave none."""
    try:
        done = subprocess.run([sys.executable, "-I", str(RUNNER), str(folder)], input=json.dumps(request),
                              capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{what} did not finish within {TIMEOUT} seconds"}
    finally:
        shutil.rmtree(Path(folder) / "__pycache__", ignore_errors=True)     # keep the folder to its four files
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        answer = None
    if not isinstance(answer, dict) or "ok" not in answer:
        return {"ok": False, "error": f"the runner gave no readable answer: {_one_line(done.stderr)}"}
    return answer


def run_tests(conn, name: str, *, reason: str, session_id: str, folder=None) -> dict:
    """Run the unit tests and worked examples of a module and record the run (SPEC 4.1)."""
    folder = Path(folder) if folder is not None else module_dir(name)
    found = fingerprint(folder)
    if found is None:
        report = {"tests": [], "golden": [], "passed": False, "error": "files missing"}
    else:
        answer = _run(folder, {"action": "test"}, "the tests")
        if answer["ok"] and "report" in answer:
            report = answer["report"]
        else:
            report = {"tests": [], "golden": [], "passed": False, "error": answer.get("error", "")}
    passed = bool(report.get("passed"))
    fingerprint_text = found or ""
    cursor = conn.execute(
        "INSERT INTO test_runs (ts, module, fingerprint, reason, passed, report) VALUES (?, ?, ?, ?, ?, ?)",
        (_now(), name, fingerprint_text, reason, int(passed), json.dumps(report)))
    conn.commit()
    test_run_id = cursor.lastrowid
    db.record_event(conn, session_id=session_id, kind="build.tests_run", actor="harness",
                    payload={"module": name, "test_run_id": test_run_id, "reason": reason,
                             "passed": passed, "fingerprint": fingerprint_text})
    return {"test_run_id": test_run_id, "passed": passed, "fingerprint": fingerprint_text, "report": report}


def step_refusal(conn, module: dict) -> str | None:
    """Why the plan stops a registered module from running, or None (SPEC 4.4).

    Stale: the plan's step it was built for has a fingerprint other than the stored one, or is gone.
    Not built: the step's last build ended not built. With no confirmed plan, or no stored fingerprint,
    nothing is refused here."""
    step_id = module["spec"].get("step_id", "")
    record = get_build(conn, step_id)
    if record is not None and record["status"] == "not_built":
        return NOT_BUILT.format(name=module["name"])
    brief = load_brief(load_config().brief_dir)
    if brief is None or not module.get("step_fingerprint"):
        return None
    if plan_fingerprint(conn, brief, step_id) != module["step_fingerprint"]:
        return STALE.format(name=module["name"])
    return None


def _refuse(conn, session_id, name, inputs, message):
    db.record_event(conn, session_id=session_id, kind="calc.refused", actor="harness",
                    payload={"module": name, "reason": message, "inputs": inputs})
    raise Refused(message)


def call(conn, name: str, inputs, *, assumptions, expected, session_id: str) -> dict:
    """Run a registered module, if every check passes (SPEC 4.4). Raises `Refused` otherwise."""
    module = get_module(conn, name)
    if module is None:
        _refuse(conn, session_id, name, inputs, NOT_REGISTERED.format(name=name))
    if file_status(conn, name) != "unchanged":
        _refuse(conn, session_id, name, inputs, FILES_CHANGED.format(name=name))
    refusal = step_refusal(conn, module)
    if refusal:
        _refuse(conn, session_id, name, inputs, refusal)
    if (not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions)
            or not isinstance(expected, str) or not expected.strip()):
        _refuse(conn, session_id, name, inputs, NO_EXPECTATION.format(name=name))
    problems = input_problems(module["spec"], inputs)
    if problems:
        _refuse(conn, session_id, name, inputs, BAD_INPUTS.format(name=name, problems="; ".join(problems)))
    tests = run_tests(conn, name, reason="gate", session_id=session_id)
    if not tests["passed"]:
        _refuse(conn, session_id, name, inputs, TESTS_FAIL.format(name=name))

    answer = _run(module_dir(name), {"action": "call", "inputs": inputs}, "the module")
    if not answer["ok"] or "output" not in answer:
        error = answer.get("error", "")
        db.record_event(conn, session_id=session_id, kind="calc.run_failed", actor="harness",
                        payload={"module": name, "error": error, "inputs": inputs})
        raise Refused(RUN_FAILED.format(name=name, error=error))

    output = answer["output"]
    cursor = conn.execute(
        "INSERT INTO calc_runs (ts, session_id, module, fingerprint, test_run_id, inputs, assumptions,"
        " expected, output) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (_now(), session_id, name, module["fingerprint"], tests["test_run_id"], json.dumps(inputs),
         json.dumps(assumptions), expected, json.dumps(output)))
    conn.commit()
    run_id = cursor.lastrowid
    db.record_event(conn, session_id=session_id, kind="calc.run", actor="harness",
                    payload={"module": name, "run_id": run_id, "test_run_id": tests["test_run_id"],
                             "inputs": inputs, "output": output})
    return {"run_id": run_id, "module": name, "output": output,
            "test_run_id": tests["test_run_id"], "fingerprint": module["fingerprint"]}
