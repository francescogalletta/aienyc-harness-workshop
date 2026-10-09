"""The registry of tested modules (SPEC 5.4 and 5.5).

A module is registered only through `register`, which re-checks everything
itself: the files, the safety check, the spec, the worked examples and a
passing test run on exactly these files.
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
            "test_run_id": row["test_run_id"], "registered_at": row["registered_at"], "steps": steps}


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


def register(conn, name: str, *, step_id: str, test_run_id: int, session_id: str) -> str:
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
            "INSERT INTO modules (name, fingerprint, spec, test_run_id, registered_at, session_id)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET fingerprint = excluded.fingerprint, spec = excluded.spec,"
            " test_run_id = excluded.test_run_id, registered_at = excluded.registered_at,"
            " session_id = excluded.session_id",
            (name, current, json.dumps(spec), test_run_id, _now(), session_id))
        conn.execute("INSERT INTO step_modules (step_id, module) VALUES (?, ?)"
                     " ON CONFLICT(step_id) DO UPDATE SET module = excluded.module", (step_id, name))
    db.record_event(conn, session_id=session_id, kind="calc.module_registered", actor="harness",
                    payload={"module": name, "step": step_id, "fingerprint": current,
                             "test_run_id": test_run_id})
    return current
