"""The analyst on the core's main lane (SPEC 5.1).

One analyst turn answers one message of the person: the model works with the tools of the enabled layers
(`run_module`, `save_input`, `change_plan` here) until it gives a reply, which the number check reads
before the person sees it. The model never does arithmetic: a number the person sees, or that goes into a
tool, must be backed by a source (a module result, a saved input, the plan, a note, today, or the person's
own words). A reply with an unbacked number is sent back once, then withheld.
"""
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from ..calc import gate
from ..calc.added import list_added_steps, process_steps
from ..calc.builder import format_sections, plan_of
from ..calc.notes import list_notes
from ..calc.provenance import unbacked
from ..calc.registry import get_module, list_modules, module_for_step, step_status
from ..core import list_messages
from ..grounding.brief import input_ids
from ..grounding.revise import revise_plan
from ..model import ToolSpec
from .figures import figures, input_backing

MAX_CALLS = 10

RUN_MODULE = ToolSpec(
    name="run_module",
    description=("Run a registered module through the gate. Give the module name, every input the spec lists, "
                 "your assumptions (a list of sentences, may be empty) and what you expect the result to be."),
    input_schema={"type": "object", "properties": {
        "module": {"type": "string"}, "inputs": {"type": "object"},
        "assumptions": {"type": "array", "items": {"type": "string"}}, "expected": {"type": "string"}},
        "required": ["module", "inputs", "assumptions", "expected"]})
SAVE_INPUT = ToolSpec(
    name="save_input",
    description=("Save a figure the person gave you, so it is not asked for again. Give a snake_case name, "
                 "the value in plain form and a note on where it came from."),
    input_schema={"type": "object", "properties": {
        "name": {"type": "string"}, "value": {"type": "string"}, "note": {"type": "string"}},
        "required": ["name", "value", "note"]})
CHANGE_PLAN = ToolSpec(
    name="change_plan",
    description=("Change the agreed plan, when the person says the plan itself is wrong. Give the id of the step "
                 "it is about (empty for the whole plan) and the person's own words, copied exactly from what "
                 "they wrote. Never use it on your own idea."),
    input_schema={"type": "object", "properties": {"step": {"type": "string"}, "words": {"type": "string"}},
                  "required": ["step", "words"]})

NUMBERS_CORRECTION = ("[harness] Your reply was not shown. These numbers did not come from a module result in "
                      "this conversation, a saved input, the plan or the person's own words: {numbers}. "
                      "Do not work numbers out yourself: run a module, or leave the number out. Then reply again.")
WITHHELD = ("(The answer was held back, because it held numbers that no tested module produced: {numbers}.)")
WITHHELD_NOTE = ("[harness] Your last reply was not shown to the person, because it contained numbers that "
                 "no module produced: {numbers}.")
INPUTS_UNBACKED = ("These numbers did not come from the person, the plan, a saved input or a module result: "
                   "{numbers}. Ask the person, or run the module that produces them.")
EMPTY_REPLY = "[harness] Your reply was empty. Ask the person for what you need, or give your answer."
TOO_MANY = "(The harness stopped working on this, because it took too many steps. Try asking in a simpler way.)"
BAD_NAME = "The name must be in snake_case, such as monthly_income."
EMPTY_VALUE = "The value is empty."
SAVED = "Saved."
NOT_THEIR_WORDS = "Those are not words the person typed in this conversation. Copy them exactly from their message."
NO_SUCH_TOOL = "There is no tool called {name} here."
NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class Turn:
    """One analyst turn: what tools and hooks get. `runs` are the calc_runs ids made in it; `reply` is the id
    of the message that ended it (the reply, the withheld notice or the stop notice) once it is posted."""
    work: object
    message: dict
    runs: list[int] = field(default_factory=list)
    reply: str | None = None
    withheld: bool = False
    corrections: int = 0
    extra: dict = field(default_factory=dict)        # what a later layer's tools count within the turn

    @property
    def conn(self):
        return self.work.conn

    @property
    def conversation(self) -> str:
        return self.work.conversation

    def today(self) -> str:
        return today_of(self.work.session.memory).isoformat()

    def plan(self) -> dict | None:
        return plan_of(self.work.config)

    def sources(self) -> list:
        """What a number may come from, read afresh at each check (SPEC 5.1)."""
        return number_sources(self.conn, self.work.config, self.conversation, self.work.session.memory)

    def unbacked(self, value) -> list[str]:
        """The numbers in `value` (text, or a JSON value) that no source backs."""
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return unbacked(text, self.sources())

    def record(self, kind: str, payload: dict, actor: str = "harness") -> None:
        self.work.record(kind, payload, actor)


Tool = tuple[ToolSpec, Callable]


def tool_result(call, content: str, error: bool = False) -> dict:
    """The message that answers a tool call. Handlers return this."""
    result = {"role": "tool", "tool_call_id": call.id, "content": content}
    if error:
        result["is_error"] = True
    return result


def today_of(memory: dict) -> date:
    """Today: `memory["today"]` (a date or an ISO date; replay and tests set it), else the clock."""
    found = memory.get("today")
    if isinstance(found, date):
        return found
    if isinstance(found, str):
        return date.fromisoformat(found)
    return date.today()


# --- What numbers may come from, and what the model is told ---

def saved_inputs(conn) -> dict[str, dict]:
    """{name: {"value", "note"}} of the saved inputs, in the order they were first saved."""
    return {row["name"]: {"value": json.loads(row["value"]), "note": row["note"]}
            for row in conn.execute("SELECT * FROM inputs ORDER BY rowid")}


def person_words(conn, conversation: str) -> list[str]:
    return [message["text"] for message in list_messages(conn, conversation) if message["who"] == "you"]


def without_meta(brief: dict | None) -> dict:
    return {key: value for key, value in (brief or {}).items() if key != "meta"}


def number_sources(conn, config, conversation: str, memory: dict) -> list:
    """The sources of the number check: the plan, today, the person's messages, saved inputs, notes, and the
    inputs and results of the runs of this conversation (SPEC 5.1)."""
    found = [without_meta(plan_of(config)), today_of(memory).isoformat(), *person_words(conn, conversation)]
    found += [each["value"] for each in saved_inputs(conn).values()]
    found += [note["text"] for note in list_notes(conn)]
    found += [added for added in list_added_steps(conn)]
    for row in conn.execute("SELECT inputs, output FROM calc_runs WHERE session_id = ?", (conversation,)):
        found += [json.loads(row["inputs"]), json.loads(row["output"])]
    return found


def trace_sources(conn, config, conversation: str, memory: dict, turn_runs=()) -> list[tuple]:
    """The same sources with their labels for `trace`, in order of preference. A run is given with its inputs, so
    a number leads only to a step whose run produced it, never to one that was given it (`trace`). Runs come in
    the order a figure prefers them (SPEC 5.2): those of this turn (`turn_runs`), the most recent first, then the
    earlier ones, the most recent first."""
    found = [("brief", None, without_meta(plan_of(config))), ("today", None, today_of(memory).isoformat())]
    found += [("person", None, text) for text in person_words(conn, conversation)]
    found += [("input", None, each["value"]) for each in saved_inputs(conn).values()]
    found += [("note", None, note["text"]) for note in list_notes(conn)]
    found += [("brief", None, added) for added in list_added_steps(conn)]
    rows = conn.execute("SELECT id, inputs, output FROM calc_runs WHERE session_id = ? ORDER BY id DESC",
                        (conversation,)).fetchall()
    current = set(turn_runs)
    for row in sorted(rows, key=lambda row: row["id"] not in current):        # stable: newest first in each part
        found.append(("run", row["id"], json.loads(row["output"]), json.loads(row["inputs"])))
    return found


def step_of_module(conn, module: str, step_ids: set[str]) -> str | None:
    """The step a module carries out (its own step, from its spec), if the plan still has it."""
    registered = get_module(conn, module)
    step = registered["spec"].get("step_id") if registered else None
    return step if step in step_ids else None


def reply_figures(turn: Turn, text: str) -> list[dict]:
    """The Figures of a reply (SPEC 5.2)."""
    conn, config = turn.conn, turn.work.config
    brief = plan_of(config)
    step_ids = {step["id"] for step in process_steps(conn, brief)} if brief else set()
    ids = set(input_ids(brief).values()) if brief else set()
    modules = {row["id"]: row["module"] for row in conn.execute(
        "SELECT id, module FROM calc_runs WHERE session_id = ?", (turn.conversation,))}
    saved = [(f"in:{name}" if f"in:{name}" in ids else None, each["value"])
             for name, each in saved_inputs(conn).items()]
    return figures(text, trace_sources(conn, config, turn.conversation, turn.work.session.memory, turn.runs),
                   step_of_run=lambda run: step_of_module(conn, modules.get(run, ""), step_ids),
                   input_of=lambda written: input_backing(written, saved))


def sections(work, conn, runs_made: list[int]) -> dict:
    """Layer 3's sections of `## What you know` (SPEC 5.1)."""
    brief = plan_of(work.config) or {}
    process = []
    for step in process_steps(conn, brief) if brief else []:
        shown = {key: value for key, value in step.items() if key != "origin"}
        if step.get("kind") == "calculation":
            shown["module"] = module_for_step(conn, step["id"])
            shown["build"] = step_status(conn, brief, step["id"])[0]
        process.append(shown)
    modules = {module["name"]: {"steps": module["steps"], "spec": module["spec"]} for module in list_modules(conn)}
    runs = [{"run": row["id"], "module": row["module"], "inputs": json.loads(row["inputs"]),
             "output": json.loads(row["output"])}
            for row in conn.execute("SELECT * FROM calc_runs WHERE session_id = ? ORDER BY id DESC LIMIT 8",
                                    (work.conversation,)) if row["id"] not in runs_made][::-1]
    found = {"today": today_of(work.session.memory).isoformat(),
             "goal": (brief.get("goal") or {}).get("text", ""),
             "particulars": [{key: item[key] for key in ("what", "handling", "step") if key in item}
                             for item in brief.get("particulars", [])],
             "inputs the plan names": [_plan_input(item) for item in brief.get("inputs", [])],
             "process": process, "modules": modules, "saved inputs": saved_inputs(conn),
             "notes": list_notes(conn)}
    if runs:
        found["earlier runs in this conversation"] = runs
    return found


def _plan_input(item: dict) -> dict:
    """A brief input for the analyst: name, description and, when the person stated it, their words,
    so a figure they gave while the plan was made is not asked for again."""
    shown = {"name": item["name"], "description": item["description"]}
    origin = item.get("origin") or {}
    if origin.get("kind") == "person" and origin.get("quote"):
        shown["the person said"] = origin["quote"]
    return shown


def system_prompt(turn: Turn) -> str:
    """The prompt parts of the enabled layers, then `## What you know` with their sections, layer 3's first."""
    layers = turn.work.session.layers
    parts = [Path(layer.prompt).read_text(encoding="utf-8").strip() for layer in layers if layer.prompt]
    known = sections(turn.work, turn.conn, turn.runs)
    for layer in layers:
        if layer.number != 3 and layer.context is not None:
            known.update(layer.context(turn.conn))
    return "\n\n".join([*parts, "## What you know\n\n" + format_sections(known)])


# --- Layer 3's tools ---

def tools(turn: Turn) -> list[Tool]:
    return [(RUN_MODULE, run_module), (SAVE_INPUT, save_input), (CHANGE_PLAN, change_plan)]


def run_module(turn: Turn, call) -> dict:
    """The inputs and the assumptions are number-checked, then the gate runs the module. Never held for the person."""
    arguments = call.arguments
    shown = {"inputs": arguments.get("inputs"), "assumptions": arguments.get("assumptions")}
    numbers = turn.unbacked(shown)
    if numbers:
        turn.corrections += 1
        turn.record("ask.correction", {"reason": "run_module", "numbers": numbers, "text": json.dumps(arguments)})
        return tool_result(call, INPUTS_UNBACKED.format(numbers=", ".join(numbers)), True)
    module = arguments.get("module")
    registered = get_module(turn.conn, module) if isinstance(module, str) else None
    step = registered["spec"].get("step_id") if registered else None
    turn.work.progress(f"running {module}", step=step)
    try:
        result = gate.call(turn.conn, module, arguments.get("inputs"), assumptions=arguments.get("assumptions"),
                           expected=arguments.get("expected"), session_id=turn.conversation)
    except gate.Refused as refused:
        turn.work.changed()
        return tool_result(call, str(refused), True)
    turn.runs.append(result["run_id"])
    turn.work.changed()
    return tool_result(call, json.dumps({"module": result["module"], "run_id": result["run_id"],
                                         "output": result["output"]}))


def save_input(turn: Turn, call) -> dict:
    arguments = call.arguments
    name, value, note = arguments.get("name"), arguments.get("value"), arguments.get("note", "")
    if not isinstance(name, str) or not NAME.match(name):
        return tool_result(call, BAD_NAME, True)
    if not str(value if value is not None else "").strip():
        return tool_result(call, EMPTY_VALUE, True)
    numbers = turn.unbacked(value)
    if numbers:
        turn.corrections += 1
        turn.record("ask.correction", {"reason": "save_input", "numbers": numbers, "text": json.dumps(arguments)})
        return tool_result(call, INPUTS_UNBACKED.format(numbers=", ".join(numbers)), True)
    turn.conn.execute(
        "INSERT INTO inputs (name, value, note, ts, session_id) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(name) DO UPDATE SET value = excluded.value, note = excluded.note,"
        " ts = excluded.ts, session_id = excluded.session_id",
        (name, json.dumps(value), str(note), datetime.now(timezone.utc).isoformat(), turn.conversation))
    turn.conn.commit()
    turn.record("ask.input_saved", {"name": name, "value": value, "note": note}, "agent")
    turn.work.changed()
    return tool_result(call, SAVED)


def spaced(text: str) -> str:
    return " ".join(text.casefold().split())


def change_plan(turn: Turn, call) -> dict:
    """The person's words change the plan (ARCHITECTURE.md 10, question 1): `words` must be in a message they typed."""
    arguments = call.arguments
    words, step = arguments.get("words"), arguments.get("step") or None
    typed = [spaced(text) for text in person_words(turn.conn, turn.conversation)]
    if not isinstance(words, str) or not spaced(words) or not any(spaced(words) in text for text in typed):
        return tool_result(call, NOT_THEIR_WORDS, True)
    result = revise_plan(turn.work, words=words, step=step if isinstance(step, str) else None, by="person")
    turn.record("ask.plan_changed", {"step": step, "words": words, **result}, "agent")
    turn.work.changed()
    return tool_result(call, json.dumps(result), "error" in result)


# --- A turn ---

def memory_of(session) -> dict:
    """The analyst's in-memory conversation with the model: kept for the life of the Session, and begun again
    in a new conversation."""
    entry = session.memory.get("analyst")
    if entry is None or entry["conversation"] != session.conversation:
        entry = session.memory["analyst"] = {"conversation": session.conversation, "messages": [], "note": ""}
    return entry


def question_for_model(turn: Turn, message: dict) -> str:
    """The person's message as the model reads it: a step attached to it is said first (SPEC 5.1)."""
    step = message.get("step")
    if not step:
        return message["text"]
    brief = plan_of(turn.work.config)
    name = next((each["name"] for each in process_steps(turn.conn, brief) if each["id"] == step), "") if brief else ""
    return f"[harness] About step {step}{f' ({name})' if name else ''}: {message['text']}"


def answer(work, message: dict) -> None:
    """Answer one message of the person: the analyst turn (a main-lane handler)."""
    turn = Turn(work=work, message=message)
    memory = memory_of(work.session)
    messages = memory["messages"]
    start = len(messages)
    work.record("ask.message", {"text": message["text"], "step": message.get("step")}, "person")
    messages.append({"role": "user", "content": question_for_model(turn, message) + memory["note"]})
    memory["note"] = ""
    try:
        text, who, kind, note = _run_turn(turn, messages)
    except Exception:
        del messages[start:]            # a failed model call leaves no half turn behind
        raise
    memory["note"] = note
    data = {"_runs": turn.runs}
    if who == "assistant":
        data["figures"] = reply_figures(turn, text)
    turn.reply = work.post(text, who=who, kind=kind, data=data)
    if who == "assistant":
        turn.record("ask.reply", {"text": text, "message": turn.reply, "runs": turn.runs}, "agent")
    work.hook("turn_finished", work, turn)


def _run_turn(turn: Turn, messages: list) -> tuple[str, str, str, str]:
    """Work until there is something to show. Returns (text, who, message kind, a note for the next message)."""
    work, collected = turn.work, []
    for layer in work.session.layers:
        if layer.tools is not None:
            collected += layer.tools(turn)
    specs = [spec for spec, _ in collected]
    handlers = {spec.name: handle for spec, handle in collected}
    corrected = False
    for _ in range(MAX_CALLS):
        work.progress("thinking")
        response = work.model.complete(system=system_prompt(turn), messages=messages, tools=specs)
        if response.tool_calls:                         # its text is not shown
            results = []
            for call in response.tool_calls:
                handle = handlers.get(call.name)
                results.append(handle(turn, call) if handle else tool_result(call, NO_SUCH_TOOL.format(name=call.name), True))
            messages.append({"role": "assistant", "content": response.text, "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.tool_calls]})
            messages.extend(results)
            continue
        text = response.text.strip()
        if not text:
            messages.append({"role": "user", "content": EMPTY_REPLY})
            continue
        numbers = turn.unbacked(text)
        if numbers and not corrected:
            corrected = True
            turn.corrections += 1
            turn.record("ask.correction", {"reason": "reply", "numbers": numbers, "text": text})
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": NUMBERS_CORRECTION.format(numbers=", ".join(numbers))})
            continue
        messages.append({"role": "assistant", "content": text})
        if numbers:
            turn.withheld = True
            turn.record("ask.withheld", {"numbers": numbers, "text": text})
            joined = ", ".join(numbers)
            return WITHHELD.format(numbers=joined), "harness", "withheld", "\n\n" + WITHHELD_NOTE.format(numbers=joined)
        return text, "assistant", "text", ""
    turn.record("ask.stopped", {"reason": "too many steps"})
    return TOO_MANY, "harness", "text", ""
