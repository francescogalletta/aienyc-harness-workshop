"""Scenarios and replay (SPEC 2.6).

A scenario is a scripted person: lines said to the main chat and actions (build, confirm, correct, choose,
side, use, dismiss), played in order against the configured model on a Session, in a scratch copy of the
example under `my/var/replay/`, at the scenario's layer. What the harness must have done is checked by the
expectations the layers register (`Layer.expects`); a check never reads wording.
"""
import dataclasses
import json
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from .config import EXAMPLES_DIR, UNKNOWN_EXAMPLE, load_config
from .core import Session
from .layers import enabled

REPLAY_DIR = Path("my/var/replay")
SETTLE_TIMEOUT = 900            # seconds the harness may work on one line before replay calls it stuck
NO_SCENARIO = "There is no scenario '{scenario}' in {folder}. The scenarios are: {names}."
NO_SCENARIOS = "There are no scenarios in {folder}."
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEYS = ("name", "layer", "kind", "description", "today", "without", "review", "lines", "expect")
REQUIRED = ("name", "layer", "kind", "lines", "expect")

# verb -> (lowest layer, allowed keys, required keys). Every action object may also carry "settle": false
# (play it without waiting for the harness to finish what it is doing: a side thread opened mid-answer).
VERBS = {
    "say": (1, {"text", "step"}, {"text"}),
    "build": (2, set(), set()),
    "confirm": (4, set(), set()),                   # confirm_assumptions on the latest open notice
    "correct": (4, {"text"}, {"text"}),             # say, with the latest notice attached ("Change it")
    "choose": (4, {"option"}, {"option"}),          # the option of the decision the main lane waits on
    "side": (4, {"text", "step", "reply"}, {"text"}),   # a new side thread; "reply": true, in the latest one
    "use": (5, {"index"}, set()),                   # use_challenge on the index-th open challenge (not a question)
    "dismiss": (5, {"index"}, set()),               # dismiss_challenge on the index-th open challenge
}


class ReplayError(Exception):
    """The scripted person could not do what the scenario says, or the harness failed while it did."""


def _is_date(value) -> bool:
    if not isinstance(value, str) or not DAY.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _whole(value, low=0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= low


def _one_line(error) -> str:
    return f"{type(error).__name__}: {' '.join(str(error).split())}"


# --- What the layers register ---

def _config_at(layer: int):
    return dataclasses.replace(load_config(), layers=layer)


def available_layers() -> int:
    """The highest layer both set and present in this tree."""
    return len(enabled(load_config())) - 1


def expectations(layer: int) -> dict:
    """The expectation keys of layers 0..`layer`, each an `Expect`."""
    found = {}
    for each in enabled(_config_at(layer)):
        found.update(each.expects)
    return found


# --- Validation ---

def _steps_of(brief: dict, *kinds) -> set:
    return {step.get("id") for step in brief.get("process", []) if not kinds or step.get("kind") in kinds}


def _known_step(step, brief: dict) -> bool:
    return isinstance(step, str) and (step in _steps_of(brief) or re.match(r"^added_[1-9][0-9]*$", step) is not None)


def _line_problems(number: int, line, layer: int, brief: dict) -> list[str]:
    where = f"lines: line {number}"
    if isinstance(line, str):
        return [] if line.strip() else [f"{where} is empty"]
    if not isinstance(line, dict) or not isinstance(line.get("act"), str):
        return [f"{where} must be a text or an object with an act"]
    verb = line["act"]
    if verb not in VERBS:
        return [f"{where}: unknown act '{verb}' (the acts are {', '.join(VERBS)})"]
    lowest, allowed, required = VERBS[verb]
    errors = []
    if layer < lowest:
        errors.append(f"{where}: '{verb}' needs layer {lowest} or above")
    errors += [f"{where}: '{verb}' does not take '{key}'" for key in line if key not in allowed | {"act", "settle"}]
    errors += [f"{where}: '{verb}' needs '{key}'" for key in sorted(required) if key not in line]
    if "settle" in line and not isinstance(line["settle"], bool):
        errors.append(f"{where}: settle must be true or false")
    for key in ("text",):
        if key in line and not (isinstance(line[key], str) and line[key].strip()):
            errors.append(f"{where}: {key} must be a non-empty text")
    if "option" in line and not _whole(line["option"], 1):
        errors.append(f"{where}: option must be a whole number from 1")
    if "index" in line and not _whole(line["index"], 1):
        errors.append(f"{where}: index must be a whole number from 1")
    if "reply" in line and not isinstance(line["reply"], bool):
        errors.append(f"{where}: reply must be true or false")
    if "step" in line and not _known_step(line["step"], brief):
        errors.append(f"{where}: '{line['step']}' is not a step of the brief")
    if line.get("reply") and "step" in line:
        errors.append(f"{where}: a reply goes to a thread that has its step already")
    return errors


def validate_scenario(value, *, stem: str, brief: dict, layers: int | None = None) -> list[str]:
    """Return what is wrong with a scenario. An empty list means it can run (SPEC 2.6).

    `layers`: the highest layer present, to know which expectation keys exist (default: this tree's).
    """
    if not isinstance(value, dict):
        return ["the scenario must be an object"]
    missing = [f"missing: {key}" for key in REQUIRED if key not in value]
    if missing:
        return missing
    errors = [f"unknown key: {key}" for key in value if key not in KEYS]
    if not SNAKE.match(stem) or value["name"] != stem:
        errors.append(f"name must be the file name without .json, in snake_case: '{stem}'")
    layer, kind = value["layer"], value["kind"]
    if not _whole(layer, 1) or layer > 5:
        errors.append("layer must be a whole number from 1 to 5")
        layer = None
    if kind not in ("ask", "build"):
        errors.append("kind must be ask or build")
    elif kind == "build" and isinstance(layer, int) and layer < 2:
        errors.append("a build scenario needs layer 2 or above")
    if "description" in value and not isinstance(value["description"], str):
        errors.append("description must be a string")
    if "today" in value:
        if kind == "build":
            errors.append("today is only for ask scenarios")
        if not _is_date(value["today"]):
            errors.append("today must be a date written YYYY-MM-DD")
    if "review" in value and not isinstance(value["review"], bool):
        errors.append("review must be true or false")
    if "without" in value:
        without = value["without"]
        if not isinstance(without, list) or not all(isinstance(item, str) for item in without):
            errors.append("without must be a list of step ids")
        else:
            errors += [f"without: '{item}' is not a calculation step of the brief"
                       for item in without if item not in _steps_of(brief, "calculation")]
    lines = value["lines"]
    if not isinstance(lines, list):
        errors.append("lines must be a list")
        lines = []
    elif not lines and kind == "ask":
        errors.append("an ask scenario needs at least one line")
    for number, line in enumerate(lines, start=1):
        errors += _line_problems(number, line, layer or 5, brief)
    if layer is not None:
        errors += _expect_problems(value["expect"], layer, brief, layers)
    return errors


def _expect_problems(expect, layer: int, brief: dict, layers: int | None) -> list[str]:
    if not isinstance(expect, dict) or not expect:
        return ["expect must be an object with at least one expectation"]
    known = expectations(min(layer, layers if layers is not None else available_layers()))
    errors = []
    for key, value in expect.items():
        if key not in known:
            errors.append(f"expect: unknown key: {key}")
            continue
        problem = known[key].validate(value)
        if problem:
            errors.append(f"expect.{key}: {problem}")
    steps = expect.get("steps")
    if isinstance(steps, dict):
        errors += [f"expect.steps: '{step}' is not a calculation step of the brief" for step in steps
                   if step not in _steps_of(brief, "calculation") and not _known_step(step, brief)]
    for entry in expect.get("decisions", []) if isinstance(expect.get("decisions"), list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("step"), str) and not _known_step(entry["step"], brief):
            errors.append(f"expect.decisions: '{entry['step']}' is not a step of the brief")
    return errors


def read_brief(example_dir) -> dict:
    """The example's brief as plain data (replay reads only the steps from it)."""
    try:
        value = json.loads((Path(example_dir) / "brief" / "domain_brief.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def load_scenarios(example_dir, only: str | None = None) -> tuple[list[dict], list[dict]]:
    """(scenarios, skipped) of an example, by file name, or just `only`. A scenario whose layer is above
    the enabled layers is skipped: `{"name", "layer"}`. Raises ValueError with every problem, one per line,
    each `<file name>: <problem>`."""
    folder = Path(example_dir) / "scenarios"
    found = sorted(folder.glob("*.json")) if folder.is_dir() else []
    if only is not None:
        names = [path.stem for path in found]
        found = [path for path in found if path.stem == only]
        if not found:
            raise ValueError(NO_SCENARIO.format(scenario=only, folder=folder, names=", ".join(names) or "(none)"))
    elif not found:
        raise ValueError(NO_SCENARIOS.format(folder=folder))
    brief, top = read_brief(example_dir), available_layers()
    scenarios, skipped, problems = [], [], []
    for path in found:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            problems.append(f"{path.name}: not valid JSON: {error}")
            continue
        if isinstance(value, dict) and _whole(value.get("layer"), 1) and value["layer"] > top:
            skipped.append({"name": path.stem, "layer": value["layer"]})
            continue
        errors = validate_scenario(value, stem=path.stem, brief=brief, layers=top)
        problems += [f"{path.name}: {error}" for error in errors]
        scenarios.append(value)
    if problems:
        raise ValueError("\n".join(problems))
    return scenarios, skipped


# --- Playing ---

def _copy_example(example_dir: Path, folder: Path, without: list[str]) -> None:
    """Copy the brief and the modules of an example into the scratch folder, leaving out the modules that
    carry out a `without` step."""
    if (example_dir / "brief").is_dir():
        shutil.copytree(example_dir / "brief", folder / "brief", ignore=shutil.ignore_patterns("__pycache__"))
    else:
        (folder / "brief").mkdir()
    (folder / "modules").mkdir()
    source = example_dir / "modules"
    for path in sorted(source.iterdir()) if source.is_dir() else []:
        if not path.is_dir() or path.name.startswith(("_", ".")):
            continue
        try:
            step = json.loads((path / "spec.json").read_text(encoding="utf-8")).get("step_id")
        except (OSError, ValueError, AttributeError):
            step = None
        if step not in without:
            shutil.copytree(path, folder / "modules" / path.name, ignore=shutil.ignore_patterns("__pycache__"))


def _latest_notice(state: dict, *, open_only: bool) -> str:
    """The id of the latest message with a notice under it (an open one, when `open_only`)."""
    for message in reversed(state["chat"]):
        notice = message.get("notice")
        if notice and (not open_only or notice.get("status") == "open"):
            return message["id"]
    raise ReplayError("there is no open notice to confirm" if open_only else "there is no notice to change")


def _open_challenges(state: dict, *, usable: bool) -> list[str]:
    found = [thread["challenge"] for thread in state.get("threads", [])
             if thread["kind"] == "review" and (thread.get("challenge") or {}).get("status") == "open"]
    found = [each for each in found if not usable or each["kind"] == "challenge"]
    return [each["id"] for each in sorted(found, key=lambda each: int(each["id"][1:]))]


def _action_for(line, state: dict) -> tuple[str, dict]:
    """The core action and payload a line stands for."""
    if isinstance(line, str):
        return "say", {"text": line}
    verb = line["act"]
    if verb == "say":
        return "say", {"text": line["text"], "step": line.get("step")}
    if verb == "build":
        return "build", {}
    if verb == "confirm":
        return "confirm_assumptions", {"message": _latest_notice(state, open_only=True)}
    if verb == "correct":
        return "say", {"text": line["text"], "notice": _latest_notice(state, open_only=False)}
    if verb == "choose":
        waiting = state["waiting"]
        if not waiting or waiting.get("kind") != "decision":
            raise ReplayError("nothing waits for a choice")
        return "choose", {"decision": waiting["decision"], "option": line["option"]}
    if verb == "side":
        if line.get("reply"):
            latest = next((thread["id"] for thread in reversed(state.get("threads", []))
                           if thread["kind"] == "side"), None)
            if latest is None:
                raise ReplayError("there is no side thread to reply in")
            return "side", {"text": line["text"], "thread": latest}
        return "side", {"text": line["text"], **({"step": line["step"]} if "step" in line else {})}
    open_ones = _open_challenges(state, usable=verb == "use")
    index = line.get("index", 1)
    if index > len(open_ones):
        raise ReplayError(f"there are {len(open_ones)} open challenges to {verb}, not {index}")
    return ("use_challenge" if verb == "use" else "dismiss_challenge"), {"challenge": open_ones[index - 1]}


def _describe(line) -> str:
    if isinstance(line, str):
        text = line
    else:
        text = f"[{line['act']}] " + str(line.get("text") or line.get("option") or line.get("index") or "")
    text = " ".join(text.split())
    return text if len(text) <= 72 else text[:71] + "…"


def _settle(session, timeout: float) -> dict:
    state = session.settle(timeout)
    if any(lane == "working" for lane in state["lanes"].values()):
        raise ReplayError(f"the harness was still working after {timeout:.0f} seconds; "
                          f"lanes {state['lanes']}, activity {[entry['text'] for entry in state['activity']]}")
    if state["error"]:
        raise ReplayError(f"a job failed: {state['error']}")
    return state


def _play(session, scenario: dict, say, timeout: float) -> None:
    """The scripted person: settle, then each line in order (SPEC 2.6)."""
    state = _settle(session, timeout)
    lines = list(scenario["lines"])
    if scenario["kind"] == "build":
        lines.insert(0, {"act": "build"})
    for number, line in enumerate(lines, start=1):
        if not (isinstance(line, dict) and line.get("settle") is False):
            state = _settle(session, timeout)
        say(f"  [{number}/{len(lines)}] {_describe(line)}")
        action, payload = _action_for(line, state)
        applied, reason = session.act(action, payload)
        if not applied:
            raise ReplayError(f"the harness did not take line {number} ({action}): {reason}")
    _settle(session, timeout)


def _check(scenario: dict, session) -> list[dict]:
    known = expectations(scenario["layer"])
    checks = []
    for key, value in scenario["expect"].items():
        try:
            result = known[key].check(value, session)
            checks.append({"key": key, "what": result["what"], "passed": bool(result["passed"]),
                           "seen": result["seen"]})
        except Exception as failure:         # a check that cannot be made is a check that failed
            checks.append({"key": key, "what": key, "passed": False, "seen": _one_line(failure)})
    return checks


def run_scenario(scenario, *, example_dir, keep=False, model_factory=None, write=print,
                 timeout: float = SETTLE_TIMEOUT) -> dict:
    """Run one validated scenario in a scratch folder and check it. Returns {"scenario", "passed", "checks",
    "error", "seconds", "folder"}; `folder` only with `keep`."""
    example_dir = Path(example_dir)
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(dir=REPLAY_DIR, prefix=f"{example_dir.name}-{scenario['name']}-")).resolve()
    variables = {"HARNESS_DB": str(folder / "harness.db"), "HARNESS_BRIEF_DIR": str(folder / "brief"),
                 "HARNESS_MODULES_DIR": str(folder / "modules"), "HARNESS_LAYERS": str(scenario["layer"]),
                 "HARNESS_REVIEW": "auto" if scenario.get("review") else "off"}
    earlier = {name: os.environ.get(name) for name in variables}
    started = time.monotonic()
    error, checks, session = None, [], None
    try:
        os.environ.update(variables)
        _copy_example(example_dir, folder, scenario.get("without", []))
        memory = {"today": date.fromisoformat(scenario["today"])} if "today" in scenario else {}
        options = {"model_factory": model_factory} if model_factory is not None else {}
        session = Session(load_config(), memory=memory, **options)
        session.record("replay.scenario", {"example": example_dir.name, "scenario": scenario["name"],
                                           "layer": scenario["layer"], "lines": scenario["lines"],
                                           "expect": scenario["expect"], "without": scenario.get("without", [])})
        try:
            _play(session, scenario, write, timeout)
        except ReplayError as failure:
            error = str(failure)
        checks = _check(scenario, session)
        passed = error is None and all(check["passed"] for check in checks)
        session.record("replay.checked", {"scenario": scenario["name"], "passed": passed, "error": error,
                                          "checks": checks})
    except Exception as failure:            # a problem of the scratch folder or the session itself
        error, passed = _one_line(failure), False
    finally:
        if session is not None:
            session.close()
        for name, value in earlier.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if not keep:
            shutil.rmtree(folder, ignore_errors=True)
    return {"scenario": scenario["name"], "passed": passed, "checks": checks, "error": error,
            "seconds": time.monotonic() - started, "folder": str(folder) if keep else None}


# --- The command ---

def report(example: str, result: dict, layer: int, write=print) -> None:
    for check in result["checks"]:
        write(f"  {'ok  ' if check['passed'] else 'FAIL'} {check['what']}  [{check['seen']}]")
    if result["error"]:
        write(f"  FAIL stopped: {result['error']}")
    write(f"{'PASS' if result['passed'] else 'FAIL'} {example}/{result['scenario']} "
          f"(layer {layer}) {result['seconds']:.0f} s")
    if result["folder"]:
        write(f"  kept: {result['folder']}")


def replay_command(args) -> int:
    """`replay EXAMPLE [SCENARIO] [--keep]`: exit 0 only when every scenario run passed."""
    example_dir = EXAMPLES_DIR / args.example
    if not SNAKE.match(args.example) or not example_dir.is_dir():
        names = sorted(path.name for path in EXAMPLES_DIR.iterdir() if path.is_dir()) if EXAMPLES_DIR.is_dir() else []
        print(UNKNOWN_EXAMPLE.format(name=args.example, names=", ".join(names) or "(none)"), file=sys.stderr)
        return 1
    try:
        scenarios, skipped = load_scenarios(example_dir, args.scenario)
    except ValueError as problem:
        print(problem, file=sys.stderr)
        return 1
    for each in skipped:
        print(f"skipped {args.example}/{each['name']}: it needs layer {each['layer']}", flush=True)
    failed = 0
    for scenario in scenarios:
        print(f"== {args.example}/{scenario['name']} (layer {scenario['layer']})", flush=True)
        result = run_scenario(scenario, example_dir=example_dir, keep=args.keep,
                              write=lambda text: print(text, flush=True))
        report(args.example, result, scenario["layer"])
        failed += not result["passed"]
    print(f"{len(scenarios) - failed} passed, {failed} failed, {len(skipped)} skipped", flush=True)
    return 1 if failed else 0


def replay_arguments(parser) -> None:
    parser.add_argument("example", help="the example whose scenarios to play (a folder of examples/)")
    parser.add_argument("scenario", nargs="?", help="one scenario, by file name without .json (default: all)")
    parser.add_argument("--keep", action="store_true", help="keep the scratch copy under my/var/replay/")
