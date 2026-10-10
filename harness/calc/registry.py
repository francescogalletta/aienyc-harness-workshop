"""The registry of tested modules, and the build record of each calculation step (SPEC 4.1 to 4.4).

A module is registered only through `register`, which re-checks everything
itself: the files, the safety check, the spec, the worked examples and a
passing test run on exactly these files. It also stores the fingerprint of the
plan's step the module was built for, so a change to the plan makes it stale.

The build record (`build_steps`) holds what the last build or adoption of a
step gave. `step_status` works out `built`, `not_built`, `stale` or `none`
from it, the files and the plan; `build_view` is the step's `build` key of the
plan state document (ARCHITECTURE.md 3.3).
"""
import hashlib
import json
import keyword
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .. import db
from ..config import load_config
from ..grounding.brief import step_fingerprint
from .added import ADDED_PREFIX, list_added_steps
from .safety import check_code
from .values import TYPES, from_json

MIN_CONFIRMED = 2       # worked examples a module needs before it is registered
FILES = ("spec.json", "golden.json", "module.py", "tests.py")
SPEC_KEYS = ("name", "description", "step_id", "method", "formula", "inputs", "output")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
INPUT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def module_dir(name: str) -> Path:
    """The folder of a module (SPEC 5.4)."""
    return load_config().modules_dir / name


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_spec(spec) -> list[str]:
    """Return what is wrong with a spec. An empty list means it is acceptable (SPEC 5.4)."""
    if not isinstance(spec, dict):
        return ["the spec must be an object"]
    missing = [f"missing: {key}" for key in SPEC_KEYS if key not in spec]
    if missing:
        return missing

    errors = []
    if not isinstance(spec["name"], str) or not NAME.match(spec["name"]):
        errors.append("name must be snake_case, start with a letter and be at most 40 characters")
    for key in ("description", "step_id", "method", "formula"):
        if not _text(spec[key]):
            errors.append(f"{key} must be a non-empty string")

    inputs = spec["inputs"]
    if not isinstance(inputs, list) or not inputs:
        errors.append("inputs must be a non-empty list")
        inputs = []
    seen = set()
    for number, item in enumerate(inputs, start=1):
        if not isinstance(item, dict) or not {"name", "type", "description"} <= item.keys():
            errors.append(f"input {number} must be an object with name, type and description")
            continue
        name = item["name"]
        if not isinstance(name, str) or not INPUT_NAME.match(name) or keyword.iskeyword(name):
            errors.append(f"input name '{name}' must be snake_case and not a Python keyword")
        elif name in seen:
            errors.append(f"input names must be unique, but '{name}' appears twice")
        else:
            seen.add(name)
        if item["type"] not in TYPES:
            errors.append(f"input '{name}': type must be one of {', '.join(TYPES)}")
        if not _text(item["description"]):
            errors.append(f"input '{name}': description must be a non-empty string")

    output = spec["output"]
    if (not isinstance(output, dict) or output.get("type") not in TYPES
            or not _text(output.get("description"))):
        errors.append("output must be an object with a type and a non-empty description")
    return errors


def input_problems(spec: dict, inputs) -> list[str]:
    """Say whether a set of inputs fits a spec (SPEC 5.4). An empty list means it fits."""
    if not isinstance(inputs, dict):
        return ["the inputs must be an object"]
    names = [item["name"] for item in spec["inputs"]]
    problems = [f"missing input '{name}'" for name in names if name not in inputs]
    problems += [f"unexpected input '{name}'" for name in inputs if name not in names]
    for item in spec["inputs"]:
        if item["name"] in inputs:
            try:
                from_json(inputs[item["name"]], item["type"])
            except ValueError as error:
                problems.append(f"input '{item['name']}': {error}")
    return problems


def fingerprint(folder) -> str | None:
    """The SHA-256 of a module's four files, or None if the folder or a file is missing (SPEC 5.4)."""
    folder = Path(folder)
    digest = hashlib.sha256()
    for name in FILES:
        path = folder / name
        if not path.is_file():
            return None
        data = path.read_bytes()
        digest.update(f"{name}\n{len(data)}\n".encode("utf-8"))
        digest.update(data)
    return digest.hexdigest()


def _module(conn, row) -> dict:
    steps = [r["step_id"] for r in conn.execute(
        "SELECT step_id FROM step_modules WHERE module = ? ORDER BY step_id", (row["name"],))]
    return {"name": row["name"], "fingerprint": row["fingerprint"], "spec": json.loads(row["spec"]),
            "test_run_id": row["test_run_id"], "registered_at": row["registered_at"], "steps": steps,
            "step_fingerprint": row["step_fingerprint"]}


def get_module(conn, name) -> dict | None:
    """The registered module, or None."""
    row = conn.execute("SELECT * FROM modules WHERE name = ?", (name,)).fetchone()
    return _module(conn, row) if row else None


def list_modules(conn) -> list[dict]:
    """Every registered module, ordered by name."""
    return [_module(conn, row) for row in conn.execute("SELECT * FROM modules ORDER BY name")]


def step_map(conn) -> dict[str, str]:
    """Step id to module name, ordered by step id."""
    return {row["step_id"]: row["module"]
            for row in conn.execute("SELECT * FROM step_modules ORDER BY step_id")}


def file_status(conn, name: str) -> str:
    """`missing`, `unchanged` or `changed`, by comparing the files with the registered fingerprint."""
    module = get_module(conn, name)
    if module is None:
        raise ValueError(f"There is no registered module called '{name}'.")
    now = fingerprint(module_dir(name))
    if now is None:
        return "missing"
    return "unchanged" if now == module["fingerprint"] else "changed"


def map_step(conn, step_id: str, name: str) -> None:
    """Say which module carries out a step. The module must be registered."""
    if get_module(conn, name) is None:
        raise ValueError(f"There is no registered module called '{name}'.")
    conn.execute("INSERT INTO step_modules (step_id, module) VALUES (?, ?)"
                 " ON CONFLICT(step_id) DO UPDATE SET module = excluded.module", (step_id, name))
    conn.commit()


def _read_json(path: Path, what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"{what} is not valid JSON: {error}") from None


def register(conn, name: str, *, step_id: str, test_run_id: int, session_id: str,
             step_fingerprint: str = "") -> str:
    """Register a module, if its files and its passing test run all check out (SPEC 5.5).

    Returns the fingerprint. Raises ValueError with a plain reason at the first failure.
    """
    folder = module_dir(name)
    absent = [file for file in FILES if not (folder / file).is_file()]
    if absent:
        raise ValueError(f"'{name}' is missing files: {', '.join(absent)}")

    problems = check_code((folder / "module.py").read_text(encoding="utf-8"))
    problems += check_code((folder / "tests.py").read_text(encoding="utf-8"), also_allow=("module",))
    if problems:
        raise ValueError(f"the code of '{name}' is not allowed: {'; '.join(problems)}")

    spec = _read_json(folder / "spec.json", "spec.json")
    errors = validate_spec(spec)
    if errors:
        raise ValueError(f"the spec of '{name}' is not acceptable: {'; '.join(errors)}")
    if spec["name"] != name:
        raise ValueError(f"the spec is for '{spec['name']}', not '{name}'")

    golden = _read_json(folder / "golden.json", "golden.json")
    if not isinstance(golden, list) or len(golden) < MIN_CONFIRMED:
        raise ValueError(f"'{name}' needs at least {MIN_CONFIRMED} confirmed worked examples")

    run = conn.execute("SELECT * FROM test_runs WHERE id = ?", (test_run_id,)).fetchone()
    if run is None:
        raise ValueError(f"there is no test run {test_run_id}")
    if run["module"] != name:
        raise ValueError(f"test run {test_run_id} is for '{run['module']}', not '{name}'")
    if not run["passed"]:
        raise ValueError(f"test run {test_run_id} did not pass")
    current = fingerprint(folder)
    if run["fingerprint"] != current:
        raise ValueError(f"the files of '{name}' are not the ones test run {test_run_id} tested")

    with conn:      # one transaction
        conn.execute(
            "INSERT INTO modules (name, fingerprint, spec, test_run_id, registered_at, session_id,"
            " step_fingerprint) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET fingerprint = excluded.fingerprint, spec = excluded.spec,"
            " test_run_id = excluded.test_run_id, registered_at = excluded.registered_at,"
            " session_id = excluded.session_id, step_fingerprint = excluded.step_fingerprint",
            (name, current, json.dumps(spec), test_run_id, _now(), session_id, step_fingerprint or ""))
        conn.execute("INSERT INTO step_modules (step_id, module) VALUES (?, ?)"
                     " ON CONFLICT(step_id) DO UPDATE SET module = excluded.module", (step_id, name))
    db.record_event(conn, session_id=session_id, kind="build.registered", actor="harness",
                    payload={"module": name, "step": step_id, "fingerprint": current,
                             "test_run_id": test_run_id})
    return current


# --- The plan's steps, as layer 2 sees them ---

def plan_fingerprint(conn, brief: dict | None, step_id: str) -> str | None:
    """The fingerprint of a step as the plan has it now (SPEC 4.4), or None when the plan has no such step.

    A step of the brief uses `brief.step_fingerprint`; an added step (`added_<n>`) is hashed the same way
    from its row, and never changes."""
    if step_id.startswith(ADDED_PREFIX):
        step = next((each for each in list_added_steps(conn) if each["id"] == step_id), None)
        if step is None:
            return None
        canonical = {key: step[key] for key in ("kind", "method", "formula", "needs", "produces")}
        return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode("utf-8")).hexdigest()
    return step_fingerprint(brief, step_id) if brief else None


def calculation_steps(conn, brief: dict | None) -> list[dict]:
    """The calculation steps in plan order (the brief's, then the added ones), as dicts with `id`, `name`,
    `kind`, `method`, `formula`, `needs`, `produces` (and `reason` for an added step)."""
    steps = [*(brief or {}).get("process", []), *list_added_steps(conn)]
    return [step for step in steps if step.get("kind") == "calculation"]


def find_step(conn, brief: dict | None, step_id: str) -> dict | None:
    return next((step for step in calculation_steps(conn, brief) if step["id"] == step_id), None)


def module_for_step(conn, step_id: str) -> str | None:
    """The registered module that carries out a step, or None."""
    return step_map(conn).get(step_id)


# --- Build records (SPEC 4.2) ---

def get_build(conn, step_id: str) -> dict | None:
    """The build record of a step, decoded, or None."""
    row = conn.execute("SELECT * FROM build_steps WHERE step_id = ?", (step_id,)).fetchone()
    if row is None:
        return None
    return {"step_id": row["step_id"], "status": row["status"], "module": row["module"],
            "spec": json.loads(row["spec"]) if row["spec"] else None,
            "departures": json.loads(row["departures"]), "departures_confirmed": bool(row["departures_confirmed"]),
            "examples": json.loads(row["examples"]), "disagreement": json.loads(row["disagreement"]),
            "reason": row["reason"], "step_fingerprint": row["step_fingerprint"], "ts": row["ts"]}


def save_build(conn, step_id: str, *, status: str, module=None, spec=None, departures=(),
               departures_confirmed=False, examples=(), disagreement=(), reason="", step_fingerprint="") -> None:
    """Write the whole build record of a step, replacing the one before."""
    if status not in ("built", "not_built"):
        raise ValueError(f"a build record is built or not_built, not {status!r}")
    conn.execute(
        "INSERT INTO build_steps (step_id, status, module, spec, departures, departures_confirmed, examples,"
        " disagreement, reason, step_fingerprint, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(step_id) DO UPDATE SET status = excluded.status, module = excluded.module,"
        " spec = excluded.spec, departures = excluded.departures,"
        " departures_confirmed = excluded.departures_confirmed, examples = excluded.examples,"
        " disagreement = excluded.disagreement, reason = excluded.reason,"
        " step_fingerprint = excluded.step_fingerprint, ts = excluded.ts",
        (step_id, status, module, json.dumps(spec) if spec is not None else None, json.dumps(list(departures)),
         int(bool(departures_confirmed)), json.dumps(list(examples)), json.dumps(list(disagreement)), reason,
         step_fingerprint or "", _now()))
    conn.commit()


def update_build(conn, step_id: str, **changes) -> None:
    """Change some fields of an existing build record."""
    record = get_build(conn, step_id)
    if record is None:
        raise ValueError(f"step {step_id} has no build record")
    fields = {key: record[key] for key in ("status", "module", "spec", "departures", "departures_confirmed",
                                          "examples", "disagreement", "reason", "step_fingerprint")}
    fields.update(changes)
    save_build(conn, step_id, **fields)


STALE_PLAN = "the step changed in the plan"
STALE_FILES = "its files changed"


def step_status(conn, brief: dict | None, step_id: str) -> tuple[str, str]:
    """(status, reason) of a calculation step: `none`, `built`, `not_built` or `stale` (SPEC 4.4).

    Stale: built, but the plan's step fingerprint differs from the one stored when it was built, or the
    module's files changed or are gone. `building` is not stored: see `builder.building_step`."""
    record = get_build(conn, step_id)
    if record is None:
        module = module_for_step(conn, step_id)
        if module is None:
            return "none", ""
        stored = get_module(conn, module)["step_fingerprint"]
    elif record["status"] == "not_built":
        return "not_built", record["reason"]
    else:
        module, stored = record["module"], record["step_fingerprint"]
    if module is None or get_module(conn, module) is None or file_status(conn, module) != "unchanged":
        return "stale", STALE_FILES
    if stored and plan_fingerprint(conn, brief, step_id) != stored:
        return "stale", STALE_PLAN
    return "built", ""


def latest_test_run(conn, name: str) -> dict | None:
    row = conn.execute("SELECT * FROM test_runs WHERE module = ? ORDER BY id DESC LIMIT 1", (name,)).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "ts": row["ts"], "passed": bool(row["passed"]), "report": json.loads(row["report"]),
            "reason": row["reason"]}


def _code(name: str | None) -> dict | None:
    """The two code files of a module folder, else of its staging folder (a build that did not pass)."""
    if not name:
        return None
    for folder in (module_dir(name), load_config().modules_dir / "_build" / name):
        if (folder / "module.py").is_file() and (folder / "tests.py").is_file():
            return {"module_py": (folder / "module.py").read_text(encoding="utf-8"),
                    "tests_py": (folder / "tests.py").read_text(encoding="utf-8")}
    return None


def build_view(conn, brief: dict | None, step_id: str, *, building: bool = False) -> dict:
    """The `build` key of a calculation step in the plan state document (ARCHITECTURE.md 3.3)."""
    status, reason = step_status(conn, brief, step_id)
    record = get_build(conn, step_id) or {}
    module = record.get("module") or module_for_step(conn, step_id)
    spec = record.get("spec")
    if spec is None and module and get_module(conn, module):
        spec = get_module(conn, module)["spec"]
    examples = record.get("examples")
    if examples is None and module and (module_dir(module) / "golden.json").is_file():
        examples = examples_from_golden(module_dir(module) / "golden.json")
    examples = examples or []
    named = module or (spec or {}).get("name")
    run = latest_test_run(conn, named) if named else None
    report = (run or {}).get("report") or {}
    tests = report.get("tests") or []
    golden = report.get("golden") or []
    departures = record.get("departures") or []
    return {
        "status": "building" if building else status,
        "module": module if module and get_module(conn, module) else None,
        "examples": len(golden) if run else len([each for each in examples if each.get("checked_by")]),
        "tests": len(tests), "passing": sum(1 for each in tests if each.get("passed")),
        "examples_passing": sum(1 for each in golden if each.get("passed")),
        "reason": "" if building else reason,
        "plan_check": ({"departures": departures, "confirmed": bool(record.get("departures_confirmed"))}
                       if departures else None),
        "spec": ({key: spec[key] for key in ("formula", "inputs", "output") if key in spec} if spec else None),
        "example_list": examples,
        "disagreement": (record.get("disagreement") or []) if status == "not_built" and not building else [],
        "code": _code(named),
        "tested_at": run["ts"] if run else None,
    }


def examples_from_golden(path) -> list[dict]:
    """The Example list (ARCHITECTURE.md 3.3) of a golden.json file; an unreadable file gives none."""
    try:
        golden = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(golden, list):
        return []
    return [{"n": n, "inputs": each.get("inputs", {}), "expected": each.get("expected"),
             "working": each.get("working", ""),
             "checked_by": each.get("checked_by") if each.get("checked_by") in ("second_pass", "you") else None,
             "second_pass": None}
            for n, each in enumerate(golden, start=1) if isinstance(each, dict)]
