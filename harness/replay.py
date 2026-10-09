"""Scenarios and replay (SPEC 6.4 and 6.5).

A scenario is a scripted person and what the harness must see. `run_scenario`
runs one against a model, in a scratch folder, and checks module runs and
numbers, never wording.
"""
import json
import os
import re
import shutil
import tempfile
import uuid
from datetime import date
from pathlib import Path

from . import db
from .calc.adopt import adopt
from .calc.added import step_label
from .calc.agent import run_agent
from .calc.builder import build, load_brief
from .calc.provenance import _read, unbacked
from .calc.values import same

NO_SCENARIO = "There is no scenario '{scenario}' in {folder}. The scenarios are: {names}."
NO_SCENARIOS = "There are no scenarios in {folder}."

KEYS = ("name", "kind", "description", "today", "without", "lines", "expect")
REQUIRED = ("name", "kind", "lines", "expect")
ASK_EXPECTS = ("runs", "shown", "not_shown", "max_withheld", "max_corrections")
BUILD_EXPECTS = ("steps",)
OUTCOMES = ("built", "reused", "kept", "not_built")
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPLAY_DIR = "var/replay"


def _is_date(value) -> bool:
    if not isinstance(value, str) or not DAY.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _one_number(text: str) -> bool:
    """Is the text exactly one number the number check reads: no date, no bare whole number from 0 to 12?"""
    text = text.strip()
    items = _read(text)
    return (len(items) == 1 and not items[0]["parts"] and items[0]["written"] == text
            and not items[0]["exempt"])


def validate_scenario(value, *, stem: str, brief: dict) -> list[str]:
    """Return what is wrong with a scenario. An empty list means it can run (SPEC 6.4)."""
    if not isinstance(value, dict):
        return ["the scenario must be an object"]
    missing = [f"missing: {key}" for key in REQUIRED if key not in value]
    if missing:
        return missing

    errors = [f"unknown key: {key}" for key in value if key not in KEYS]
    if not SNAKE.match(stem) or value["name"] != stem:
        errors.append(f"name must be the file name without .json, in snake_case: '{stem}'")
    kind = value["kind"]
    if kind not in ("ask", "build"):
        errors.append("kind must be ask or build")
    if "description" in value and not isinstance(value["description"], str):
        errors.append("description must be a string")
    if "today" in value:
        if kind == "build":
            errors.append("today is only for ask scenarios")
        if not _is_date(value["today"]):
            errors.append("today must be a date written YYYY-MM-DD")
    if "without" in value:
        without = value["without"]
        if not isinstance(without, list) or not all(isinstance(item, str) for item in without):
            errors.append("without must be a list of step ids")
        else:
            calculations = {step.get("id") for step in brief.get("process", []) if step.get("kind") == "calculation"}
            errors += [f"without: '{item}' is not a calculation step of the brief"
                       for item in without if item not in calculations]
    lines = value["lines"]
    if (not isinstance(lines, list) or not lines
            or not all(isinstance(line, str) and line.strip() for line in lines)):
        errors.append("lines must be a non-empty list of non-empty strings")
    errors += _expect_problems(value["expect"], kind, brief)
    return errors


def _expect_problems(expect, kind, brief) -> list[str]:
    if not isinstance(expect, dict):
        return ["expect must be an object"]
    if not expect:
        return ["expect must hold at least one expectation"]
    errors = [f"expect: unknown key: {key}" for key in expect if key not in ASK_EXPECTS + BUILD_EXPECTS]
    if kind in ("ask", "build"):
        other = BUILD_EXPECTS if kind == "ask" else ASK_EXPECTS
        errors += [f"expect.{key} is only for {'build' if kind == 'ask' else 'ask'} scenarios"
                   for key in expect if key in other]

    if "runs" in expect:
        runs = expect["runs"]
        if not isinstance(runs, list):
            errors.append("expect.runs must be a list")
        else:
            for k, entry in enumerate(runs, start=1):
                good = (isinstance(entry, dict) and set(entry) <= {"module", "inputs"}
                        and isinstance(entry.get("module"), str) and entry["module"]
                        and ("inputs" not in entry or isinstance(entry["inputs"], dict)))
                if not good:
                    errors.append(f"expect.runs: entry {k} must be an object with module and, optionally, inputs")
    texts = [key for key in ("shown", "not_shown") if key in expect]
    for key in texts:
        if not isinstance(expect[key], list) or not all(isinstance(item, str) for item in expect[key]):
            errors.append(f"expect.{key} must be a list of numbers written as text")
    for key in texts:
        if isinstance(expect[key], list) and all(isinstance(item, str) for item in expect[key]):
            errors += [f"expect.{key}: '{item}' must be one number the number check reads, not a date and "
                       "not a bare whole number from 0 to 12" for item in expect[key] if not _one_number(item)]
    for key in ("max_withheld", "max_corrections"):
        if key in expect and (not isinstance(expect[key], int) or isinstance(expect[key], bool)
                              or expect[key] < 0):
            errors.append(f"expect.{key} must be a whole number, 0 or more")
    if "steps" in expect:
        steps = expect["steps"]
        if not isinstance(steps, dict):
            errors.append("expect.steps must be an object")
        else:
            calculations = {step.get("id") for step in brief.get("process", []) if step.get("kind") == "calculation"}
            errors += [f"expect.steps: '{step}' is not a calculation step of the brief"
                       for step in steps if step not in calculations and not step.startswith("added_")]
            errors += [f"expect.steps: '{step}' must be built, reused, kept or not_built"
                       for step, outcome in steps.items() if outcome not in OUTCOMES]
    return errors


def load_scenarios(example_dir, brief: dict, only: str | None = None) -> list[dict]:
    """The validated scenarios of an example, by file name, or just `only` (SPEC 6.4).

    Raises ValueError with every problem, one per line, each `<file name>: <problem>`.
    """
    folder = Path(example_dir) / "scenarios"
    found = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if only is not None:
        names = [path.stem for path in found]
        found = [path for path in found if path.stem == only]
        if not found:
            raise ValueError(NO_SCENARIO.format(scenario=only, folder=folder, names=", ".join(names) or "(none)"))
    elif not found:
        raise ValueError(NO_SCENARIOS.format(folder=folder))

    scenarios, problems = [], []
    for path in found:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            problems.append(f"{path.name}: not valid JSON: {error}")
            continue
        errors = validate_scenario(value, stem=path.stem, brief=brief)
        problems += [f"{path.name}: {error}" for error in errors]
        scenarios.append(value)
    if problems:
        raise ValueError("\n".join(problems))
    return scenarios


def _events(conn, session_id, kind) -> list[dict]:
    return [json.loads(row["payload"]) for row in db.list_events(conn, session_id=session_id, kind=kind)]


def check_scenario(conn, session_id, scenario, results=None) -> list[dict]:
    """One check per expectation, in the order of SPEC 6.5."""
    expect = scenario["expect"]
    checks = []

    def check(what, passed, seen):
        checks.append({"what": what, "passed": bool(passed), "seen": seen})

    replies = [event["text"] for event in _events(conn, session_id, "ask.reply")]
    for entry in expect.get("runs", []):
        runs = conn.execute("SELECT id, inputs FROM calc_runs WHERE session_id = ? AND module = ? ORDER BY id",
                            (session_id, entry["module"])).fetchall()
        wanted = entry.get("inputs")
        matching = [row for row in runs if wanted is None or _has_inputs(json.loads(row["inputs"]), wanted)]
        what = f"ran {entry['module']}"
        if wanted is not None:
            what += f" with {json.dumps(wanted, ensure_ascii=False)}"
        seen = ("; ".join(f"run {row['id']}: {json.dumps(json.loads(row['inputs']), ensure_ascii=False)}"
                          for row in runs) or f"no run of {entry['module']}")
        check(what, matching, seen)
    for key in ("shown", "not_shown"):
        for item in expect.get(key, []):
            found = next((k for k, text in enumerate(replies, start=1) if unbacked(item, [text]) == []), None)
            seen = f"in reply {found} of {len(replies)}" if found else f"in none of {len(replies)} replies"
            check(f"shows {item}" if key == "shown" else f"does not show {item}",
                  found if key == "shown" else not found, seen)
    if "max_withheld" in expect:
        count = len(_events(conn, session_id, "ask.withheld"))
        check(f"at most {expect['max_withheld']} replies withheld", count <= expect["max_withheld"],
              f"{count} withheld")
    if "max_corrections" in expect:
        count = len(_events(conn, session_id, "ask.correction"))
        check(f"at most {expect['max_corrections']} corrections", count <= expect["max_corrections"],
              f"{count} corrections")
    for step, outcome in expect.get("steps", {}).items():
        result = next((each for each in results or [] if each["step"] == step), None)
        seen = "not handled"
        if result is not None:
            seen = result["outcome"] + (f" ({result['reason']})" if result["outcome"] == "not_built" else "")
        check(f"step {step_label(step)} {outcome}", result is not None and result["outcome"] == outcome, seen)
    return checks


def _has_inputs(actual, wanted: dict) -> bool:
    """Does a run have each key of `wanted`, with a value `same()` accepts?"""
    return isinstance(actual, dict) and all(key in actual and same(value, actual[key])
                                            for key, value in wanted.items())


def _one_line(error: Exception) -> str:
    return f"{type(error).__name__}: {' '.join(str(error).split())}"


def _copy_example(example_dir: Path, folder: Path, without: list[str]) -> None:
    """Copy the brief and the modules of an example into a scratch folder (SPEC 6.5, step 1)."""
    if (example_dir / "brief").is_dir():
        shutil.copytree(example_dir / "brief", folder / "brief")
    else:
        (folder / "brief").mkdir()
    (folder / "modules").mkdir()
    source = example_dir / "modules"
    for path in sorted(source.iterdir()) if source.is_dir() else []:
        if not path.is_dir() or path.name.startswith("_"):
            continue
        try:
            step = json.loads((path / "spec.json").read_text(encoding="utf-8")).get("step_id")
        except (OSError, ValueError, AttributeError):
            step = None
        if step not in without:
            shutil.copytree(path, folder / "modules" / path.name)


def run_scenario(scenario, *, example_dir, model, keep=False) -> dict:
    """Run one validated scenario in a scratch folder and check it (SPEC 6.5)."""
    example_dir = Path(example_dir)
    Path(REPLAY_DIR).mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(dir=REPLAY_DIR, prefix=f"{example_dir.name}-{scenario['name']}-"))
    variables = {"HARNESS_DB": str(folder / "harness.db"), "HARNESS_BRIEF_DIR": str(folder / "brief"),
                 "HARNESS_MODULES_DIR": str(folder / "modules")}
    earlier = {name: os.environ.get(name) for name in variables}
    error, checks, conn = None, [], None
    try:
        os.environ.update(variables)
        _copy_example(example_dir, folder, scenario.get("without", []))
        conn = db.connect(folder / "harness.db")
        db.migrate(conn)
        session_id = uuid.uuid4().hex
        db.record_event(conn, session_id=session_id, kind="replay.scenario", actor="harness",
                        payload={"example": example_dir.name, "scenario": scenario["name"],
                                 "kind": scenario["kind"], "lines": scenario["lines"],
                                 "expect": scenario["expect"], "without": scenario.get("without", [])})
        error, checks = _play(scenario, conn, session_id, folder, model)
        passed = error is None and all(check["passed"] for check in checks)
        db.record_event(conn, session_id=session_id, kind="replay.checked", actor="harness",
                        payload={"scenario": scenario["name"], "passed": passed, "error": error,
                                 "checks": checks})
    except Exception as failure:        # a problem of the scratch folder or the database itself
        error, passed = _one_line(failure), False
    finally:
        if conn is not None:
            conn.close()
        for name, value in earlier.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if not keep:
            shutil.rmtree(folder, ignore_errors=True)
    return {"scenario": scenario["name"], "passed": passed, "checks": checks, "error": error,
            "folder": str(folder) if keep else None}


def _play(scenario, conn, session_id, folder, model):
    """Steps 4 to 6 of SPEC 6.5. Returns (error, checks)."""
    lines = iter(scenario["lines"])

    def ask(text):
        return next(lines, "/quit")

    shown = []
    try:
        brief = load_brief(folder / "brief")
        for result in adopt(conn=conn, brief=brief, ask=ask, say=shown.append, session_id=session_id,
                            how="replay"):
            if result["outcome"] == "not_adopted":
                return f"{result['module']} was not adopted: {result['reason']}", []
        results = None
        if scenario["kind"] == "ask":
            today = date.fromisoformat(scenario["today"]) if "today" in scenario else date.today()
            run_agent(model=model, conn=conn, brief=brief, ask=ask, say=shown.append, session_id=session_id,
                      question="", today=today)
        else:
            results = build(model=model, conn=conn, brief=brief, ask=ask, say=shown.append,
                            session_id=session_id)
    except Exception as failure:
        return _one_line(failure), []
    return None, check_scenario(conn, session_id, scenario, results)
