"""The agent that answers questions about the plan (SPEC 5.9).

It runs modules through the gate and saves what the person tells it. It
never works a number out itself: the harness checks every number it sends
out, and every number it passes to a module or saves (SPEC 5.8).
"""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .. import db
from ..model import ToolSpec
from . import gate
from .builder import format_sections
from .provenance import unbacked
from .registry import list_modules

RUN_MODULE_SCHEMA = {"type": "object", "properties": {
    "module": {"type": "string"}, "inputs": {"type": "object"},
    "assumptions": {"type": "array", "items": {"type": "string"}}, "expected": {"type": "string"}},
    "required": ["module", "inputs", "assumptions", "expected"]}
SAVE_INPUT_SCHEMA = {"type": "object", "properties": {
    "name": {"type": "string"}, "value": {"type": "string"}, "note": {"type": "string"}},
    "required": ["name", "value", "note"]}

RUN_MODULE = ToolSpec(
    name="run_module",
    description=("Run a registered module through the gate. Give the module name, every input the spec lists, "
                 "your assumptions (a list of sentences, may be empty) and what you expect the result to be."),
    input_schema=RUN_MODULE_SCHEMA)
SAVE_INPUT = ToolSpec(
    name="save_input",
    description=("Save a figure the person gave you, so it is not asked for again. Give a snake_case name, "
                 "the value in plain form and a note on where it came from."),
    input_schema=SAVE_INPUT_SCHEMA)
TOOLS = (RUN_MODULE, SAVE_INPUT)

MAX_CALLS = 10
OPENING = "What would you like to work out?"
NUMBERS_CORRECTION = ("[harness] Your reply was not shown. These numbers did not come from a module result in "
                      "this conversation, a saved input, the brief or the person's own words: {numbers}. "
                      "Do not work numbers out yourself: run a module, or leave the number out. Then reply again.")
WITHHELD = ("(The answer was held back, because it contained numbers that no tested module produced: "
            "{numbers}.)")
WITHHELD_NOTE = ("[harness] Your last reply was not shown to the person, because it contained numbers that "
                 "no module produced: {numbers}.")
INPUTS_UNBACKED = ("These numbers did not come from the person, the brief, a saved input or a module result: "
                   "{numbers}. Ask the person, or run the module that produces them.")
EMPTY_REPLY = "[harness] Your reply was empty. Ask the person for what you need, or give your answer."
TOO_MANY = "(The harness stopped working on this, because it took too many steps. Try asking in a simpler way.)"
BAD_NAME = "The name must be in snake_case, such as monthly_income."
EMPTY_VALUE = "The value is empty."
SAVED = "Saved."

NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def run_agent(*, model, conn, brief, ask, say=print, session_id, question="", today=None) -> None:
    """Answer the person's questions until they type /quit.

    `ask(text)` shows text to the person and returns what they typed.
    `say(text)` shows text that needs no answer.
    """
    today = today or date.today()
    today_text = today.isoformat()
    system = _system_prompt(conn, brief, today_text)
    typed = []          # every message the person typed in this session, as typed
    messages = []

    def record(kind, actor, payload):
        db.record_event(conn, session_id=session_id, kind=kind, actor=actor, payload=payload)

    def sources() -> list:
        """What a number may come from, read afresh at each check (SPEC 5.9)."""
        found = [brief, today_text, *typed]
        found += [json.loads(row["value"]) for row in conn.execute("SELECT value FROM inputs")]
        for row in conn.execute("SELECT inputs, output FROM calc_runs WHERE session_id = ?", (session_id,)):
            found += [json.loads(row["inputs"]), json.loads(row["output"])]
        return found

    def run_module(call) -> dict:
        arguments = call.arguments
        numbers = unbacked(json.dumps(arguments.get("inputs")), sources())
        if numbers:
            record("ask.correction", "harness", {"reason": "run_module", "numbers": numbers,
                                                 "text": json.dumps(arguments)})
            return _result(call, INPUTS_UNBACKED.format(numbers=", ".join(numbers)), True)
        say(f"  (running {arguments.get('module')})")
        try:
            result = gate.call(conn, arguments.get("module"), arguments.get("inputs"),
                               assumptions=arguments.get("assumptions"), expected=arguments.get("expected"),
                               session_id=session_id)
        except gate.Refused as refused:
            return _result(call, str(refused), True)
        return _result(call, json.dumps({"module": result["module"], "run_id": result["run_id"],
                                         "output": result["output"]}), False)

    def save_input(call) -> dict:
        arguments = call.arguments
        name, value, note = arguments.get("name"), arguments.get("value"), arguments.get("note", "")
        if not isinstance(name, str) or not NAME.match(name):
            return _result(call, BAD_NAME, True)
        if not str(value if value is not None else "").strip():
            return _result(call, EMPTY_VALUE, True)
        numbers = unbacked(value, sources())
        if numbers:
            record("ask.correction", "harness", {"reason": "save_input", "numbers": numbers,
                                                 "text": json.dumps(arguments)})
            return _result(call, INPUTS_UNBACKED.format(numbers=", ".join(numbers)), True)
        conn.execute(
            "INSERT INTO inputs (name, value, note, ts, session_id) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET value = excluded.value, note = excluded.note,"
            " ts = excluded.ts, session_id = excluded.session_id",
            (name, json.dumps(value), note, datetime.now(timezone.utc).isoformat(), session_id))
        conn.commit()
        record("ask.input_saved", "agent", {"name": name, "value": value, "note": note})
        return _result(call, SAVED, False)

    def turn() -> tuple[str, str]:
        """Work on the last person message. Returns what to show the person, and a note for their next message."""
        calls, corrected = 0, False
        while True:
            if calls == MAX_CALLS:
                record("ask.stopped", "harness", {"reason": "too many steps"})
                return TOO_MANY, ""
            say("  (thinking)")
            response = model.complete(system=system, messages=messages, tools=TOOLS)
            calls += 1

            if response.tool_calls:         # its text is not shown
                results = []
                for call in response.tool_calls:
                    if call.name == "run_module":
                        results.append(run_module(call))
                    elif call.name == "save_input":
                        results.append(save_input(call))
                    else:
                        results.append(_result(call, f"There is no tool called {call.name} here.", True))
                messages.append({"role": "assistant", "content": response.text, "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in response.tool_calls]})
                messages.extend(results)
                continue

            text = response.text.strip()
            if not text:
                messages.append({"role": "user", "content": EMPTY_REPLY})
                continue
            numbers = unbacked(text, sources())
            if numbers and not corrected:
                corrected = True
                record("ask.correction", "harness", {"reason": "reply", "numbers": numbers, "text": text})
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": NUMBERS_CORRECTION.format(numbers=", ".join(numbers))})
                continue
            messages.append({"role": "assistant", "content": text})
            if numbers:
                record("ask.withheld", "harness", {"numbers": numbers, "text": text})
                joined = ", ".join(numbers)
                return WITHHELD.format(numbers=joined), "\n\n" + WITHHELD_NOTE.format(numbers=joined)
            record("ask.reply", "agent", {"text": text})
            return text, ""

    def hear(shown: str):
        """Wait for the person. Returns what they typed, or None for /quit."""
        while True:
            answer = ask(shown).strip()
            if answer == "/quit":
                return None
            if answer:
                return answer

    text = question or ask(OPENING).strip()
    if text in ("", "/quit"):
        return
    note = ""
    while True:
        typed.append(text)
        record("ask.message", "person", {"text": text})
        messages.append({"role": "user", "content": text + note})
        shown, note = turn()
        text = hear(shown)
        if text is None:
            return


def _result(call, content: str, is_error: bool) -> dict:
    result = {"role": "tool", "tool_call_id": call.id, "content": content}
    if is_error:
        result["is_error"] = True
    return result


def _system_prompt(conn, brief: dict, today_text: str) -> str:
    """The text of analyst.md with the context filled in. Made once, when the session starts."""
    modules = {module["name"]: {"steps": module["steps"], "spec": module["spec"]}
               for module in list_modules(conn)}
    saved = {row["name"]: {"value": json.loads(row["value"]), "note": row["note"]}
             for row in conn.execute("SELECT * FROM inputs ORDER BY name")}
    context = format_sections({"today": today_text, "goal": brief["goal"], "particulars": brief["particulars"],
                               "process": brief["process"], "modules": modules, "saved inputs": saved})
    return Path(__file__).with_name("analyst.md").read_text(encoding="utf-8").replace("{context}", context)
