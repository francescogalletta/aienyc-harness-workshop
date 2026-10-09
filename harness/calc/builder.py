"""The builder (SPEC 5.7): turns each calculation step of the brief into a registered module.

Three phases, each its own conversation with the model: the spec, the worked
examples (which the person checks by hand), and the code. The code writer
never sees the worked examples. Nothing is registered unless the code passes
its tests and the person's examples.
"""
import ast
import json
import re
import shutil
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .. import db
from ..config import load_config
from ..model import ToolSpec
from .gate import NOT_REGISTERED, run_tests
from .registry import (MIN_CONFIRMED, file_status, get_module, input_problems, list_modules,
                       map_step, module_dir, register, step_map, validate_spec)
from .safety import check_code
from .values import TYPES, from_json, to_json

MAX_ATTEMPTS = 3
MIN_EXAMPLES = 3
NO_BRIEF = "There is no brief yet. Write one with: python -m harness ground"
DRAFT_BRIEF = "The brief is still a draft. Confirm it first with: python -m harness ground"
STEP_HEADER = "Step {id}: {name}"
USE_TOOL = "[harness] Reply only by calling {tools}."
ONE_CALL = "Only one tool call is handled per reply. This one was ignored."
SPEC_REJECTED = "The spec was not accepted. Fix these and propose it again:"
NAME_TAKEN = "a module called '{name}' already exists: reuse it, or choose another name"
CANNOT_REUSE = "There is no registered module called '{name}' with unchanged files. Propose a spec instead."
EXAMPLES_REJECTED = "The examples were not accepted. Fix these and propose them again:"
EXAMPLES_INTRO = "Check these worked examples for {name}: {description} Your answers become the check its code must pass."
CONFIRM_EXAMPLE = ("Type /accept if the answer is right, type the right answer, or type /skip to leave "
                   "this example out. /quit stops the build.")
NOT_A_VALUE = "That could not be read as {kind}. Type /accept, the right answer, or /skip."
CODE_REJECTED = "The code was not accepted. Fix these and write both files again:"
RUNNING_TESTS = "  (running the tests)"
TESTS_FAILED = "The code was run and did not pass. Fix it and write both files again:"
EXAMPLE_FAILED = "Example {index} failed. Its inputs were: {inputs}"
EXAMPLES_DISAGREE = ("The code and these worked examples disagree. One of them is wrong. Check each by hand: "
                     "if the example was wrong, run the build again and type the right answer.")
DISAGREEMENT = "  With {inputs} you confirmed {expected}, and the code gives {got}."
REASON_SPEC = "no acceptable spec after 3 attempts"
REASON_EXAMPLES = "no acceptable examples after 3 attempts"
REASON_CONFIRMED = "fewer than 2 examples were confirmed"
REASON_CODE = "the code did not pass after 3 attempts"
REASON_STOPPED = "stopped by the person"
KIND_WORDS = {"number": "a number", "integer": "a whole number", "date": "a date (YYYY-MM-DD)",
              "boolean": "yes or no", "text": "text", "list": "a JSON list", "object": "a JSON object"}

_TEXT = {"type": "string"}
_TYPE = {"type": "string", "enum": list(TYPES)}
SPEC_SCHEMA = {"type": "object", "properties": {
    "name": _TEXT, "description": _TEXT, "method": _TEXT, "formula": _TEXT,
    "inputs": {"type": "array", "items": {"type": "object", "properties": {
        "name": _TEXT, "type": _TYPE, "description": _TEXT}, "required": ["name", "type", "description"]}},
    "output": {"type": "object", "properties": {"type": _TYPE, "description": _TEXT},
               "required": ["type", "description"]}},
    "required": ["name", "description", "method", "formula", "inputs", "output"]}
REUSE_SCHEMA = {"type": "object", "properties": {"module": _TEXT, "reason": _TEXT},
                "required": ["module", "reason"]}
EXAMPLES_SCHEMA = {"type": "object", "properties": {"examples": {"type": "array", "items": {
    "type": "object", "properties": {"inputs": {"type": "object"}, "expected": {}, "working": _TEXT},
    "required": ["inputs", "expected", "working"]}}}, "required": ["examples"]}
CODE_SCHEMA = {"type": "object", "properties": {"module_py": _TEXT, "tests_py": _TEXT},
               "required": ["module_py", "tests_py"]}

PROPOSE_SPEC = ToolSpec(
    name="propose_spec",
    description=("Propose the spec of the calculation: its name, what it works out, the method, the formula, "
                 "its typed inputs and its typed output. The harness checks it."),
    input_schema=SPEC_SCHEMA)
REUSE_MODULE = ToolSpec(
    name="reuse_module",
    description="Use a registered module that already does this step's job, instead of writing a new one.",
    input_schema=REUSE_SCHEMA)
PROPOSE_EXAMPLES = ToolSpec(
    name="propose_examples",
    description=("Propose worked examples for the spec: the inputs, the exact expected answer and one line "
                 "of working each. The person checks them by hand."),
    input_schema=EXAMPLES_SCHEMA)
WRITE_MODULE = ToolSpec(
    name="write_module",
    description="Send the two files: module.py with the function calculate, and tests.py with its unit tests.",
    input_schema=CODE_SCHEMA)

SPEC_FILE_KEYS = ("name", "description", "step_id", "method", "formula", "inputs", "output")


class Stopped(Exception):
    """The person typed /quit."""


def load_brief(folder) -> dict:
    """Read the confirmed brief in `folder`, without its `meta` (SPEC 5.7)."""
    path = Path(folder) / "domain_brief.json"
    if not path.exists():
        raise ValueError(NO_BRIEF)
    brief = json.loads(path.read_text(encoding="utf-8"))
    if brief.get("meta", {}).get("status") != "confirmed":
        raise ValueError(DRAFT_BRIEF)
    return {key: value for key, value in brief.items() if key != "meta"}


def build(*, model, conn, brief, ask, say=print, session_id, rebuild=None) -> list[dict]:
    """Build a module for each calculation step of the brief. Returns one result per step handled.

    `ask(text)` shows text to the person and returns what they typed.
    `say(text)` shows text that needs no answer.
    With `rebuild=NAME`, only that registered module is built again.
    """
    brief = {key: value for key, value in brief.items() if key != "meta"}
    steps = {step["id"]: step for step in brief["process"]}
    if rebuild is not None:
        registered = get_module(conn, rebuild)
        if registered is None:
            raise ValueError(NOT_REGISTERED.format(name=rebuild))
        step_id = registered["spec"]["step_id"]
        if step_id not in steps:
            raise ValueError(f"The brief has no step '{step_id}', which '{rebuild}' was built for.")
        todo = [steps[step_id]]
    else:
        todo = [step for step in brief["process"] if step.get("kind") == "calculation"]

    results = []
    for step in todo:
        say(STEP_HEADER.format(id=step["id"], name=step["name"]))
        name = rebuild                              # the module to build again, if there is one
        if rebuild is None and step["id"] in step_map(conn):
            name = step_map(conn)[step["id"]]
            if file_status(conn, name) == "unchanged":
                results.append({"step": step["id"], "outcome": "kept", "module": name, "reason": ""})
                continue
        try:
            result = _build_step(model, conn, brief, step, name, ask, say, session_id)
        except Stopped:
            result = {"step": step["id"], "outcome": "not_built", "module": None, "reason": REASON_STOPPED}
            _record_not_built(conn, session_id, result)
            results.append(result)
            break
        if result["outcome"] == "not_built":
            _record_not_built(conn, session_id, result)
        results.append(result)
    return results


def _record_not_built(conn, session_id, result) -> None:
    db.record_event(conn, session_id=session_id, kind="calc.step_not_built", actor="harness",
                    payload={"step": result["step"], "reason": result["reason"]})


def _build_step(model, conn, brief, step, rebuild, ask, say, session_id) -> dict:
    """Run the three phases for one step. `rebuild` is the name of the module being built again, or None."""
    def record(kind, actor, payload):
        db.record_event(conn, session_id=session_id, kind=kind, actor=actor, payload=payload)

    def done(outcome, module=None, reason=""):
        return {"step": step["id"], "outcome": outcome, "module": module, "reason": reason}

    spec = _phase_spec(model, conn, brief, step, rebuild, record)
    if isinstance(spec, str):                       # the name of a module reused
        return done("reused", spec)
    if spec is None:
        return done("not_built", reason=REASON_SPEC)

    examples = _phase_examples(model, step, spec, record)
    if examples is None:
        return done("not_built", reason=REASON_EXAMPLES)
    golden = _check_examples(examples, spec, ask, say, record)
    if len(golden) < MIN_CONFIRMED:
        return done("not_built", reason=REASON_CONFIRMED)

    if not _phase_code(model, conn, step, spec, golden, record, say, session_id):
        return done("not_built", reason=REASON_CODE)
    return done("built", spec["name"])


# --- Conversations -------------------------------------------------------------

def format_sections(sections: dict) -> str:
    """A user message: a line `[title]` and then the value, one blank line between sections."""
    parts = []
    for title, value in sections.items():
        text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
        parts.append(f"[{title}]\n{text}")
    return "\n\n".join(parts)


def _converse(model, system: str, user: str, tools: list, handle):
    """One phase: up to MAX_ATTEMPTS model calls. Returns what `handle` accepted, or None.

    `handle(call, attempt)` returns (tool result text, is_error, accepted or None).
    """
    names = [tool.name for tool in tools]
    messages = [{"role": "user", "content": user}]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = model.complete(system=system, messages=messages, tools=tools)
        if not response.tool_calls:
            messages.append({"role": "assistant", "content": response.text})
            messages.append({"role": "user", "content": USE_TOOL.format(tools=" or ".join(names))})
            continue
        first, *others = response.tool_calls
        if first.name in names:
            content, is_error, accepted = handle(first, attempt)
        else:
            content, is_error, accepted = f"There is no tool called {first.name} here.", True, None
        if accepted is not None:
            return accepted
        messages.append({"role": "assistant", "content": response.text, "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.tool_calls]})
        messages.append({"role": "tool", "tool_call_id": first.id, "content": content, "is_error": is_error})
        for call in others:
            messages.append({"role": "tool", "tool_call_id": call.id, "content": ONE_CALL, "is_error": True})
    return None


def _bullets(heading: str, lines: list[str]) -> str:
    return heading + "\n" + "\n".join(f"- {line}" for line in lines)


# --- Phase 1: the spec ---------------------------------------------------------

def _phase_spec(model, conn, brief, step, rebuild, record):
    """Returns the accepted spec, the name of a module reused, or None."""
    others = [module["spec"] for module in list_modules(conn)
              if module["name"] != rebuild and file_status(conn, module["name"]) == "unchanged"]
    sections = {"step": step, "brief": brief, "registered modules": others}
    if rebuild is not None:
        sections["current spec"] = get_module(conn, rebuild)["spec"]
    tools = [PROPOSE_SPEC] if rebuild is not None else [PROPOSE_SPEC, REUSE_MODULE]
    system = (Path(__file__).with_name("spec_writer.md")).read_text(encoding="utf-8")

    def handle(call, attempt):
        if call.name == "reuse_module":
            module = call.arguments.get("module")
            if isinstance(module, str) and get_module(conn, module) and file_status(conn, module) == "unchanged":
                map_step(conn, step["id"], module)
                record("calc.module_reused", "agent", {"step": step["id"], "module": module,
                                                       "reason": call.arguments.get("reason", "")})
                return "Reused.", False, module
            return CANNOT_REUSE.format(name=module), True, None

        spec = _clean_spec(call.arguments, step["id"], rebuild)
        errors = validate_spec(spec)
        name = spec.get("name")
        if rebuild is None and isinstance(name, str) and get_module(conn, name) is not None:
            errors.append(NAME_TAKEN.format(name=name))
        if errors:
            record("calc.spec_rejected", "harness", {"step": step["id"], "errors": errors})
            return _bullets(SPEC_REJECTED, errors), True, None
        record("calc.spec_proposed", "agent", {"step": step["id"], "spec": spec})
        return "Spec accepted.", False, spec

    return _converse(model, system, format_sections(sections), tools, handle)


def _clean_spec(arguments: dict, step_id: str, rebuild) -> dict:
    """Drop unknown keys; the harness sets `step_id` (and `name` on a rebuild)."""
    spec = {key: arguments[key] for key in SPEC_FILE_KEYS if key in arguments}
    spec["step_id"] = step_id
    if rebuild is not None:
        spec["name"] = rebuild
    if isinstance(spec.get("inputs"), list):
        spec["inputs"] = [{key: item[key] for key in ("name", "type", "description") if key in item}
                          if isinstance(item, dict) else item for item in spec["inputs"]]
    if isinstance(spec.get("output"), dict):
        spec["output"] = {key: spec["output"][key] for key in ("type", "description") if key in spec["output"]}
    return {key: spec[key] for key in SPEC_FILE_KEYS if key in spec}


# --- Phase 2: the worked examples ----------------------------------------------

def _phase_examples(model, step, spec, record):
    """Returns the accepted examples, or None."""
    system = Path(__file__).with_name("example_writer.md").read_text(encoding="utf-8")

    def handle(call, attempt):
        examples = call.arguments.get("examples")
        errors = _example_problems(examples if isinstance(examples, list) else [], spec)
        if errors:
            record("calc.examples_rejected", "harness", {"module": spec["name"], "errors": errors})
            return _bullets(EXAMPLES_REJECTED, errors), True, None
        record("calc.examples_proposed", "agent", {"module": spec["name"], "examples": examples})
        return "Examples accepted.", False, examples

    return _converse(model, system, format_sections({"spec": spec, "step": step}), [PROPOSE_EXAMPLES], handle)


def _example_problems(examples: list, spec: dict) -> list[str]:
    problems = []
    if len(examples) < MIN_EXAMPLES:
        problems.append(f"at least {MIN_EXAMPLES} examples are needed")
    for k, example in enumerate(examples, start=1):
        if (not isinstance(example, dict) or "inputs" not in example or "expected" not in example
                or not isinstance(example.get("working"), str) or not example["working"].strip()):
            problems.append(f"example {k}: it needs inputs, expected and a non-empty working")
            continue
        problems += [f"example {k}: {problem}" for problem in input_problems(spec, example["inputs"])]
        try:
            from_json(example["expected"], spec["output"]["type"])
        except ValueError as error:
            problems.append(f"example {k}: the expected answer: {error}")
    return problems


def _show(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _check_examples(examples, spec, ask, say, record) -> list[dict]:
    """The person checks every example. Returns the confirmed ones, as golden.json holds them."""
    say(EXAMPLES_INTRO.format(name=spec["name"], description=spec["description"]))
    golden = []
    for k, example in enumerate(examples, start=1):
        lines = [f"Example {k} of {len(examples)}"]
        lines += [f"  {item['name']}: {_show(example['inputs'][item['name']])}" for item in spec["inputs"]]
        lines += [f"  Working: {example['working']}", f"  Proposed answer: {_show(example['expected'])}"]
        say("\n".join(lines))
        decision, expected = _decide(example, spec["output"]["type"], ask, say)
        record("calc.golden_decision", "person", {"module": spec["name"], "index": k, "decision": decision,
                                                  "expected": None if decision == "skipped" else expected})
        if decision != "skipped":
            golden.append({"inputs": example["inputs"], "expected": expected,
                           "working": example["working"], "decision": decision})
    return golden


def _decide(example, kind, ask, say):
    """Ask until the person accepts, skips or corrects. Returns (decision, confirmed answer)."""
    while True:
        answer = ask(CONFIRM_EXAMPLE).strip()
        if answer == "/quit":
            raise Stopped
        if answer == "":
            continue
        if answer == "/accept":
            return "accepted", example["expected"]
        if answer == "/skip":
            return "skipped", None
        try:
            return "corrected", _read_answer(answer, kind)
        except ValueError:
            say(NOT_A_VALUE.format(kind=KIND_WORDS[kind]))


def _read_answer(text: str, kind: str):
    """Read what the person typed as the output type. Raises ValueError if it cannot be read."""
    if kind in ("number", "integer"):
        text = re.sub(r"[ ,$€£]", "", text)
        if kind == "integer":
            return str(int(text))
        try:
            number = Decimal(text)
        except InvalidOperation:
            raise ValueError("not a number") from None
        if not number.is_finite():
            raise ValueError("not finite")
        return to_json(number)
    if kind == "date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            raise ValueError("not YYYY-MM-DD")
        date.fromisoformat(text)
        return text
    if kind == "boolean":
        if text.lower() in ("yes", "y", "true"):
            return True
        if text.lower() in ("no", "n", "false"):
            return False
        raise ValueError("not yes or no")
    if kind == "text":
        return text
    value = json.loads(text)
    if not isinstance(value, list if kind == "list" else dict):
        raise ValueError(f"not {KIND_WORDS[kind]}")
    return value


# --- Phase 3: the code ---------------------------------------------------------

def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _phase_code(model, conn, step, spec, golden, record, say, session_id) -> bool:
    """Write, check and test the code in the staging folder. On success move it into place and register."""
    name = spec["name"]
    staging = load_config().modules_dir / "_build" / name
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    _write_json(staging / "spec.json", spec)
    _write_json(staging / "golden.json", golden)
    system = Path(__file__).with_name("module_writer.md").read_text(encoding="utf-8")
    last_report = {}                                # the report of the latest run, for the person only

    def handle(call, attempt):
        module_py, tests_py = (call.arguments.get(key) for key in ("module_py", "tests_py"))
        module_py = module_py if isinstance(module_py, str) else ""
        tests_py = tests_py if isinstance(tests_py, str) else ""
        record("calc.code_written", "agent", {"module": name, "attempt": attempt,
                                              "module_py": module_py, "tests_py": tests_py})
        problems = _code_problems(module_py, tests_py, spec)
        if problems:
            record("calc.code_rejected", "harness", {"module": name, "attempt": attempt, "problems": problems})
            return _bullets(CODE_REJECTED, problems), True, None

        (staging / "module.py").write_text(module_py, encoding="utf-8")
        (staging / "tests.py").write_text(tests_py, encoding="utf-8")
        say(RUNNING_TESTS)
        run = run_tests(conn, name, reason="build", session_id=session_id, folder=staging)
        shutil.rmtree(staging / "__pycache__", ignore_errors=True)      # nothing stale between attempts
        last_report.clear()
        last_report.update(run["report"])
        if not run["passed"]:
            return _failure_text(run["report"], golden), True, None

        if module_dir(name).exists():
            shutil.rmtree(module_dir(name))
        module_dir(name).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(module_dir(name)))
        register(conn, name, step_id=step["id"], test_run_id=run["test_run_id"], session_id=session_id)
        return "Registered.", False, True

    registered = bool(_converse(model, system, format_sections({"spec": spec}), [WRITE_MODULE], handle))
    if not registered:
        _say_disagreement(last_report, golden, say)
    return registered


def _say_disagreement(report: dict, golden: list[dict], say) -> None:
    """The code failed three times. If worked examples failed, tell the person: one of them may be wrong.

    This goes to the person only; the code writer is never told the expected or the actual answer.
    """
    failing = [example for example in report.get("golden", []) if not example["passed"]]
    if not failing:
        return
    say(EXAMPLES_DISAGREE)
    for example in failing:
        confirmed = golden[example["index"] - 1]
        got = json.dumps(example["got"], ensure_ascii=False) if "got" in example else "an error"
        say(DISAGREEMENT.format(inputs=json.dumps(confirmed["inputs"], ensure_ascii=False),
                                expected=json.dumps(confirmed["expected"], ensure_ascii=False), got=got))


def _code_problems(module_py: str, tests_py: str, spec: dict) -> list[str]:
    problems = []
    if not module_py:
        problems.append("module.py is empty")
    if not tests_py:
        problems.append("tests.py is empty")
    problems += [f"module.py: {problem}" for problem in check_code(module_py)]
    problems += [f"tests.py: {problem}" for problem in check_code(tests_py, also_allow=("module",))]

    names = [item["name"] for item in spec["inputs"]]
    try:
        top = ast.parse(module_py).body
    except SyntaxError:
        top = None                  # check_code has already said so
    if top is not None:
        found = [node for node in top if isinstance(node, ast.FunctionDef) and node.name == "calculate"]
        arguments = found[0].args if found else None
        parameters = ([a.arg for a in arguments.posonlyargs + arguments.args + arguments.kwonlyargs]
                      if arguments else [])
        if (arguments is None or arguments.vararg or arguments.kwarg
                or sorted(parameters) != sorted(names)):
            problems.append("module.py must define calculate with exactly these parameters: "
                            + ", ".join(names))
    try:
        top = ast.parse(tests_py).body
    except SyntaxError:
        top = None
    if top is not None and not any(isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
                                   for node in top):
        problems.append("tests.py must hold at least one test_ function")
    return problems


def _failure_text(report: dict, golden: list[dict]) -> str:
    """What the code writer is told when the run fails: never the expected or the actual answer."""
    lines = []
    if report.get("error"):
        lines.append(f"- The run stopped: {report['error']}")
    for test in report["tests"]:
        if not test["passed"]:
            lines.append(f"- {test['name']} failed:\n{test.get('error', '')}")
    for example in report["golden"]:
        if not example["passed"]:
            inputs = json.dumps(golden[example["index"] - 1]["inputs"], ensure_ascii=False)
            line = "- " + EXAMPLE_FAILED.format(index=example["index"], inputs=inputs)
            if example.get("error"):
                line += f" It stopped with: {example['error']}"
            lines.append(line)
    return "\n".join([TESTS_FAILED] + lines)
