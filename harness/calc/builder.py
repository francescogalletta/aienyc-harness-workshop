"""The unattended build (SPEC 4.3): turns each calculation step of the plan into a registered module.

For a step, three model phases, each its own conversation, and a second pass:

1. the spec (or `reuse_module`), with the ways it departs from the plan;
2. three to five worked examples, by the example writer;
3. the second pass (`checker.py`) works out each example's answer without
   seeing the writer's; only examples both agree on (or the person confirmed)
   are kept as `golden.json`;
4. the code, written from the spec alone, never seeing the examples; the
   harness runs its tests and the examples, and registers it on a pass.

Nothing waits on the person. A step that cannot be finished ends `not_built`
with a reason, and the build goes on to the next.

What other packages call (ARCHITECTURE.md section 11, A2a):
`start_build(core)`, `run_build(work)`, `build_step(work, step, rebuild=, code_only=)`,
`building_step(memory)`, `build_running(memory)`, `record_confirmation(...)`,
`confirm_departures(...)`, `run_step_tests(...)`, `format_sections(...)`.
"""
import ast
import json
import shutil
from pathlib import Path

from .. import db
from ..config import load_config
from ..core import NotNow
from ..grounding.brief import load_brief
from ..model import ToolSpec
from .gate import run_tests
from .notes import list_notes
from .provenance import unbacked
from .registry import (MIN_CONFIRMED, calculation_steps, examples_from_golden, file_status, find_step, get_build,
                       get_module, input_problems, list_modules, map_step, module_dir, module_for_step,
                       plan_fingerprint, register, save_build, step_status, update_build, validate_spec)
from .safety import check_code
from .values import TYPES, from_json, same

MAX_ATTEMPTS = 3
MIN_EXAMPLES = 3
MEMORY = "calc"                         # this layer's entry in core.memory

NO_PLAN = "There is no accepted plan to build yet."
ALREADY_BUILDING = "The build is already running."
BUILD_DONE = "{built} of {total} calculation steps are built and tested."
BUILD_NEEDS_YOU = "These need you: {steps}. Click one to see why."

REASON_SPEC = "no acceptable spec"
REASON_EXAMPLES = "no acceptable examples"
REASON_SECOND_PASS = "the second pass did not agree with enough examples"
REASON_CODE = "the code did not pass"
REASON_TESTS = "its tests do not pass here"

STARTING = "starting the build"
WRITING_SPEC = "writing the spec, attempt {attempt}"
WRITING_EXAMPLES = "writing worked examples, attempt {attempt}"
MORE_EXAMPLES_TEXT = "writing more worked examples, attempt {attempt}"
CHECKING = "second pass on {count} examples"
WRITING_CODE = "writing the code, attempt {attempt}"
RUNNING_TESTS = "running the tests"

USE_TOOL = "[harness] Reply only by calling {tools}."
ONE_CALL = "Only one tool call is handled per reply. This one was ignored."
SPEC_REJECTED = "The spec was not accepted. Fix these and propose it again:"
NAME_TAKEN = "a module called '{name}' already exists: reuse it, or choose another name"
CANNOT_REUSE = "There is no registered module called '{name}' with unchanged files. Propose a spec instead."
BAD_DEPARTURES = ("departures must be a list, one entry per way the spec departs from the step, each with a kind ("
                  + ", ".join(("formula", "input", "left_out", "output", "made_exact")) + ") and a plain sentence as "
                  "text; [] when none")
DEPARTURE_KINDS = ("formula", "input", "left_out", "output", "made_exact")
NOT_A_DEPARTURE = "made_exact"      # the brief's own step made exact: kept out of the plan check
EXAMPLES_REJECTED = "The examples were not accepted. Fix these and propose them again:"
MORE_EXAMPLES = ("[harness] The second pass agreed with too few of these examples. Write three to five new examples "
                 "with different inputs, simpler where you can.")
CODE_REJECTED = "The code was not accepted. Fix these and write both files again:"
TESTS_FAILED = "The code was run and did not pass. Fix it and write both files again:"
EXAMPLE_FAILED = "Example {index} failed. Its inputs were: {inputs}"

_TEXT = {"type": "string"}
_TYPE = {"type": "string", "enum": list(TYPES)}
SPEC_SCHEMA = {"type": "object", "properties": {
    "name": _TEXT, "description": _TEXT, "method": _TEXT, "formula": _TEXT,
    "inputs": {"type": "array", "items": {"type": "object", "properties": {
        "name": _TEXT, "type": _TYPE, "description": _TEXT}, "required": ["name", "type", "description"]}},
    "output": {"type": "object", "properties": {"type": _TYPE, "description": _TEXT},
               "required": ["type", "description"]},
    "departures": {"type": "array", "items": {"type": "object", "properties": {
        "kind": {"type": "string", "enum": list(DEPARTURE_KINDS)}, "text": _TEXT}, "required": ["kind", "text"]}}},
    "required": ["name", "description", "method", "formula", "inputs", "output", "departures"]}
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
                 "its typed inputs, its typed output, and every way it departs from the step. The harness checks it."),
    input_schema=SPEC_SCHEMA)
REUSE_MODULE = ToolSpec(
    name="reuse_module",
    description="Use a registered module that already does this step's job, instead of writing a new one.",
    input_schema=REUSE_SCHEMA)
PROPOSE_EXAMPLES = ToolSpec(
    name="propose_examples",
    description=("Propose worked examples for the spec: the inputs, the exact expected answer and one line "
                 "of working each. A second pass checks them independently."),
    input_schema=EXAMPLES_SCHEMA)
WRITE_MODULE = ToolSpec(
    name="write_module",
    description="Send the two files: module.py with the function calculate, and tests.py with its unit tests.",
    input_schema=CODE_SCHEMA)

SPEC_FILE_KEYS = ("name", "description", "step_id", "method", "formula", "inputs", "output")


# --- What the core and later layers call ------------------------------------------------

def _memory(memory: dict) -> dict:
    return memory.setdefault(MEMORY, {"building": None, "running": False})


def building_step(memory: dict) -> str | None:
    """The id of the step being built right now, or None. `memory` is `core.memory` (or `view.memory`)."""
    return _memory(memory).get("building")


def build_running(memory: dict) -> bool:
    """Whether the build job (`run_build`) is running now."""
    return bool(_memory(memory).get("running"))


def plan_of(config) -> dict | None:
    """The confirmed brief, with its meta, or None."""
    return load_brief(config.brief_dir)


def start_build(core) -> None:
    """Queue the unattended build on the main lane. Raises NotNow without a confirmed plan, or while a build
    is queued or running. (The `build` action.)"""
    from ..grounding.layer import phase_of

    if phase_of(core) != "accepted":
        raise NotNow(NO_PLAN)
    if build_running(core.memory) or not core.queue("main", run_build, what="build", text=STARTING, key="build"):
        raise NotNow(ALREADY_BUILDING)


def run_build(work) -> dict:
    """The build job: every calculation step in plan order whose status is none, not built or stale is built;
    a built one is kept. Records `build.finished` and posts BUILD_DONE (and BUILD_NEEDS_YOU). Returns
    {step id: outcome}."""
    state = _memory(work.session.memory)
    state["running"] = True
    try:
        work.progress(STARTING, what="build")
        brief = plan_of(work.config)
        outcomes = {}
        for step in calculation_steps(work.conn, brief):
            status, _ = step_status(work.conn, brief, step["id"])
            if status == "built":
                outcomes[step["id"]] = "kept"
                continue
            outcomes[step["id"]] = build_step(work, step)["outcome"]
            brief = plan_of(work.config)                  # a hook may have changed the plan
        steps = calculation_steps(work.conn, brief)
        built = [step for step in steps if step_status(work.conn, brief, step["id"])[0] == "built"]
        stuck = [step for step in steps if step_status(work.conn, brief, step["id"])[0] == "not_built"]
        work.record("build.finished", {"steps": outcomes})
        work.post(BUILD_DONE.format(built=len(built), total=len(steps)), who="harness")
        if stuck:
            work.post(BUILD_NEEDS_YOU.format(steps=", ".join(step["name"] for step in stuck)), who="harness")
        return outcomes
    finally:
        state["running"] = False
        work.changed()


def build_step(work, step, *, rebuild: str | None = None, code_only: bool = False) -> dict:
    """Build one calculation step (a dict from the plan, or its id). Returns {"step", "outcome", "module",
    "reason"}, outcome `built`, `reused` or `not_built`.

    `rebuild=NAME` builds that registered module again for this step (by default the step's own module, when
    it has one). `code_only` reruns only the code phase with the stored spec and examples, as they stand after
    the person's confirmations. Calls the hook `step_built` at the end."""
    brief = plan_of(work.config)
    if isinstance(step, str):
        found = find_step(work.conn, brief, step)
        if found is None:
            raise ValueError(f"the plan has no calculation step '{step}'")
        step = found
    state = _memory(work.session.memory)
    state["building"] = step["id"]
    work.progress(WRITING_SPEC.format(attempt=1) if not code_only else WRITING_CODE.format(attempt=1),
                  step=step["id"], what="build")
    work.record("build.started", {"step": step["id"], "code_only": code_only, "rebuild": rebuild})
    try:
        builder = _Builder(work, brief, step)
        result = builder.code_only() if code_only else builder.build(rebuild)
    finally:
        state["building"] = None
        work.changed()
    if result["outcome"] == "not_built":
        work.record("build.not_built", {"step": step["id"], "reason": result["reason"],
                                        "error": result.pop("error", "")})
    result.pop("error", None)
    work.hook("step_built", work, step["id"])
    return result


def record_confirmation(conn, step_id: str, n: int, *, answer=None, session_id: str) -> dict:
    """The person confirmed example `n` of a step (`answer` None: as it stands) or corrected it (`answer`:
    the right answer, in the output type). Stored in `example_confirmations`; the example becomes
    `checked_by: "you"` in the build record. Returns {"rebuild": bool}: true when the module must be built
    again with `code_only` (a corrected answer, or an example that was not among the tested ones).
    Raises ValueError for an unknown example or an answer that does not fit the output type."""
    record = get_build(conn, step_id)
    example = next((each for each in (record or {}).get("examples", []) if each.get("n") == n), None)
    if example is None:
        raise ValueError(f"step {step_id} has no example {n}")
    if answer is not None:
        from_json(answer, record["spec"]["output"]["type"])
    corrected = answer is not None and not same(example["expected"], answer)
    tested = example.get("checked_by") in ("second_pass", "you") and record["status"] == "built"
    final = answer if answer is not None else example["expected"]
    conn.execute("INSERT INTO example_confirmations (ts, step_id, n, answer) VALUES (?, ?, ?, ?)",
                 (db.now(), step_id, n, json.dumps(final)))
    conn.commit()
    example.update(expected=final, checked_by="you")
    update_build(conn, step_id, examples=record["examples"])
    db.record_event(conn, session_id=session_id, actor="person",
                    kind="build.example_corrected" if corrected else "build.example_confirmed",
                    payload={"step": step_id, "n": n, "answer": final})
    return {"rebuild": corrected or not tested}


def read_departures(given) -> tuple[list[str], list[str]] | None:
    """The departures of a proposed spec: (those that put a plan check on the step, those that only make the
    brief's own step exact). An entry is {kind, text}; a plain sentence counts as a departure. None when malformed."""
    if not isinstance(given, list):
        return None
    real, exact = [], []
    for each in given:
        if isinstance(each, str) and each.strip():
            real.append(each.strip())
        elif (isinstance(each, dict) and each.get("kind") in DEPARTURE_KINDS and isinstance(each.get("text"), str)
              and each["text"].strip()):
            (exact if each["kind"] == NOT_A_DEPARTURE else real).append(" ".join(each["text"].split()))
        else:
            return None
    return real, exact


def confirm_departures(conn, step_id: str, *, session_id: str) -> None:
    """The person accepts the ways the step's spec departs from the plan: the plan-check mark goes."""
    record = get_build(conn, step_id)
    if record is None or not record["departures"]:
        raise ValueError(f"step {step_id} has no departures to confirm")
    update_build(conn, step_id, departures_confirmed=True)
    db.record_event(conn, session_id=session_id, kind="build.departures_confirmed", actor="person",
                    payload={"step": step_id, "departures": record["departures"]})


def run_step_tests(conn, step_id: str, *, session_id: str) -> dict:
    """Run the tests of the module of a step now (the `run_tests` action). Returns the run, as
    `gate.run_tests` does. Raises ValueError when the step has no registered module."""
    name = module_for_step(conn, step_id) or (get_build(conn, step_id) or {}).get("module")
    if not name or get_module(conn, name) is None:
        raise ValueError(f"step {step_id} has no registered module")
    return run_tests(conn, name, reason="status", session_id=session_id)


# --- Conversations ---------------------------------------------------------------------

def format_sections(sections: dict) -> str:
    """A user message: a line `[title]` and then the value, one blank line between sections."""
    parts = []
    for title, value in sections.items():
        text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
        parts.append(f"[{title}]\n{text}")
    return "\n\n".join(parts)


def _bullets(heading: str, lines: list[str]) -> str:
    return heading + "\n" + "\n".join(f"- {line}" for line in lines)


def _close_call(messages: list, content: str) -> None:
    """Answer the tool calls of the last assistant message, so the conversation can go on."""
    first, *rest = messages[-1]["tool_calls"]
    messages.append({"role": "tool", "tool_call_id": first["id"], "content": content, "is_error": False})
    for call in rest:
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": ONE_CALL, "is_error": True})


class _Builder:
    """The phases of one step. Each phase's model conversation is its own."""

    def __init__(self, work, brief, step):
        self.work, self.conn, self.brief, self.step = work, work.conn, brief, step
        self.sid = step["id"]
        self.fingerprint = plan_fingerprint(work.conn, brief, step["id"]) or ""
        self.previous = get_build(work.conn, step["id"])
        self.error = ""                     # the last failed model call, for the not_built event

    def record(self, kind, payload, actor="harness"):
        self.work.record(kind, {"step": self.sid, **payload}, actor)

    def done(self, outcome, module=None, reason=""):
        return {"step": self.sid, "outcome": outcome, "module": module, "reason": reason, "error": self.error}

    def not_built(self, reason, *, spec=None, departures=(), examples=(), disagreement=(), module=None):
        confirmed = bool(self.previous and self.previous["departures_confirmed"]
                         and self.previous["departures"] == list(departures))
        save_build(self.conn, self.sid, status="not_built", module=module, spec=spec, departures=departures,
                   departures_confirmed=confirmed, examples=examples, disagreement=disagreement, reason=reason,
                   step_fingerprint=self.fingerprint)
        return self.done("not_built", module, reason)

    def converse(self, system_file, messages, tools, handle, progress):
        """Up to MAX_ATTEMPTS model calls. Returns what `handle` accepted, or None.

        `handle(call, attempt)` returns (tool result text, is_error, accepted or None). `messages` is extended
        in place; an accepted call's assistant message is left at its end. A failed model call counts as an
        attempt."""
        system = Path(__file__).with_name(system_file).read_text(encoding="utf-8")
        names = [tool.name for tool in tools]
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.work.progress(progress.format(attempt=attempt), step=self.sid, what="build")
            try:
                response = self.work.model.complete(system=system, messages=messages, tools=tools)
            except Exception as error:
                self.error = f"{type(error).__name__}: {' '.join(str(error).split())}"[:300]
                continue
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

    # --- The whole step ---

    def build(self, rebuild):
        name = rebuild
        if name is None:
            mapped = module_for_step(self.conn, self.sid)
            if mapped and get_module(self.conn, mapped)["spec"].get("step_id") == self.sid:
                name = mapped                       # the step's own module: build it again under its name
        found = self.spec_phase(name)
        if found[0] == "reused":
            module = found[1]
            save_build(self.conn, self.sid, status="built", module=module, spec=get_module(self.conn, module)["spec"],
                       examples=examples_from_golden(module_dir(module) / "golden.json"),
                       step_fingerprint=self.fingerprint)
            return self.done("reused", module)
        if found[0] == "ended":
            return self.not_built(REASON_SPEC)
        spec, departures = found[1], found[2]

        examples, reason = self.examples_phase(spec)
        if reason:
            return self.not_built(reason, spec=spec, departures=departures, examples=examples)
        return self.code_phase(spec, departures, examples, existing=False)

    def code_only(self):
        if self.previous is None or self.previous["spec"] is None:
            return self.not_built(REASON_SPEC)
        spec, departures = self.previous["spec"], self.previous["departures"]
        examples = self.previous["examples"]
        if len([each for each in examples if each.get("checked_by")]) < MIN_CONFIRMED:
            return self.not_built(REASON_SECOND_PASS, spec=spec, departures=departures, examples=examples)
        return self.code_phase(spec, departures, examples, existing=True)

    # --- Phase 1: the spec ---

    def spec_phase(self, rebuild):
        """Returns ("spec", spec, departures), ("reused", name) or ("ended", None)."""
        conn = self.conn
        others = [module["spec"] for module in list_modules(conn)
                  if module["name"] != rebuild and file_status(conn, module["name"]) == "unchanged"]
        brief = {key: value for key, value in (self.brief or {}).items() if key != "meta"}
        sections = {"step": self.step, "brief": brief, "registered modules": others, "notes": list_notes(conn)}
        current = get_module(conn, rebuild)["spec"] if rebuild else (self.previous or {}).get("spec")
        if current:
            sections["current spec"] = current
        tools = [PROPOSE_SPEC] if rebuild is not None else [PROPOSE_SPEC, REUSE_MODULE]

        def handle(call, attempt):
            if call.name == "reuse_module":
                module = call.arguments.get("module")
                if isinstance(module, str) and get_module(conn, module) and file_status(conn, module) == "unchanged":
                    map_step(conn, self.sid, module)
                    self.record("build.reused", {"module": module, "reason": call.arguments.get("reason", "")},
                                "agent")
                    return "Reused.", False, ("reused", module)
                return CANNOT_REUSE.format(name=module), True, None
            spec = _clean_spec(call.arguments, self.sid, rebuild)
            errors = validate_spec(spec)
            name = spec.get("name")
            if rebuild is None and isinstance(name, str) and get_module(conn, name) is not None:
                errors.append(NAME_TAKEN.format(name=name))
            given = call.arguments.get("departures")
            read = read_departures(given)
            if read is None:
                errors.append(BAD_DEPARTURES)
            if errors:
                self.record("build.spec_rejected", {"errors": errors})
                return _bullets(SPEC_REJECTED, errors), True, None
            departures, made_exact = read
            self.record("build.spec_proposed", {"spec": spec, "departures": departures, "made_exact": made_exact},
                        "agent")
            return "Spec accepted.", False, ("spec", spec, departures)

        messages = [{"role": "user", "content": format_sections(sections)}]
        accepted = self.converse("spec_writer.md", messages, tools, handle, WRITING_SPEC)
        return accepted if accepted is not None else ("ended", None)

    # --- Phase 2 and 3: the examples and the second pass ---

    def examples_phase(self, spec):
        """Returns (examples, reason): every example with `n` and `checked_by`, and "" or why not built."""
        kept = [dict(each) for each in (self.previous or {}).get("examples", [])
                if each.get("checked_by") == "you" and _fits(spec, each)]
        examples = []
        for each in kept:                           # what the person confirmed earlier stays, as theirs
            examples.append({**each, "n": len(examples) + 1})

        def handle(call, attempt):
            proposed = call.arguments.get("examples")
            errors = _example_problems(proposed if isinstance(proposed, list) else [], spec)
            if errors:
                self.record("build.examples_rejected", {"module": spec["name"], "errors": errors})
                return _bullets(EXAMPLES_REJECTED, errors), True, None
            self.record("build.examples_proposed", {"module": spec["name"], "examples": proposed}, "agent")
            return "Examples accepted.", False, proposed

        messages = [{"role": "user", "content": format_sections({"spec": spec, "step": self.step})}]
        proposed = self.converse("example_writer.md", messages, [PROPOSE_EXAMPLES], handle, WRITING_EXAMPLES)
        if proposed is None:
            return examples, (REASON_EXAMPLES if len(examples) < MIN_CONFIRMED else "")
        examples += self.second_pass(spec, proposed, len(examples))
        if _checked(examples) < MIN_CONFIRMED:
            _close_call(messages, "Examples accepted.")
            messages.append({"role": "user", "content": MORE_EXAMPLES})
            proposed = self.converse("example_writer.md", messages, [PROPOSE_EXAMPLES], handle, MORE_EXAMPLES_TEXT)
            if proposed is not None:
                examples += self.second_pass(spec, proposed, len(examples))
        if _checked(examples) < MIN_CONFIRMED:
            return examples, REASON_SECOND_PASS
        return examples, ""

    def second_pass(self, spec, proposed, start):
        """Number the writer's examples from `start + 1`, check them, and mark each checked or left out."""
        from .checker import check_examples

        examples = [{"n": start + k, "inputs": each["inputs"], "expected": each["expected"],
                     "working": each["working"]} for k, each in enumerate(proposed, start=1)]
        self.work.progress(CHECKING.format(count=len(examples)), step=self.sid, what="build")
        verdicts = {each["n"]: each for each in check_examples(self.work.model, spec, examples)}
        for example in examples:
            verdict = verdicts[example["n"]]
            example["checked_by"] = "second_pass" if verdict["agrees"] else None
            example["second_pass"] = None if verdict["agrees"] else verdict["answer"]
        self.record("build.second_pass", {"module": spec["name"],
                                          "agreed": [each["n"] for each in examples if each["checked_by"]],
                                          "left_out": [{"n": each["n"], "answer": each["second_pass"],
                                                        "why": verdicts[each["n"]]["why"],
                                                        "given": verdicts[each["n"]]["given"]}
                                                       for each in examples if not each["checked_by"]]})
        return examples

    # --- Phase 4: the code ---

    def code_phase(self, spec, departures, examples, *, existing):
        """Write, check and test the code in a staging folder; on a pass, move it into place and register.
        With `existing`, the module's present code is tried first against the examples as they now stand."""
        conn, name = self.conn, spec["name"]
        checked = [each for each in examples if each.get("checked_by")]
        golden = [{"inputs": each["inputs"], "expected": each["expected"], "working": each["working"],
                   "checked_by": each["checked_by"]} for each in checked]
        staging = load_config().modules_dir / "_build" / name
        present = None                              # the code there is now: the module's, else the last attempt's
        for folder in (module_dir(name), staging) if existing else ():
            if (folder / "module.py").is_file() and (folder / "tests.py").is_file():
                present = ((folder / "module.py").read_text(encoding="utf-8"),
                           (folder / "tests.py").read_text(encoding="utf-8"))
                break
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        _write_json(staging / "spec.json", spec)
        _write_json(staging / "golden.json", golden)
        last = {}                                   # the report of the latest run, never shown to the writer
        session_id = self.work.conversation

        def try_files(module_py, tests_py):
            (staging / "module.py").write_text(module_py, encoding="utf-8")
            (staging / "tests.py").write_text(tests_py, encoding="utf-8")
            self.work.progress(RUNNING_TESTS, step=self.sid, what="build")
            run = run_tests(conn, name, reason="build", session_id=session_id, folder=staging)
            last.clear()
            last.update(run["report"])
            if not run["passed"]:
                return False
            if module_dir(name).exists():
                shutil.rmtree(module_dir(name))
            module_dir(name).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging), str(module_dir(name)))
            register(conn, name, step_id=self.sid, test_run_id=run["test_run_id"], session_id=session_id,
                     step_fingerprint=self.fingerprint)
            return True

        registered = try_files(*present) if present else False

        def handle(call, attempt):
            module_py, tests_py = (call.arguments.get(key) for key in ("module_py", "tests_py"))
            module_py = module_py if isinstance(module_py, str) else ""
            tests_py = tests_py if isinstance(tests_py, str) else ""
            self.record("build.code_written", {"module": name, "attempt": attempt, "module_py": module_py,
                                               "tests_py": tests_py}, "agent")
            problems = _code_problems(module_py, tests_py, spec)
            if problems:
                self.record("build.code_rejected", {"module": name, "attempt": attempt, "problems": problems})
                return _bullets(CODE_REJECTED, problems), True, None
            if not try_files(module_py, tests_py):
                return _failure_text(last, golden), True, None
            return "Registered.", False, True

        if not registered:
            messages = [{"role": "user", "content": format_sections({"spec": spec})}]
            registered = bool(self.converse("module_writer.md", messages, [WRITE_MODULE], handle, WRITING_CODE))
        if not registered:
            disagreement = [{"n": checked[each["index"] - 1]["n"], "expected": checked[each["index"] - 1]["expected"],
                             "code_gives": each["got"] if "got" in each else "an error"}
                            for each in last.get("golden", []) if not each["passed"]]
            registered_before = get_module(conn, name) is not None and module_for_step(conn, self.sid) == name
            return self.not_built(REASON_CODE, spec=spec, departures=departures, examples=examples,
                                  disagreement=disagreement, module=name if registered_before else None)
        confirmed = bool(self.previous and self.previous["departures_confirmed"]
                         and self.previous["departures"] == list(departures))
        save_build(conn, self.sid, status="built", module=name, spec=spec, departures=departures,
                   departures_confirmed=confirmed, examples=examples, step_fingerprint=self.fingerprint)
        return self.done("built", name)


# --- Checks --------------------------------------------------------------------------------

def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _checked(examples) -> int:
    return len([each for each in examples if each.get("checked_by")])


def _fits(spec, example) -> bool:
    if input_problems(spec, example.get("inputs")):
        return False
    try:
        from_json(example.get("expected"), spec["output"]["type"])
    except ValueError:
        return False
    return True


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
        missing = unbacked(json.dumps(example["expected"], ensure_ascii=False),
                           [example["working"], example["inputs"]])
        if missing:
            problems.append(f"example {k}: the expected answer has numbers that neither its working nor its "
                            "inputs show: "
                            + ", ".join(missing))
    return problems


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
    for test in report.get("tests", []):
        if not test["passed"]:
            lines.append(f"- {test['name']} failed:\n{test.get('error', '')}")
    for example in report.get("golden", []):
        if not example["passed"]:
            inputs = json.dumps(golden[example["index"] - 1]["inputs"], ensure_ascii=False)
            line = "- " + EXAMPLE_FAILED.format(index=example["index"], inputs=inputs)
            if example.get("error"):
                line += f" It stopped with: {example['error']}"
            lines.append(line)
    return "\n".join([TESTS_FAILED] + lines)
