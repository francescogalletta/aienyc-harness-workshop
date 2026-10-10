"""The builder (SPEC 5.7): turns each calculation step of the process into a registered module.

Three phases, each its own conversation with the model: the spec (which the
person reads in plain words and checks against what they have), the worked
examples (which the person checks by hand, in their own words, with the
example helper), and the code. The code writer never sees the worked examples.
Nothing is registered unless the code passes its tests and the person's examples.
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
from .added import ADDED_PREFIX, process_steps, step_label
from .gate import NOT_REGISTERED, run_tests
from .notes import add_note, list_notes
from .provenance import unbacked
from .registry import (MIN_CONFIRMED, file_status, get_module, input_problems, list_modules,
                       map_step, module_dir, register, step_map, validate_spec)
from .safety import check_code
from .values import TYPES, from_json, to_json

MAX_ATTEMPTS = 3
MIN_EXAMPLES = 3
MAX_PLAN_ROUNDS = 2
ACCEPT_WORDS = {"/accept", "yes", "y", "yes.", "ok", "okay", "si", "sí"}
NO_BRIEF = "There is no brief yet. Write one with: python -m harness ground"
DRAFT_BRIEF = "The brief is still a draft. Confirm it first with: python -m harness ground"
RESERVED_ID = ("The brief has a step '{id}', but step ids that start with added_ are kept for steps added in a "
               "conversation. Change it with: python -m harness ground")
NO_STEP = "The process has no step '{step}', which '{name}' was built for."
STEP_HEADER = "Step {id}: {name}"         # {id} is step_label(the step's id)
WRITING_SPEC = "  (writing the plan for this step, attempt {attempt})"
WRITING_EXAMPLES = "  (writing made-up examples, attempt {attempt})"
WRITING_CODE = "  (writing the code, attempt {attempt})"
READING_REPLY = "  (reading your answer)"
USE_TOOL = "[harness] Reply only by calling {tools}."
ONE_CALL = "Only one tool call is handled per reply. This one was ignored."
SPEC_REJECTED = "The spec was not accepted. Fix these and propose it again:"
NAME_TAKEN = "a module called '{name}' already exists: reuse it, or choose another name"
CANNOT_REUSE = "There is no registered module called '{name}' with unchanged files. Propose a spec instead."
PLAN_QUESTION = ("Does this fit what you have? Type yes to go on. If not, tell me in your own words what you do "
                 "have: a list of amounts, a rough range, anything. /skip leaves this step for later, /quit "
                 "stops the build.")
PLAN_FEEDBACK = ("The spec passed the checks, and the person read it in plain words. They said it does not fit "
                 "what they have, in these words:\n{text}\nPropose a revised spec shaped around what they have. "
                 "Their figures are for later: never put them in the spec.")
PLAN_KEPT = ("I will go on with the last plan shown above. What you said is kept as a note, for when you work "
             "with your real numbers.")
EXAMPLES_REJECTED = "The examples were not accepted. Fix these and propose them again:"
EXAMPLES_INTRO = ("Now a few made-up examples, to check the arithmetic before any code is written. They are not "
                  "your figures: they use small round numbers, and your real numbers come later, when you ask "
                  "about your plan. Check the working and the proposed answer of each one by hand. What you "
                  "confirm becomes the test the code must pass.")
CONFIRM_EXAMPLE = ("Is the proposed answer right for this made-up example? Type yes if it is. If not, type the "
                   "right answer, or say in your own words what is wrong. You can also ask a question about it. "
                   "/skip leaves this example out, /quit stops the build.")
CONFIRM_ANSWER = ("Is that the right answer for this made-up example? Type yes to keep it, or say what to "
                  "change. /skip leaves this example out, /quit stops the build.")
NOTE_KEPT = ("Thank you. I have kept that as a note about your real situation, for later. For now, only the "
             "made-up example above needs checking.")
NOT_UNDERSTOOD = ("Sorry, I did not understand that. Type yes if the proposed answer is right. If not, type the "
                  "right answer, with every number in it written out.")
CODE_REJECTED = "The code was not accepted. Fix these and write both files again:"
RUNNING_TESTS = "  (running the tests)"
TESTS_FAILED = "The code was run and did not pass. Fix it and write both files again:"
EXAMPLE_FAILED = "Example {index} failed. Its inputs were: {inputs}"
EXAMPLES_DISAGREE = ("The code and these worked examples disagree. One of them is wrong. Check each by hand: "
                     "if the example was wrong, run the build again and type the right answer.")
DISAGREEMENT = "Example {k}"
REASON_SPEC = "no acceptable spec after 3 attempts"
REASON_SKIPPED = "left for later by the person"
REASON_EXAMPLES = "no acceptable examples after 3 attempts"
REASON_CONFIRMED = "fewer than 2 examples were confirmed"
REASON_CODE = "the code did not pass after 3 attempts"
REASON_STOPPED = "stopped by the person"
KIND_WORDS = {"number": "a number", "integer": "a whole number", "date": "a date",
              "boolean": "yes or no", "text": "text", "list": "a list", "object": "a few named values"}

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
RESPOND_SCHEMA = {"type": "object", "properties": {
    "action": {"type": "string", "enum": ["correct", "explain", "note", "skip"]},
    "answer": {}, "message": _TEXT},
    "required": ["action"]}
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
RESPOND = ToolSpec(
    name="respond",
    description=("Say what the person meant by their reply: correct (the right answer, transcribed), explain "
                 "(a short plain answer to their question), note (they described their own situation) or skip."),
    input_schema=RESPOND_SCHEMA)
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
    for step in brief.get("process", []):
        if str(step.get("id")).startswith(ADDED_PREFIX):
            raise ValueError(RESERVED_ID.format(id=step["id"]))
    return {key: value for key, value in brief.items() if key != "meta"}


def build_step(*, model, conn, brief, step, ask, say=print, session_id, rebuild=None) -> dict:
    """Build a module for one calculation step, a brief step or an added step. Returns its result.

    `ask(text)` shows text to the person and returns what they typed.
    `say(text)` shows text that needs no answer.
    With `rebuild=NAME`, that registered module is built again for this step.
    """
    brief = {key: value for key, value in brief.items() if key != "meta"}
    say(STEP_HEADER.format(id=step_label(step["id"]), name=step["name"]))
    name = rebuild                                  # the module to build again, if there is one
    if rebuild is None and step["id"] in step_map(conn):
        name = step_map(conn)[step["id"]]
        if file_status(conn, name) == "unchanged":
            return {"step": step["id"], "outcome": "kept", "module": name, "reason": ""}
    try:
        result = _build_step(model, conn, brief, step, name, ask, say, session_id)
    except Stopped:
        result = {"step": step["id"], "outcome": "not_built", "module": None, "reason": REASON_STOPPED}
    if result["outcome"] == "not_built":
        _record_not_built(conn, session_id, result)
    return result


def build(*, model, conn, brief, ask, say=print, session_id, rebuild=None) -> list[dict]:
    """Build a module for each calculation step of the process. Returns one result per step handled.

    With `rebuild=NAME`, only that registered module is built again.
    """
    brief = {key: value for key, value in brief.items() if key != "meta"}
    steps = process_steps(conn, brief)
    if rebuild is not None:
        registered = get_module(conn, rebuild)
        if registered is None:
            raise ValueError(NOT_REGISTERED.format(name=rebuild))
        step_id = registered["spec"]["step_id"]
        found = [step for step in steps if step["id"] == step_id]
        if not found:
            raise ValueError(NO_STEP.format(step=step_id, name=rebuild))
        todo = found[:1]
    else:
        todo = [step for step in steps if step.get("kind") == "calculation"]

    results = []
    for step in todo:
        result = build_step(model=model, conn=conn, brief=brief, step=step, ask=ask, say=say,
                            session_id=session_id, rebuild=rebuild)
        results.append(result)
        if result["reason"] == REASON_STOPPED:
            break
    return results


def _record_not_built(conn, session_id, result) -> None:
    db.record_event(conn, session_id=session_id, kind="calc.step_not_built", actor="harness",
                    payload={"step": result["step"], "reason": result["reason"]})


def _build_step(model, conn, brief, step, rebuild, ask, say, session_id) -> dict:
    """Run the phases for one step. `rebuild` is the name of the module being built again, or None."""
    def record(kind, actor, payload):
        db.record_event(conn, session_id=session_id, kind=kind, actor=actor, payload=payload)

    def done(outcome, module=None, reason=""):
        return {"step": step["id"], "outcome": outcome, "module": module, "reason": reason}

    kind, value = _phase_spec(model, conn, brief, step, rebuild, ask, say, record, session_id)
    if kind == "reused":
        return done("reused", value)
    if kind == "ended":
        return done("not_built", reason=value)
    spec = value

    examples = _phase_examples(model, step, spec, say, record)
    if examples is None:
        return done("not_built", reason=REASON_EXAMPLES)
    golden, shown = _check_examples(model, conn, step, examples, spec, ask, say, record, session_id)
    if len(golden) < MIN_CONFIRMED:
        return done("not_built", reason=REASON_CONFIRMED)

    if not _phase_code(model, conn, step, spec, golden, shown, record, say, session_id):
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


def _converse(model, system: str, messages: list, tools: list, handle, say, progress: str):
    """One phase: up to MAX_ATTEMPTS model calls. Returns what `handle` accepted, or None.

    `handle(call, attempt)` returns (tool result text, is_error, accepted or None).
    `messages` is extended in place; an accepted call's assistant message is left at its end.
    """
    names = [tool.name for tool in tools]
    for attempt in range(1, MAX_ATTEMPTS + 1):
        say(progress.format(attempt=attempt))
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
        messages.append({"role": "assistant", "content": response.text, "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.tool_calls]})
        if accepted is not None:
            return accepted
        messages.append({"role": "tool", "tool_call_id": first.id, "content": content, "is_error": is_error})
        for call in others:
            messages.append({"role": "tool", "tool_call_id": call.id, "content": ONE_CALL, "is_error": True})
    return None


def _bullets(heading: str, lines: list[str]) -> str:
    return heading + "\n" + "\n".join(f"- {line}" for line in lines)


# --- Phase 1: the spec, and the plan check ---------------------------------------

def _phase_spec(model, conn, brief, step, rebuild, ask, say, record, session_id):
    """The spec and the plan check. Returns ("spec", spec), ("reused", name) or ("ended", reason)."""
    others = [module["spec"] for module in list_modules(conn)
              if module["name"] != rebuild and file_status(conn, module["name"]) == "unchanged"]
    sections = {"step": step, "brief": brief, "registered modules": others, "notes": list_notes(conn)}
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

    messages = [{"role": "user", "content": format_sections(sections)}]
    accepted = _converse(model, system, messages, tools, handle, say, WRITING_SPEC)
    if accepted is None:
        return "ended", REASON_SPEC

    sent = shown = 0                                # feedback sent back, and times the plan was shown
    while not isinstance(accepted, str):
        spec, shown = accepted, shown + 1
        say(plan_words(spec))
        text = _plan_answer(ask)
        decision = "accepted" if text.lower() in ACCEPT_WORDS else "skipped" if text == "/skip" else "feedback"
        record("calc.plan_decision", "person", {"step": step["id"], "round": shown,
                                                "decision": decision, "text": text})
        if decision == "accepted":
            return "spec", spec
        if decision == "skipped":
            return "ended", REASON_SKIPPED
        add_note(conn, step_id=step["id"], text=text, session_id=session_id)
        if sent == MAX_PLAN_ROUNDS:
            record("calc.plan_kept", "harness", {"step": step["id"], "reason": "rounds"})
            say(PLAN_KEPT)
            return "spec", spec
        sent += 1
        first, *rest = messages[-1]["tool_calls"]
        messages.append({"role": "tool", "tool_call_id": first["id"], "is_error": False,
                         "content": PLAN_FEEDBACK.format(text=text)})
        for call in rest:
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": ONE_CALL, "is_error": True})
        accepted = _converse(model, system, messages, tools, handle, say, WRITING_SPEC)
        if accepted is None:
            record("calc.plan_kept", "harness", {"step": step["id"], "reason": "spec"})
            say(PLAN_KEPT)
            return "spec", spec
    return "reused", accepted


def _plan_answer(ask) -> str:
    """Ask whether the plan fits until the person answers. Returns the stripped answer."""
    while True:
        answer = ask(PLAN_QUESTION).strip()
        if answer == "/quit":
            raise Stopped
        if answer:
            return answer


def plan_words(spec: dict) -> str:
    """The spec in plain words, for the person (SPEC 5.7)."""
    lines = [f"To work this out: {spec['formula'].replace('_', ' ')}", "I will need from you:"]
    lines += [f"  - {item['name'].replace('_', ' ')} ({KIND_WORDS[item['type']]}): {item['description']}"
              for item in spec["inputs"]]
    lines.append(f"It gives back: {spec['output']['description']}")
    return "\n".join(lines)


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

def _phase_examples(model, step, spec, say, record):
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

    messages = [{"role": "user", "content": format_sections({"spec": spec, "step": step})}]
    return _converse(model, system, messages, [PROPOSE_EXAMPLES], handle, say, WRITING_EXAMPLES)


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
        missing = unbacked(json.dumps(example["expected"], ensure_ascii=False), [example["working"]])
        if missing:
            problems.append(f"example {k}: the expected answer has numbers its working does not show: "
                            + ", ".join(missing))
    return problems


# --- Showing values ------------------------------------------------------------

def _short(value) -> bool:
    return not isinstance(value, (list, dict)) or not value


def show(value, indent: int = 0) -> str:
    """A JSON value as readable text, without JSON (SPEC 5.7)."""
    if _short(value):
        if value is None or value == [] or value == {}:
            return "(none)"
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, str):
            return value or "(none)"
        return json.dumps(value)
    if isinstance(value, dict):
        return "\n".join(field(key, item, indent) for key, item in value.items())
    lines = []
    for i, item in enumerate(value, start=1):
        mark = f"{i}. "
        if _short(item):
            lines.append(" " * indent + mark + show(item))
        else:
            body = show(item, indent + len(mark))
            lines.append(" " * indent + mark + body[indent + len(mark):])
    return "\n".join(lines)


def field(label: str, value, indent: int) -> str:
    """One labelled value: on the same line when it is short, else the lines of `show` below it."""
    if _short(value):
        return f"{' ' * indent}{label}: {show(value)}"
    return f"{' ' * indent}{label}:\n{show(value, indent + 2)}"


# --- The person checks every example -------------------------------------------

def _example_block(k: int, n: int, example: dict, spec: dict) -> str:
    lines = [f"Example {k} of {n}"]
    lines += [field(item["name"].replace("_", " "), example["inputs"][item["name"]], 2) for item in spec["inputs"]]
    lines += [field("Working", example["working"], 2), field("Proposed answer", example["expected"], 2)]
    return "\n".join(lines)


def _check_examples(model, conn, step, examples, spec, ask, say, record, session_id):
    """The person checks every example. Returns the confirmed ones, as golden.json holds them, and the
    number each was shown with (k of "Example k of n"), in the same order."""
    say(EXAMPLES_INTRO)
    golden, shown = [], []
    for k, example in enumerate(examples, start=1):
        say(_example_block(k, len(examples), example, spec))
        decision, expected = _decide(model, conn, step, spec, example, k, ask, say, record, session_id)
        record("calc.golden_decision", "person", {"module": spec["name"], "index": k, "decision": decision,
                                                  "expected": None if decision == "skipped" else expected})
        if decision != "skipped":
            golden.append({"inputs": example["inputs"], "expected": expected,
                           "working": example["working"], "decision": decision})
            shown.append(k)
    return golden, shown


def _decide(model, conn, step, spec, example, k, ask, say, record, session_id):
    """Ask until the person accepts, skips or corrects. Returns (decision, confirmed answer)."""
    kind = spec["output"]["type"]
    waiting = ()                                    # the transcribed answer waiting for a yes, if any
    replies = []                                    # the free text typed about this example
    while True:
        answer = ask(CONFIRM_ANSWER if waiting else CONFIRM_EXAMPLE).strip()
        if answer == "":
            continue
        if answer == "/quit":
            raise Stopped
        if answer.lower() in ACCEPT_WORDS:
            return ("corrected", waiting[0]) if waiting else ("accepted", example["expected"])
        if answer == "/skip":
            return "skipped", None
        try:
            return "corrected", _read_answer(answer, kind)
        except ValueError:
            pass

        replies.append(answer)                      # free text: one call to the example helper
        record("calc.example_reply", "person", {"module": spec["name"], "index": k, "text": answer})
        say(READING_REPLY)
        shown, waiting = (waiting[0] if waiting else None), ()
        problem, arguments = _ask_helper(model, spec, example, shown, replies)
        if problem:
            record("calc.helper_rejected", "harness", {"module": spec["name"], "index": k,
                                                       "problem": problem, "arguments": arguments})
            say(NOT_UNDERSTOOD)
            continue
        record("calc.helper_answer", "agent", {"module": spec["name"], "index": k, "arguments": arguments})
        if arguments["action"] == "correct":
            say(field("Your answer", arguments["answer"], 2))
            waiting = (arguments["answer"],)
        elif arguments["action"] == "explain":
            say(arguments["message"].strip())
        elif arguments["action"] == "note":
            add_note(conn, step_id=step["id"], text=answer, session_id=session_id)
            say(NOTE_KEPT)
        else:
            return "skipped", None


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
    raise ValueError("free text")                   # text, list and object are never read directly


def _ask_helper(model, spec, example, shown, replies):
    """One call to the example helper (SPEC 5.7). Returns (problem, arguments); no problem means a valid call."""
    proposed = {key: example[key] for key in ("inputs", "expected", "working")}
    sections = {"spec": spec, "example": proposed, "answer shown": shown, "replies": replies}
    response = model.complete(system=Path(__file__).with_name("example_helper.md").read_text(encoding="utf-8"),
                              messages=[{"role": "user", "content": format_sections(sections)}], tools=[RESPOND])
    if not response.tool_calls or response.tool_calls[0].name != "respond":
        return "no tool call", None
    arguments = response.tool_calls[0].arguments
    sources = [proposed, *replies]
    kind = spec["output"]["type"]
    if arguments.get("action") not in ("correct", "explain", "note", "skip"):
        return "unknown action", arguments
    if arguments["action"] == "correct":
        if "answer" not in arguments:
            return "no answer", arguments
        answer = arguments["answer"]
        try:
            from_json(answer, kind)
        except ValueError as error:
            return f"the answer does not fit: {error}", arguments
        if kind == "object" and set(answer) != set(example["expected"]):
            return ("the answer must have exactly these keys: " + ", ".join(example["expected"]), arguments)
        missing = unbacked(json.dumps(answer, ensure_ascii=False), sources)
        if missing:
            return "unbacked numbers: " + ", ".join(missing), arguments
    if arguments["action"] == "explain":
        message = arguments.get("message")
        if not isinstance(message, str) or not message.strip():
            return "empty message", arguments
        missing = unbacked(message, sources)
        if missing:
            return "unbacked numbers: " + ", ".join(missing), arguments
    return "", arguments


# --- Phase 3: the code ---------------------------------------------------------

def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _phase_code(model, conn, step, spec, golden, shown, record, say, session_id) -> bool:
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

    messages = [{"role": "user", "content": format_sections({"spec": spec})}]
    registered = bool(_converse(model, system, messages, [WRITE_MODULE], handle, say, WRITING_CODE))
    if not registered:
        _say_disagreement(last_report, golden, shown, say)
    return registered


def _say_disagreement(report: dict, golden: list[dict], shown: list[int], say) -> None:
    """The code failed three times. If worked examples failed, tell the person: one of them may be wrong.

    This goes to the person only; the code writer is never told the expected or the actual answer.
    `shown[i]` is the number golden[i] was shown with, which differs from its position when examples were skipped.
    """
    failing = [example for example in report.get("golden", []) if not example["passed"]]
    if not failing:
        return
    say(EXAMPLES_DISAGREE)
    for example in failing:
        position = example["index"] - 1
        code_gives = field("The code gives", example["got"], 2) if "got" in example else "  The code gives: an error"
        say("\n".join([DISAGREEMENT.format(k=shown[position]),
                       field("You confirmed", golden[position]["expected"], 2), code_gives]))


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
