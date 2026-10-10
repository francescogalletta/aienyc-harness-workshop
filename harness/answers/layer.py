"""Layer 3, answers with evidence (SPEC 5): the analyst on the main lane, its tools, the figures of each
answer, the last run of each step, saved inputs on the plan's inputs, the `ask` command and replay
expectations. It registers no action: the person speaks through `say`.

Which run belongs to which answer is kept on the message that ended the turn, in its private `_runs`.
"""
import json
from pathlib import Path

from ..calc.provenance import _produced, _read, unbacked
from ..calc.registry import module_for_step
from ..core import Session
from ..core.state import display, display_inputs
from ..grounding.layer import phase_of
from ..layers import Command, Expect, Layer
from .agent import answer, saved_inputs, tools

NO_PLAN = "There is no agreed plan yet. Agree one first with: python -m harness ground"
INTRO = "Ask about your plan, in your own words. Type /quit to stop."


# --- The state document ---

RECENT_RUNS = 5         # the runs of a step the state document gives, newest first


def _answers(conn, conversation: str):
    """The main chat's assistant and harness messages, oldest first, with their private data."""
    for row in conn.execute("SELECT id, data FROM messages WHERE conversation = ? AND thread IS NULL"
                            " AND who IN ('assistant', 'harness') ORDER BY id", (conversation,)):
        yield f"m{row['id']}", json.loads(row["data"])


def _cited(data: dict) -> tuple[set[str], set[int]]:
    """The steps a message's figures lead to, and the runs they name."""
    steps, runs = set(), set()
    for figure in data.get("figures") or []:
        if figure.get("step"):
            steps.add(figure["step"])
            if isinstance(figure.get("run"), str) and figure["run"][1:].isdigit():
                runs.add(int(figure["run"][1:]))
    return steps, runs


def latest_answer(conn, conversation: str) -> tuple[str | None, set[int], set[str]]:
    """The last answer: the latest message that ended an analyst turn in which modules ran, or that has a figure
    leading to a step (a reply that only asks or explains leaves the last answer as it was). Returns its id, the
    runs it used (made in its turn, or named by its figures) and the steps its figures lead to."""
    found, runs, steps = None, set(), set()
    for message, data in _answers(conn, conversation):
        cited_steps, cited_runs = _cited(data)
        if data.get("_runs") or cited_steps:
            found, runs, steps = message, set(data.get("_runs") or []) | cited_runs, cited_steps
    return found, runs, steps


def reply_of_runs(conn, conversation: str) -> dict[int, str]:
    """{run id: the message that ended the turn the run was made in}."""
    found = {}
    for message, data in _answers(conn, conversation):
        for run in data.get("_runs", []):
            found[run] = message
    return found


def run_entry(row, replies: dict) -> dict:
    """A run as the state document gives it, with how the pop-up shows its values (`shown`)."""
    inputs, output = json.loads(row["inputs"]), json.loads(row["output"])
    return {"run": f"r{row['id']}", "message": replies.get(row["id"]), "inputs": inputs, "output": output,
            "assumptions": json.loads(row["assumptions"]), "ts": row["ts"], "test_run": row["test_run_id"],
            "shown": {"inputs": display_inputs(inputs), "output": display(output)}}


def recent_runs(conn, conversation: str, module: str | None, limit: int = RECENT_RUNS) -> list:
    if not module:
        return []
    return conn.execute("SELECT * FROM calc_runs WHERE session_id = ? AND module = ? ORDER BY id DESC LIMIT ?",
                        (conversation, module, limit)).fetchall()


def last_run(conn, conversation: str, module: str | None, replies: dict, in_answer: set, lit: bool = False) -> dict | None:
    """The run a step shows: while the step is in the last answer, the latest of its runs that answer used;
    else its latest run. `in_last_answer` is whether the step is in the last answer."""
    rows = recent_runs(conn, conversation, module, limit=10_000 if lit else 1)
    if not rows:
        return None
    row = next((each for each in rows if each["id"] in in_answer), rows[0]) if lit else rows[0]
    return {**run_entry(row, replies), "in_last_answer": lit}


def contribute(view, state: dict) -> None:
    """`last_run` and `runs` on every step, edges and inputs of added steps from the runs that fed them, and
    `used` and `value` on every input (SPEC 5.2)."""
    conn = view.conn
    accepted = state["phase"] == "accepted"
    _, in_answer, cited = latest_answer(conn, view.conversation) if accepted else (None, set(), set())
    replies = reply_of_runs(conn, view.conversation) if accepted else {}
    modules_run = {row["module"] for row in conn.execute(
        f"SELECT module FROM calc_runs WHERE id IN ({','.join('?' * len(in_answer))})", tuple(in_answer))} \
        if in_answer else set()
    for step in state["steps"]:
        calculation = accepted and step.get("kind") == "calculation"
        module = module_for_step(conn, step["id"]) if calculation else None
        lit = calculation and (step["id"] in cited or (module is not None and module in modules_run))
        step["last_run"] = last_run(conn, view.conversation, module, replies, in_answer, lit) if calculation else None
        step["runs"] = [run_entry(row, replies) for row in recent_runs(conn, view.conversation, module)]
    if accepted:
        connect_added(conn, view.conversation, state)
    lit = {step["id"] for step in state["steps"] if (step["last_run"] or {}).get("in_last_answer")}
    saved = saved_inputs(conn)
    for input_id, entry in state["inputs"].items():
        found = saved.get(input_id[len("in:"):])
        value = found["value"] if found else None
        entry["value"] = value if value is None or isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        entry["used"] = any(step in lit for step in entry.get("steps", []))


def connect_added(conn, conversation: str, state: dict) -> None:
    """An added step's needs, pills and edges, from what fed its latest run: an input named as a plan input, or
    whose value a saved input holds, is a pill; an input whose value an earlier run of another step produced is
    an edge from that step. A step with no such run stays unconnected."""
    steps = {step["id"]: step for step in state["steps"]}
    saved = {f"in:{name}": each["value"] for name, each in saved_inputs(conn).items()}
    rows = conn.execute("SELECT id, module, inputs, output FROM calc_runs WHERE session_id = ? ORDER BY id DESC",
                        (conversation,)).fetchall()
    for step in state["steps"]:
        if step.get("in_plan", True) or step.get("kind") != "calculation":
            continue
        module = module_for_step(conn, step["id"])
        run = next((row for row in rows if row["module"] == module), None)
        if run is None:
            continue
        needs = []
        for key, value in json.loads(run["inputs"]).items():
            pill = f"in:{key}" if f"in:{key}" in state["inputs"] else next(
                (input_id for input_id, held in saved.items() if input_id in state["inputs"]
                 and not isinstance(value, (list, dict)) and str(held) == str(value)), None)
            if pill:
                needs.append(pill)
                continue
            wanted = _read(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
            numbers = {item["value"] for item in wanted if not item["parts"] and not item["exempt"]}
            dates = {item["written"] for item in wanted if item["parts"]}
            for row in rows:
                if row["id"] >= run["id"] or row["module"] == module:
                    continue
                made, made_dates = _produced(json.loads(row["output"]), json.loads(row["inputs"]))
                if numbers & set(made) or dates & made_dates:
                    source = _step_of(conn, row["module"], steps)
                    if source and source != step["id"]:
                        needs.append(source)
                    break
        for need in dict.fromkeys(needs):
            if need in step["needs"]:
                continue
            step["needs"].append(need)
            if need.startswith("in:"):
                step["inputs"].append(need)
                state["inputs"][need].setdefault("steps", []).append(step["id"])
            elif {"from": need, "to": step["id"]} not in state["edges"]:
                state["edges"].append({"from": need, "to": step["id"]})


def _step_of(conn, module: str, steps: dict) -> str | None:
    from ..calc.registry import get_module
    registered = get_module(conn, module)
    found = (registered or {}).get("spec", {}).get("step_id")
    return found if found in steps else None


# --- Routing ---

def left_to_helper(core, step_id: str) -> bool:
    """Whether the step helper of layer 2 takes a message about this step (SPEC 4.7). Without a helper, never."""
    try:
        from ..calc import helper
    except ImportError:
        return False
    return bool(helper.wants(core, step_id))


def route(core, message: dict):
    """After the plan is accepted, every message but those the step helper takes is one analyst turn."""
    if phase_of(core) != "accepted":
        return None
    if message.get("step") and left_to_helper(core, message["step"]):
        return None
    return answer


answer.what = "answer"


# --- The `ask` command ---

def run_ask(session, question: str = "", *, read=input, write=print) -> int:
    """Ask about the agreed plan in the terminal until /quit or the end of input. 1 when there is no plan."""
    from ..terminal import Terminal

    if session.state()["phase"] != "accepted":
        write(NO_PLAN)
        return 1
    if question.strip():
        session.act("say", {"text": question.strip()})
    else:
        write(INTRO)
    Terminal(session, read=read, write=write).run()
    return 0


def ask(args) -> int:
    from ..config import load_config

    session = Session(load_config())
    try:
        return run_ask(session, " ".join(args.question))
    finally:
        session.close()


def _ask_arguments(parser) -> None:
    parser.add_argument("question", nargs="*", help="what to ask first; otherwise you are asked")


# --- Replay expectations (SPEC 5.3). `check(value, context)`: the context is the finished Session. ---

def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _one_number(text) -> bool:
    found = _read(text) if isinstance(text, str) else []
    return len(found) == 1 and not found[0]["parts"] and not found[0]["exempt"] and found[0]["written"] == text.strip()


def _validate_runs(value):
    if not isinstance(value, list):
        return "runs must be a list"
    for n, entry in enumerate(value, start=1):
        good = (isinstance(entry, dict) and set(entry) <= {"module", "inputs"} and isinstance(entry.get("module"), str)
                and entry["module"] and isinstance(entry.get("inputs", {}), dict))
        if not good:
            return f"runs: entry {n} must be an object with a module and, optionally, inputs"
    return None


def _validate_numbers(value):
    if not isinstance(value, list) or not all(_one_number(each) for each in value):
        return ("must be a list of numbers written as text, each one number the number check reads "
                "(not a date, not a bare whole number from 0 to 12)")
    return None


def _validate_count(value):
    return None if _whole(value) else "must be a whole number, 0 or more"


def _events(context, kind: str) -> list[dict]:
    from .. import db
    return [json.loads(row["payload"]) for row in db.list_events(context.conn, session_id=context.conversation, kind=kind)]


def _has(inputs: dict, wanted: dict) -> bool:
    return all(key in inputs and str(inputs[key]) == str(value) for key, value in wanted.items())


def _check_runs(value, context) -> dict:
    rows = context.conn.execute("SELECT module, inputs FROM calc_runs WHERE session_id = ? ORDER BY id",
                                (context.conversation,)).fetchall()
    missing = [entry for entry in value
               if not any(row["module"] == entry["module"] and _has(json.loads(row["inputs"]), entry.get("inputs", {}))
                          for row in rows)]
    return {"what": "ran " + "; ".join(f"{entry['module']} {json.dumps(entry.get('inputs', {}))}" for entry in value),
            "passed": not missing,
            "seen": "; ".join(f"{row['module']} {row['inputs']}" for row in rows) or "no runs"}


def _check_shown(wanted: bool):
    def check(value, context) -> dict:
        replies = [message["text"] for message in context.state()["chat"]
                   if message["who"] == "assistant" and message["kind"] in ("text", "decision")]
        found = [item for item in value if any(not unbacked(item, [text]) for text in replies)]
        shown = [item for item in value if item in found]
        passed = len(found) == len(value) if wanted else not found
        return {"what": ("shows " if wanted else "does not show ") + ", ".join(value), "passed": passed,
                "seen": f"{', '.join(shown) or 'none'} of {len(replies)} replies"}
    return check


def _check_count(kind: str, noun: str):
    def check(value, context) -> dict:
        count = len(_events(context, kind))
        return {"what": f"at most {value} {noun}", "passed": count <= value, "seen": f"{count} {noun}"}
    return check


EXPECTS = {
    "runs": Expect(_validate_runs, _check_runs),
    "shown": Expect(_validate_numbers, _check_shown(True)),
    "not_shown": Expect(_validate_numbers, _check_shown(False)),
    "max_withheld": Expect(_validate_count, _check_count("ask.withheld", "replies withheld")),
    "max_corrections": Expect(_validate_count, _check_count("ask.correction", "corrections")),
}

LAYER = Layer(
    number=3, name="answers", schema=Path(__file__).with_name("schema.sql"),
    contribute=contribute, route=route, tools=tools, prompt=Path(__file__).with_name("analyst.md"),
    commands={"ask": Command(help="ask about your plan, in the terminal", run=ask, arguments=_ask_arguments)},
    expects=EXPECTS,
)
