"""The agent that answers questions about the plan (SPEC 5.9, 8.2 to 8.6, 9.7).

It runs modules through the gate and saves what the person tells it. It
is given the notes kept during a build, and when no module can do what is
needed it asks for one to be built, and the person decides. It never works a
number out itself: the harness checks every number it sends out, and every
number it passes to a module or saves (SPEC 5.8). The person decides what a
run takes as given, and the calls only they can make; at any question they
can step aside (SPEC 8). With `verify`, the person's figures are checked
first, and a figure that disagrees with a reference is put to the person
before it is calculated with (SPEC 9).
"""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .. import db
from ..model import ToolSpec
from . import gate
from .added import add_step, list_added_steps, process_steps, step_label
from .builder import ACCEPT_WORDS, NO_STEP, build_step, format_sections
from .decisions import (GATE_QUESTION, SOMETHING_ELSE, DECISION_QUESTION, DECISION_QUESTION_SUGGESTED,
                        assumption_set, decision_block, gate_block, list_decisions, one_line, read_choice,
                        record_decision)
from .findings import close_finding, list_findings, open_finding, open_findings, same_value
from .gate import NOT_REGISTERED
from .notes import add_note, list_notes
from .provenance import unbacked
from .registry import file_status, get_module, input_problems, list_modules, step_map
from .verifier import needs_check
from .verifier import verify as check_message

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
    "runs": {"type": "array", "items": {"type": "integer"}},
    "finding": {"type": "integer"}},
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
                 "results it rests on. The person answers, and you get their choice or their own words. To put "
                 "an open finding to the person, give only finding (its number) and runs as []: the harness "
                 "shows its own block."),
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
REQUEST_QUESTION = ("Build it now? Type yes to start. As with python -m harness build, you will check a plan "
                    "and a few made-up examples. Anything else leaves it, and we carry on without it. During "
                    "the build, /quit stops only the build.")
TOO_MANY_REQUESTS = ("No more builds can be asked for until the person's next message. Tell the person plainly "
                     "what cannot be answered yet.")
BAD_CASE = "case must be step, new or replace."
MISSING_WORDS = "Say in plain words: {fields}."
NOT_A_STEP = "There is no calculation step '{target}' in the process."
ALREADY_BUILT = ("Step '{target}' already has the module '{module}', with unchanged files. Run it, or ask to "
                 "replace it if it does not fit.")
GATE_UNBACKED = ("The person would see your assumptions and what you expect before the run, and these numbers in "
                 "it did not come from the person, the brief, a saved input or a module result: {numbers}. Say it "
                 "without them, or ask the person, and call run_module again.")
ASK_FIRST = ("This run takes things as given that the person has not accepted, and it could not be shown to them "
             "with the rest of your reply. Call run_module again.")
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
FINDING_NOTE = ("[harness] The harness checked the person's figures and opened finding {id}. Raise it now: call "
                "ask_decision with finding {id} and runs [], and nothing else. The person will see this block, "
                "word for word:\n{block}\nUntil they decide, run_module and save_input are refused and your "
                "replies are held back.")
FINDING_OPEN = ("Refused while finding {id} is open. Call ask_decision with finding {id} and runs [] first: the "
                "person decides which figure to use.")
FINDING_FIRST = ("[harness] Your reply was not shown, because finding {id} is open. Call ask_decision with "
                 "finding {id} and runs [] now.")
FINDING_RAISED = ("Not saved: '{name}' already holds a different value. The harness opened finding {id}. Call "
                  "ask_decision with finding {id} and runs [] next: the person decides which value to keep.")
FINDING_DECIDED = ("Not saved: the person already decided about this value of '{name}' (finding {id}). Carry on "
                   "with what they chose.")
FINDING_NOT_OPEN = "There is no open finding {finding} in this conversation."

NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def says_yes(answer: str) -> bool:
    """Is this a yes to a build request? Lenient, here only: the first word may carry `.,!;:` (SPEC 6.6)."""
    if answer.lower() in ACCEPT_WORDS:
        return True
    words = answer.split()
    return bool(words) and words[0].lower().rstrip(".,!;:") in ACCEPT_WORDS


def run_agent(*, model, conn, brief, ask, say=print, session_id, question="", today=None, desk=None,
              verify=False) -> None:
    """Answer the person's questions until they type /quit.

    `ask(text)` shows text to the person and returns what they typed.
    `say(text)` shows text that needs no answer.
    `desk` is the research desk a side conversation looks terms up with (SPEC 8.5).
    `verify` turns on the verifier, the findings and their refusals (SPEC 9.7).
    """
    from .aside import ASIDE_CARRIED, Asides       # aside.py imports this module's texts, so it is imported here

    today = today or date.today()
    today_text = today.isoformat()
    db.record_event(conn, session_id=session_id, kind="ask.started", actor="harness",
                    payload={"today": today_text})         # the date is a source for the number check (SPEC 7.2)
    system = _system_prompt(conn, brief, today_text)
    asides = Asides(model=model, conn=conn, brief=brief, ask=ask, say=say, session_id=session_id,
                    today=today_text, desk=desk)
    ask, say = asides.ask, asides.say           # from here every question has /aside (SPEC 8.5)
    typed = []          # every message the person typed in this session, as typed
    accepted = []       # the assumption sets the person said yes to (SPEC 8.2)
    requests = {"shown": 0}     # requests shown for the last person message
    decisions = {"shown": 0}    # decisions shown for the last person message
    messages = []

    def record(kind, actor, payload):
        db.record_event(conn, session_id=session_id, kind=kind, actor=actor, payload=payload)

    def sources() -> list:
        """What a number may come from, read afresh at each check (SPEC 5.9)."""
        found = [brief, today_text, *typed, *(each["words"] for each in list_decisions(conn, session_id=session_id)),
                 *asides.carried]
        found += [json.loads(row["value"]) for row in conn.execute("SELECT value FROM inputs")]
        found += [note["text"] for note in list_notes(conn)]       # the person's words, or a request they approved
        for row in conn.execute("SELECT inputs, output FROM calc_runs WHERE session_id = ?", (session_id,)):
            found += [json.loads(row["inputs"]), json.loads(row["output"])]
        for row in conn.execute("SELECT output FROM data_summaries WHERE session_id = ?", (session_id,)):
            found.append(json.loads(row["output"]))         # summaries of the person's own files (SPEC 9.4)
        return found

    def oldest_open():
        """The oldest finding of this session that is still open, or None. Only with `verify` (SPEC 9.7)."""
        found = open_findings(conn, session_id=session_id) if verify else []
        return found[0] if found else None

    def refused_while_open(call, found) -> dict:
        record("finding.refused", "harness", {"finding": found["id"], "tool": call.name,
                                              "arguments": call.arguments})
        return _result(call, FINDING_OPEN.format(id=found["id"]), True)

    def needs_yes(call) -> bool:
        """Does this run take things as given that the person has not accepted, and could it otherwise run? (SPEC 8.2)"""
        arguments = call.arguments
        inputs, name = arguments.get("inputs"), arguments.get("module")
        assumptions, expected = arguments.get("assumptions"), arguments.get("expected")
        if oldest_open() is not None:
            return False
        if unbacked(json.dumps(inputs), sources()):
            return False
        module = get_module(conn, name) if isinstance(name, str) else None
        if module is None or file_status(conn, name) != "unchanged":
            return False
        if (not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions)
                or not isinstance(expected, str) or not expected.strip()):
            return False
        if input_problems(module["spec"], inputs):
            return False
        wanted = assumption_set(assumptions)
        return bool(wanted) and wanted not in accepted

    def assumption_gate(calls) -> tuple[set, dict]:
        """Show the person the held runs of a reply and ask once (SPEC 8.2).

        Returns the indexes of the held calls, and the results the gate gave some of them.
        """
        held = [(k, call) for k, call in enumerate(calls) if call.name == "run_module" and needs_yes(call)]
        if not held:
            return set(), {}
        block = gate_block([(get_module(conn, call.arguments["module"])["spec"]["description"],
                             call.arguments["assumptions"], call.arguments["expected"]) for _k, call in held])
        numbers = unbacked(block, sources())
        if numbers:
            record("ask.correction", "harness", {"reason": "assumptions", "numbers": numbers,
                                                 "text": json.dumps([call.arguments for _k, call in held])})
            return {k for k, _call in held}, {
                k: _result(call, GATE_UNBACKED.format(numbers=", ".join(numbers)), True) for k, call in held}
        record("ask.gate", "agent", {"calls": [call.arguments for _k, call in held], "block": block})
        say(block)
        while True:
            answer = ask(GATE_QUESTION).strip()
            if answer:
                break
        yes = answer.lower() in ACCEPT_WORDS            # strict: the leniency of SPEC 6.6 does not apply
        record_decision(conn, session_id=session_id, kind="assumptions", step_id=None, question=block,
                        options=[], choice="yes" if yes else "no", words=answer, runs=[])
        if yes:
            accepted.extend(assumption_set(call.arguments["assumptions"]) for _k, call in held)
            return {k for k, _call in held}, {}
        return {k for k, _call in held}, {
            k: _result(call, json.dumps({"outcome": "not_run", "said": answer}), False) for k, call in held}

    def run_module(call, held=False) -> dict:
        arguments = call.arguments
        found = oldest_open()
        if found is not None:
            return refused_while_open(call, found)
        numbers = unbacked(json.dumps(arguments.get("inputs")), sources())
        if numbers:
            record("ask.correction", "harness", {"reason": "run_module", "numbers": numbers,
                                                 "text": json.dumps(arguments)})
            return _result(call, INPUTS_UNBACKED.format(numbers=", ".join(numbers)), True)
        if not held and needs_yes(call):
            return _result(call, ASK_FIRST, True)
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

    def over_saved_value(call, name, value, note) -> dict | None:
        """Refuse to save over a different saved value, and open a finding instead (SPEC 9.7). None: save it."""
        row = conn.execute("SELECT * FROM inputs WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        stored = json.loads(row["value"])
        stored = stored if isinstance(stored, str) else json.dumps(stored)
        new = value if isinstance(value, str) else json.dumps(value)
        if same_value(stored, new):
            return None
        decided = [each for each in list_findings(conn, session_id=session_id) if each["status"] == "decided"]
        if any(each["chosen"] is not None and same_value(new, each["chosen"]) for each in decided):
            return None             # the person chose this figure
        before = next((each for each in decided if each["kind"] == "earlier" and each["input"] == name
                       and same_value(each["claim"], new)), None)
        if before is not None:
            return _result(call, FINDING_DECIDED.format(name=name, id=before["id"]), True)
        raised = open_finding(conn, session_id=session_id, kind="earlier", claim=new, claim_figure=new,
                              reference=stored, reference_figure=stored, input_name=name,
                              earlier={"value": stored, "note": row["note"], "ts": row["ts"],
                                       "session_id": row["session_id"]}, pending_note=note)
        return _result(call, FINDING_RAISED.format(name=name, id=raised["id"]), True)

    def save_input(call) -> dict:
        arguments = call.arguments
        found = oldest_open()
        if found is not None:
            return refused_while_open(call, found)
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
        if verify:
            refusal = over_saved_value(call, name, value, note)
            if refusal is not None:
                return refusal
        store_input(name, value, note)
        return _result(call, SAVED, False)

    def request_module(call) -> dict:
        """Ask the person to build one step, and build it (SPEC 5.9). Returns the tool result."""
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
        while True:
            answer = ask(REQUEST_QUESTION).strip()
            if answer:
                break
        decision = "accepted" if says_yes(answer) else "declined"
        record("ask.module_decision", "person", {"decision": decision, "text": answer})

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

    def put_finding(call, first) -> dict:
        """Put an open finding to the person, and close it with what they choose (SPEC 9.7)."""
        arguments = call.arguments

        def refuse(error: str) -> dict:
            record("ask.decision_refused", "harness", {"error": error, "arguments": arguments})
            return _result(call, error, True)

        if not first:
            return refuse(ONE_DECISION)
        wanted = arguments["finding"]
        found = next((each for each in open_findings(conn, session_id=session_id)
                      if isinstance(wanted, int) and not isinstance(wanted, bool) and each["id"] == wanted), None)
        if found is None:
            return refuse(FINDING_NOT_OPEN.format(finding=json.dumps(wanted)))
        record("ask.decision_asked", "agent", {"arguments": arguments, "block": found["block"]})
        say(found["block"])
        while True:
            answer = ask(DECISION_QUESTION).strip()
            if answer:
                break
        choice = read_choice(answer, found["options"], None)
        decision = record_decision(conn, session_id=session_id, kind="finding", step_id=None,
                                   question=found["block"], options=found["options"], choice=choice, words=answer,
                                   runs=[])
        saved = found["kind"] == "earlier" and choice == "1"
        if saved:
            store_input(found["input"], found["claim"], found["pending_note"] or "")
        closed = close_finding(conn, found["id"], decision_id=decision["id"], choice=choice, saved=saved,
                               session_id=session_id)
        return _result(call, json.dumps({
            "outcome": "decided", "decision": decision["id"], "finding": found["id"], "choice": choice,
            "option": None if choice == SOMETHING_ELSE else decision["options"][int(choice) - 1],
            "use": closed["chosen"], "said": answer, "saved": saved}), False)

    def ask_decision(call, reply) -> dict:
        """Put a call only the person can make to them, and record what they say (SPEC 8.3)."""
        arguments = call.arguments

        def refuse(error: str) -> dict:
            record("ask.decision_refused", "harness", {"error": error, "arguments": arguments})
            return _result(call, error, True)

        first = not reply["decision"]
        reply["decision"] = True
        if verify and arguments.get("finding") is not None:
            return put_finding(call, first)
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
            for carried in asides.take_carried():       # words the person passed back from a side conversation
                messages.append({"role": "user", "content": ASIDE_CARRIED.format(text=carried)})
            response = model.complete(system=system, messages=messages, tools=TOOLS)
            calls += 1

            if response.tool_calls:         # its text is not shown
                results, reply = [], {"decision": False}
                held, gated = assumption_gate(response.tool_calls)      # before any call is handled (SPEC 8.2)
                for k, call in enumerate(response.tool_calls):
                    if k in gated:
                        results.append(gated[k])
                    elif call.name == "run_module":
                        results.append(run_module(call, held=k in held))
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
            found = oldest_open()
            if found is not None:           # held back, and the number check does not read it (SPEC 9.7)
                record("ask.correction", "harness", {"reason": "finding", "numbers": [], "text": text})
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": FINDING_FIRST.format(id=found["id"])})
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
        if verify:
            if needs_check(conn, brief, text):
                check_message(model=model, conn=conn, brief=brief, message=text, session_id=session_id,
                              today=today_text, say=say)
            for found in open_findings(conn, session_id=session_id):
                messages.append({"role": "user", "content": FINDING_NOTE.format(id=found["id"],
                                                                                 block=found["block"])})
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
