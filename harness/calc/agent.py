"""Version 1's agent that answers questions about the plan. Not wired to the core: packages A3
(harness/answers/) and A4a (harness/needs_you/) replace it, keeping its checks, and then delete it.
The assumption gate, the build-request question, the findings and side conversations are removed.

It runs modules through the gate and saves what the person tells it. It
is given the notes kept during a build, and when no module can do what is
needed it asks for one to be built, and the person decides. It never works a
number out itself: the harness checks every number it sends out, and every
number it passes to a module or saves (SPEC 5.8). The person makes the
calls only they can make.
"""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .. import db
from ..model import ToolSpec
from . import gate
from .added import add_step, list_added_steps, process_steps, step_label
from .builder import NO_STEP, build_step, format_sections
from .decisions import (SOMETHING_ELSE, DECISION_QUESTION, DECISION_QUESTION_SUGGESTED, decision_block,
                        list_decisions, one_line, read_choice, record_decision)
from .gate import NOT_REGISTERED
from .notes import add_note, list_notes
from .provenance import unbacked
from .registry import file_status, get_module, list_modules, step_map

RUN_MODULE_SCHEMA = {"type": "object", "properties": {
    "module": {"type": "string"}, "inputs": {"type": "object"},
    "assumptions": {"type": "array", "items": {"type": "string"}}, "expected": {"type": "string"}},
    "required": ["module", "inputs", "assumptions", "expected"]}
SAVE_INPUT_SCHEMA = {"type": "object", "properties": {
    "name": {"type": "string"}, "value": {"type": "string"}, "note": {"type": "string"}},
    "required": ["name", "value", "note"]}
REQUEST_MODULE_SCHEMA = {"type": "object", "properties": {
    "case": {"type": "string", "enum": ["step", "new", "replace"]},
    "target": {"type": "string"},
    "works_out": {"type": "string"}, "from_what": {"type": "string"}, "gives": {"type": "string"},
    "formula": {"type": "string"}, "why": {"type": "string"}},
    "required": ["case", "works_out", "from_what", "gives", "formula", "why"]}

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
ASK_DECISION_SCHEMA = {"type": "object", "properties": {
    "step": {"type": "string"},
    "question": {"type": "string"},
    "options": {"type": "array", "items": {"type": "string"}},
    "recommendation": {"type": "integer"},
    "why": {"type": "string"},
    "runs": {"type": "array", "items": {"type": "integer"}}},
    "required": ["runs"]}

REQUEST_MODULE = ToolSpec(
    name="request_module",
    description=("Ask for one module to be built, when no module can do what is needed. case is step (a "
                 "calculation step of the process has no working module; target is its id), new (the process "
                 "has no step for it; leave target empty) or replace (a module does not fit what the person "
                 "has; target is its name). Say in plain words what must be worked out, from what, giving "
                 "what, how, and why it is needed now. The person decides. You do not write or see code."),
    input_schema=REQUEST_MODULE_SCHEMA)
ASK_DECISION = ToolSpec(
    name="ask_decision",
    description=("Put a call only the person can make to them: a step of kind judgment, or a choice between "
                 "ways forward that depends on what they want. Give the step it belongs to (when there is one), "
                 "the question, two to four options in plain words, the option you would choose "
                 "(recommendation, a number from 1, optional) with one sentence why, and the run_ids of the "
                 "results it rests on. The person answers, and you get their choice or their own words."),
    input_schema=ASK_DECISION_SCHEMA)
TOOLS = (RUN_MODULE, SAVE_INPUT, REQUEST_MODULE, ASK_DECISION)

MAX_CALLS = 10
MAX_REQUESTS = 2
MAX_DECISIONS = 2
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
REQUEST_STEP = "The assistant asks to build a module for step {step}: {name}."
REQUEST_NEW = "The assistant asks to build a calculation that is not in the brief."
REQUEST_REPLACE = "The assistant asks to rebuild the module {module}, so that it takes what you have."
TOO_MANY_REQUESTS = ("No more builds can be asked for until the person's next message. Tell the person plainly "
                     "what cannot be answered yet.")
BAD_CASE = "case must be step, new or replace."
MISSING_WORDS = "Say in plain words: {fields}."
NOT_A_STEP = "There is no calculation step '{target}' in the process."
ALREADY_BUILT = ("Step '{target}' already has the module '{module}', with unchanged files. Run it, or ask to "
                 "replace it if it does not fit.")
ONE_DECISION = "Only one ask_decision is handled per reply. Wait for the answer to the first."
TOO_MANY_DECISIONS = ("No more decisions can be put to the person until their next message. Tell the person "
                      "plainly what is still to decide.")
DECISION_NO_QUESTION = "Say the question in plain words."
DECISION_OPTIONS = "Give two to four different options, each in plain words."
DECISION_NO_STEP = "There is no step {step} in the process."
DECISION_BAD_RECOMMENDATION = "recommendation must be the number of one of the options, or left out."
DECISION_NO_WHY = "Say in one sentence why you recommend it."
DECISION_RUNS = "runs must be a list of run ids. It may be empty."
DECISION_UNKNOWN_RUNS = "These runs are not in this conversation: {runs}."

NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def run_agent(*, model, conn, brief, ask, say=print, session_id, question="", today=None) -> None:
    """Answer the person's questions until they type /quit.

    `ask(text)` shows text to the person and returns what they typed.
    `say(text)` shows text that needs no answer.
    """
    today = today or date.today()
    today_text = today.isoformat()
    db.record_event(conn, session_id=session_id, kind="ask.started", actor="harness",
                    payload={"today": today_text})         # the date is a source for the number check (SPEC 7.2)
    system = _system_prompt(conn, brief, today_text)
    typed = []          # every message the person typed in this session, as typed
    requests = {"shown": 0}     # requests shown for the last person message
    decisions = {"shown": 0}    # decisions shown for the last person message
    messages = []

    def record(kind, actor, payload):
        db.record_event(conn, session_id=session_id, kind=kind, actor=actor, payload=payload)

    def sources() -> list:
        """What a number may come from, read afresh at each check (SPEC 5.9)."""
        found = [brief, today_text, *typed, *(each["words"] for each in list_decisions(conn, session_id=session_id))]
        found += [json.loads(row["value"]) for row in conn.execute("SELECT value FROM inputs")]
        found += [note["text"] for note in list_notes(conn)]       # the person's words, or a request they approved
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

    def store_input(name, value, note) -> None:
        """Insert or replace a saved input, and record it (SPEC 5.9)."""
        conn.execute(
            "INSERT INTO inputs (name, value, note, ts, session_id) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(name) DO UPDATE SET value = excluded.value, note = excluded.note,"
            " ts = excluded.ts, session_id = excluded.session_id",
            (name, json.dumps(value), note, datetime.now(timezone.utc).isoformat(), session_id))
        conn.commit()
        record("ask.input_saved", "agent", {"name": name, "value": value, "note": note})

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
        store_input(name, value, note)
        return _result(call, SAVED, False)

    def request_module(call) -> dict:
        """Build one step without asking (SPEC 6.3 keeps these checks). Returns the tool result."""
        arguments = call.arguments

        def refuse(error: str) -> dict:
            record("ask.request_refused", "harness", {"error": error, "arguments": arguments})
            return _result(call, error, True)

        case, target = arguments.get("case"), arguments.get("target")
        target = target if isinstance(target, str) else ""
        if requests["shown"] >= MAX_REQUESTS:
            return refuse(TOO_MANY_REQUESTS)
        if case not in ("step", "new", "replace"):
            return refuse(BAD_CASE)
        fields = ("works_out", "from_what", "gives", "formula", "why")
        missing = [key for key in fields if not isinstance(arguments.get(key), str) or not arguments[key].strip()]
        if missing:
            return refuse(MISSING_WORDS.format(fields=", ".join(missing)))
        works_out, from_what, gives, formula, why = (arguments[key].strip() for key in fields)
        steps = {step["id"]: step for step in process_steps(conn, brief)}
        if case == "step":
            if target not in steps or steps[target].get("kind") != "calculation":
                return refuse(NOT_A_STEP.format(target=target))
            mapped = step_map(conn).get(target)
            if mapped is not None and file_status(conn, mapped) == "unchanged":
                return refuse(ALREADY_BUILT.format(target=target, module=mapped))
            first = REQUEST_STEP.format(step=step_label(target), name=steps[target]["name"])
        elif case == "replace":
            registered = get_module(conn, target)
            if registered is None:
                return refuse(NOT_REGISTERED.format(name=target))
            if registered["spec"]["step_id"] not in steps:
                return refuse(NO_STEP.format(step=registered["spec"]["step_id"], name=target))
            first = REQUEST_REPLACE.format(module=target)
        else:
            first = REQUEST_NEW
        block = "\n".join([first, f"  To work out: {works_out}", f"  From: {from_what}", f"  Giving: {gives}",
                           f"  How: {formula}", f"  Why now: {why}"])
        numbers = unbacked(block, sources())
        if numbers:
            record("ask.correction", "harness", {"reason": "request_module", "numbers": numbers,
                                                 "text": json.dumps(arguments)})
            return _result(call, INPUTS_UNBACKED.format(numbers=", ".join(numbers)), True)

        record("ask.module_requested", "agent", {"arguments": arguments, "request": block})
        requests["shown"] += 1                      # counts whatever the answer
        say(block)
        answer, decision = "", "accepted"

        step_id = target if case == "step" else registered["spec"]["step_id"] if case == "replace" else None
        if decision == "declined":
            result = {"outcome": "declined", "said": answer}
        else:
            rebuild = None
            if case == "new":
                step = add_step(conn, name=works_out, formula=formula, needs=from_what, produces=gives,
                                reason=why, session_id=session_id)
            elif case == "replace":
                step = steps[registered["spec"]["step_id"]]
                add_note(conn, step_id=step["id"], text=block, session_id=session_id)
                rebuild = target
            else:
                step = steps[target]
            step_id = step["id"]
            built = build_step(model=model, conn=conn, brief=brief, step=step, ask=ask, say=say,
                               session_id=session_id, rebuild=rebuild)
            if built["outcome"] == "not_built":
                result = {"outcome": "not_built", "step": built["step"], "reason": built["reason"]}
            else:
                result = {"outcome": built["outcome"], "step": built["step"], "module": built["module"],
                          "spec": get_module(conn, built["module"])["spec"]}
        record("ask.module_outcome", "harness", result)
        record_decision(conn, session_id=session_id, kind="build", step_id=step_id, question=block, options=[],
                        choice="yes" if decision == "accepted" else "no", words=answer, runs=[])
        return _result(call, json.dumps(result), False)

    def ask_decision(call, reply) -> dict:
        """Put a call only the person can make to them, and record what they say (SPEC 8.3)."""
        arguments = call.arguments

        def refuse(error: str) -> dict:
            record("ask.decision_refused", "harness", {"error": error, "arguments": arguments})
            return _result(call, error, True)

        first = not reply["decision"]
        reply["decision"] = True
        if not first:
            return refuse(ONE_DECISION)
        if decisions["shown"] >= MAX_DECISIONS:
            return refuse(TOO_MANY_DECISIONS)
        question, options = arguments.get("question"), arguments.get("options")
        if not isinstance(question, str) or not question.strip():
            return refuse(DECISION_NO_QUESTION)
        if (not isinstance(options, list) or not 2 <= len(options) <= 4
                or not all(isinstance(option, str) and option.strip() for option in options)
                or len({one_line(option).casefold() for option in options}) != len(options)):
            return refuse(DECISION_OPTIONS)
        step_id = arguments.get("step")
        steps = {step["id"]: step for step in process_steps(conn, brief)}
        if step_id is None or step_id == "":
            step = None
        elif isinstance(step_id, str) and step_id in steps:
            step = steps[step_id]
        else:
            return refuse(DECISION_NO_STEP.format(
                step=f"'{step_id}'" if isinstance(step_id, str) else json.dumps(step_id)))
        recommendation, why = arguments.get("recommendation"), arguments.get("why")
        if recommendation is not None and (not isinstance(recommendation, int) or isinstance(recommendation, bool)
                                           or not 1 <= recommendation <= len(options)):
            return refuse(DECISION_BAD_RECOMMENDATION)
        if recommendation is not None and (not isinstance(why, str) or not why.strip()):
            return refuse(DECISION_NO_WHY)
        runs = arguments.get("runs")
        if not isinstance(runs, list) or not all(isinstance(run, int) and not isinstance(run, bool) for run in runs):
            return refuse(DECISION_RUNS)
        known = {row["id"] for row in conn.execute("SELECT id FROM calc_runs WHERE session_id = ?", (session_id,))}
        unknown = list(dict.fromkeys(run for run in runs if run not in known))
        if unknown:
            return refuse(DECISION_UNKNOWN_RUNS.format(runs=", ".join(str(run) for run in unknown)))
        block = decision_block(question=question, options=options, recommendation=recommendation,
                               why=why if recommendation is not None else "", step=step)
        numbers = unbacked(block, sources())
        if numbers:
            record("ask.correction", "harness", {"reason": "ask_decision", "numbers": numbers,
                                                 "text": json.dumps(arguments)})
            return _result(call, INPUTS_UNBACKED.format(numbers=", ".join(numbers)), True)

        record("ask.decision_asked", "agent", {"arguments": arguments, "block": block})
        decisions["shown"] += 1                     # counts whatever the answer
        say(block)
        shown = DECISION_QUESTION_SUGGESTED if recommendation is not None else DECISION_QUESTION
        while True:
            answer = ask(shown).strip()
            if answer:
                break
        choice = read_choice(answer, options, recommendation)
        decision = record_decision(conn, session_id=session_id, kind="judgment",
                                   step_id=step["id"] if step else None, question=block,
                                   options=[one_line(option) for option in options], choice=choice,
                                   words=answer, runs=runs)
        decided = {each["step"] for each in list_decisions(conn, session_id=session_id)
                   if each["kind"] == "judgment"}
        result = {"outcome": "decided", "decision": decision["id"], "choice": choice,
                  "option": None if choice == SOMETHING_ELSE else decision["options"][int(choice) - 1],
                  "said": answer,
                  "judgment_steps": [{"id": each["id"], "name": each["name"], "decided": each["id"] in decided}
                                     for each in process_steps(conn, brief) if each.get("kind") == "judgment"]}
        return _result(call, json.dumps(result), False)

    def turn() -> tuple[str, str]:
        """Work on the last person message. Returns what to show the person, and a note for their next message."""
        calls, corrected = 0, False
        requests["shown"] = 0
        decisions["shown"] = 0
        while True:
            if calls == MAX_CALLS:
                record("ask.stopped", "harness", {"reason": "too many steps"})
                return TOO_MANY, ""
            say("  (thinking)")
            response = model.complete(system=system, messages=messages, tools=TOOLS)
            calls += 1

            if response.tool_calls:         # its text is not shown
                results, reply = [], {"decision": False}
                for call in response.tool_calls:
                    if call.name == "run_module":
                        results.append(run_module(call))
                    elif call.name == "save_input":
                        results.append(save_input(call))
                    elif call.name == "request_module":
                        results.append(request_module(call))
                    elif call.name == "ask_decision":
                        results.append(ask_decision(call, reply))
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
    """The text of analyst.md with the context filled in. Made once, when the session starts and not remade."""
    modules = {module["name"]: {"steps": module["steps"], "spec": module["spec"]}
               for module in list_modules(conn)}
    saved = {row["name"]: {"value": json.loads(row["value"]), "note": row["note"]}
             for row in conn.execute("SELECT * FROM inputs ORDER BY name")}
    context = format_sections({"today": today_text, "goal": brief["goal"], "particulars": brief["particulars"],
                               "process": brief["process"],
                               "added steps (not in the brief)": list_added_steps(conn),
                               "modules": modules, "saved inputs": saved, "notes": list_notes(conn)})
    return Path(__file__).with_name("analyst.md").read_text(encoding="utf-8").replace("{context}", context)
