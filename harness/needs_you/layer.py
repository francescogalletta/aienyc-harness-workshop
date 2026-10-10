"""Layer 4, when the harness needs the person (SPEC 6): run and mark (`marks.py`), calls that are the person's
(`calls.py`), missing calculations built without asking (`requests.py`), side threads (`side.py`).
"""
import json
from pathlib import Path

from ..core import BadAction, list_threads
from ..layers import Expect, Layer
from . import calls, marks, requests, side

PROMPT = Path(__file__).with_name("analyst.md")
SECTION_LIMIT = 40


# --- The state document ---

def contribute(view, state: dict) -> None:
    """`unconfirmed` and `calls` on every step, `notice` and `decision` on every message, the single
    "needs you" on the step of an open decision, and `threads` (the conversation's side threads, and the
    review threads layer 5 started, which are in the same table)."""
    conn = view.conn
    rows = calls.rows_of(conn, view.conversation)
    named = {row["step_id"] for row in rows}
    open_row = next((row for row in rows if row["status"] == "open"), None)
    for step in state["steps"]:
        loose = []
        run = step.get("last_run")
        if run:
            loose = [{"id": each["id"], "text": each["text"]}
                     for each in marks.unconfirmed_of_run(conn, int(run["run"][1:]), run["assumptions"])]
        step["unconfirmed"] = loose
        mine = [row for row in rows if row["step_id"] == step["id"]]
        if step["kind"] == "your_call" or step["id"] in named:
            asking = next((row for row in mine if row["status"] == "open"), None)
            step["calls"] = {"open": f"d{asking['id']}" if asking else None,
                             "records": [calls.record_view(row) for row in mine if row["status"] == "answered"]}
        else:
            step["calls"] = None
        if open_row is not None and step["id"] == open_row["step_id"]:
            step["needs_you"] = True
    near = {}
    for row in conn.execute("SELECT payload FROM events WHERE kind = 'you.module_requested' ORDER BY id"):
        payload = json.loads(row["payload"])
        if payload.get("near"):
            near[payload.get("step")] = payload["near"]
    ids = {step["id"] for step in state["steps"]}
    for step in state["steps"]:
        if not step.get("in_plan", True):
            step["near"] = near.get(step["id"]) if near.get(step["id"]) in ids else None
    by_id = {f"d{row['id']}": row for row in rows}
    for message in state["chat"]:
        decision = message.get("decision")
        if decision and decision["id"] in by_id:
            message["decision"] = calls.row_view(by_id[decision["id"]])
        message.setdefault("decision", None)
        notice = message.setdefault("notice", None)
        if notice:
            message["notice"] = {**notice, "status": marks.notice_status(conn, notice)}
    state["threads"] = [{**thread, "challenge": None,
                         "messages": [{"sources": [], **message} for message in thread["messages"]]}
                        for thread in list_threads(conn, view.conversation)]


# --- What the analyst is told ---

def context(conn) -> dict:
    """The sections `assumptions` and `decisions` of `## What you know` (SPEC 6.1, 6.2)."""
    row = conn.execute("SELECT value FROM meta WHERE key = 'conversation'").fetchone()
    conversation = row["value"] if row else ""
    assumed = conn.execute(
        "SELECT DISTINCT a.* FROM assumptions a JOIN run_assumptions r ON r.assumption_id = a.id"
        " JOIN calc_runs c ON c.id = r.run_id WHERE c.session_id = ? ORDER BY a.id DESC LIMIT ?",
        (conversation, SECTION_LIMIT)).fetchall()
    found = {}
    if assumed:
        found["assumptions"] = [{"assumption": each["text"], "status": each["status"],
                                 **({"their words": each["words"]} if each["words"] else {})}
                                for each in reversed(assumed)]
    decided = [row for row in calls.rows_of(conn, conversation) if row["status"] == "answered"][-SECTION_LIMIT:]
    found["decisions"] = [{"step": each["step_id"], "question": each["question"],
                           "options": json.loads(each["options"]), "choice": each["choice"],
                           "words": each["words"]} for each in decided]
    return found


# --- Actions ---

def confirm_assumptions(core, payload: dict) -> None:
    message = payload.get("message")
    if not isinstance(message, str) or not message:
        raise BadAction("message must be a message id")
    marks.confirm(core, message)


def _validate_side_threads(value):
    return None if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else \
        "side_threads must be a whole number, 0 or more"


def _check_side_threads(value, context) -> dict:
    threads = [thread for thread in context.state()["threads"] if thread["kind"] == "side"
               and any(message["who"] == "assistant" for message in thread["messages"])]
    return {"what": f"at least {value} side threads answered", "passed": len(threads) >= value,
            "seen": f"{len(threads)} answered"}


def tools(turn) -> list:
    return [*calls.tools(turn), *requests.tools(turn)]


def loaded(core) -> None:
    calls.drop_unanswered(core.conn)


# --- Replay expectations (SPEC 6.5) ---

def _validate_decisions(value):
    good = isinstance(value, list) and all(
        isinstance(each, dict) and set(each) <= {"step", "choice", "count"} and isinstance(each.get("step"), str)
        and isinstance(each.get("choice", ""), str)
        and (isinstance(each.get("count", 1), int) and not isinstance(each.get("count", 1), bool)
             and each.get("count", 1) >= 1)
        for each in value)
    return None if good else "decisions must be a list of {step, choice?, count?}"


def _check_decisions(value, context) -> dict:
    rows = [row for row in calls.rows_of(context.conn, context.conversation) if row["status"] == "answered"]
    missing = []
    for each in value:
        found = [row for row in rows if row["step_id"] == each["step"]
                 and ("choice" not in each or row["choice"] == each["choice"])]
        if len(found) < each.get("count", 1):
            missing.append(each)
    return {"what": "decided " + "; ".join(f"{each['step']} {each.get('choice', '')}".strip() for each in value),
            "passed": not missing,
            "seen": "; ".join(f"{row['step_id']} {row['choice']}" for row in rows) or "no decisions"}


def _validate_marks(value):
    good = (isinstance(value, dict) and value and set(value) <= {"min", "max", "confirmed", "corrected"}
            and all(isinstance(each, int) and not isinstance(each, bool) and each >= 0 for each in value.values()))
    return None if good else ("marks must be {min?, max?, confirmed?, corrected?}: whole numbers, 0 or more "
                              "(min and max count open notices at the end; confirmed and corrected, at least "
                              "that many such actions in the conversation)")


def _check_marks(value, context) -> dict:
    from .. import db
    state = context.state()
    open_notices = sum(1 for message in state["chat"] if (message.get("notice") or {}).get("status") == "open")
    done = {key: len(db.list_events(context.conn, session_id=context.conversation,
                                    kind=f"you.assumptions_{key}")) for key in ("confirmed", "corrected")}
    passed = (value.get("min", 0) <= open_notices <= value.get("max", open_notices)
              and all(done[key] >= value.get(key, 0) for key in done))
    wanted = [f"open notices between {value.get('min', 0)} and {value.get('max', 'any')}"]
    wanted += [f"at least {value[key]} {key}" for key in done if key in value]
    return {"what": ", ".join(wanted), "passed": passed,
            "seen": f"{open_notices} open notices, {done['confirmed']} confirmed, {done['corrected']} corrected"}


def _validate_added(value):
    return None if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else \
        "added must be a whole number, 0 or more"


def _check_added(value, context) -> dict:
    from .. import db
    events = [json.loads(row["payload"]) for row in db.list_events(context.conn, session_id=context.conversation,
                                                                   kind="you.module_requested")]
    made = [each for each in events if each["case"] == "new" and each["outcome"] != "not_built"]
    return {"what": f"at least {value} calculations added and built", "passed": len(made) >= value,
            "seen": f"{len(made)} added"}


LAYER = Layer(
    number=4, name="needs you", schema=Path(__file__).with_name("schema.sql"),
    contribute=contribute,
    actions={"choose": calls.choose, "confirm_assumptions": confirm_assumptions, "side": side.side},
    route=marks.route, tools=tools, prompt=PROMPT, context=context,
    hooks={"loaded": loaded, "turn_finished": marks.turn_finished},
    expects={"decisions": Expect(_validate_decisions, _check_decisions),
             "marks": Expect(_validate_marks, _check_marks),
             "added": Expect(_validate_added, _check_added),
             "side_threads": Expect(_validate_side_threads, _check_side_threads)},
)
