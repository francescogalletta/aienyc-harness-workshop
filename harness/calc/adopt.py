"""Adoption on load (SPEC 4.6): module folders already on disk become usable without asking.

Each folder in `modules_dir` that is not registered with unchanged files, and
whose spec names a calculation step of the plan (or an `added_<n>` step, which
is re-created), has its tests and worked examples run here. On a pass it is
registered with the step's fingerprint and gets a build record from its
files; on a failure the step is `not_built`, "its tests do not pass here".
Nothing here calls a model or asks the person.
"""
import json
import re

from .. import db
from ..config import load_config
from .added import ADDED_PREFIX, add_step, list_added_steps
from .gate import run_tests
from .registry import (calculation_steps, examples_from_golden, file_status, get_module, plan_fingerprint,
                       register, save_build, step_map, validate_spec)

ADDED_STEP = re.compile(r"^added_[1-9][0-9]*$")
ADOPTED_STEP = "Re-created from the module '{module}' when it was adopted."
REASON_TESTS = "its tests do not pass here"


def _spec(path):
    try:
        spec = json.loads((path / "spec.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return spec if isinstance(spec, dict) and isinstance(spec.get("step_id"), str) else None


def candidates(conn, brief) -> list[tuple[str, str]]:
    """(folder name, step id) of each folder adoption would try, in name order: not registered with
    unchanged files, its spec readable and naming a calculation step of the plan or an added step that
    no other unchanged module carries out. At most one folder per step: the first by name."""
    folder = load_config().modules_dir
    if not folder.is_dir():
        return []
    steps = {step["id"] for step in calculation_steps(conn, brief)}
    mapped = step_map(conn)
    found, claimed = [], set()
    for path in sorted(folder.iterdir()):
        name = path.name
        if not path.is_dir() or name.startswith(("_", ".")):
            continue
        if get_module(conn, name) and file_status(conn, name) == "unchanged":
            continue
        spec = _spec(path)
        step = spec["step_id"] if spec else None
        if step is None or step in claimed or not (step in steps or ADDED_STEP.match(step)):
            continue
        other = mapped.get(step)
        if other is not None and other != name and file_status(conn, other) == "unchanged":
            continue
        claimed.add(step)
        found.append((name, step))
    return found


def adopt_folders(conn, brief, *, session_id: str) -> list[dict]:
    """Adopt every candidate folder. Returns one {"module", "step", "outcome": adopted | not_built,
    "reason"} each, and records `build.adopted` for each."""
    results = []
    folder = load_config().modules_dir
    for name, step in candidates(conn, brief):
        path = folder / name
        spec = _spec(path)
        examples = examples_from_golden(path / "golden.json")
        run = run_tests(conn, name, reason="adopt", session_id=session_id)
        problem = "" if run["passed"] and not validate_spec(spec) and spec.get("name") == name else REASON_TESTS
        added = step.startswith(ADDED_PREFIX)
        if not problem and added and step not in {each["id"] for each in list_added_steps(conn)}:
            add_step(conn, name=spec["description"], formula=spec["formula"],     # keep the process whole
                     needs=", ".join(item["name"].replace("_", " ") for item in spec["inputs"]),
                     produces=spec["output"]["description"], reason=ADOPTED_STEP.format(module=name),
                     session_id=session_id, step_id=step)
        fingerprint = plan_fingerprint(conn, brief, step) or ""
        if not problem:
            try:
                register(conn, name, step_id=step, test_run_id=run["test_run_id"], session_id=session_id,
                         step_fingerprint=fingerprint)
            except ValueError as error:
                problem = str(error)
        if problem:
            if not added or step in {each["id"] for each in list_added_steps(conn)}:
                save_build(conn, step, status="not_built", spec=spec if not validate_spec(spec) else None,
                           examples=examples, reason=REASON_TESTS, step_fingerprint=fingerprint)
        else:
            save_build(conn, step, status="built", module=name, spec=spec, examples=examples,
                       step_fingerprint=fingerprint)
        outcome = "not_built" if problem else "adopted"
        db.record_event(conn, session_id=session_id, kind="build.adopted", actor="harness",
                        payload={"module": name, "step": step, "outcome": outcome, "reason": problem,
                                 "test_run_id": run["test_run_id"]})
        results.append({"module": name, "step": step, "outcome": outcome, "reason": problem})
    return results
