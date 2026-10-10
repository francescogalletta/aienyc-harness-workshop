"""Layer 5, review (SPEC 7): the reviewer on the review lane (`reviewer.py`), its challenges as threads in the chat
and as counts on steps, "use this" and "dismiss", and the passes that start by themselves.

Nothing here waits for the person or holds the main lane: a pass is a review-lane job, a challenge never blocks,
and "use this" is the person's own message in the main chat, handled as any message is.
"""
import json
from pathlib import Path

from ..calc.builder import plan_of
from ..core import BadAction, NotNow, list_threads, number_of, set_thread_status
from ..grounding.layer import phase_of
from ..layers import Expect, Layer
from ..needs_you import marks
from . import reviewer

PROMPT = Path(__file__).with_name("analyst.md")
USE_THIS = "Use the reviewer's suggestion on step {number} {name}: {proposal}"
NO_CHALLENGE = "There is no challenge {challenge}."
NOT_OPEN = "That challenge has already been {status}."
A_QUESTION = "A question is answered in its thread, not used."
ANSWER_FIRST = "Answer the question that is waiting first."
NO_STEP = "The step that challenge is about is no longer in the plan."


# --- Which passes start by themselves (SPEC 7.1) ---

def automatic(config) -> bool:
    return config.review != "off"


def loaded(core) -> None:
    """A plan that is already accepted when the session opens (a seeded example, a restart) is reviewed once."""
    if not automatic(core.config) or phase_of(core) != "accepted":
        return
    if core.conn.execute("SELECT 1 FROM review_passes WHERE conversation = ?", (core.conversation,)).fetchone():
        return
    reviewer.queue_pass(core, "loaded")


def plan_accepted(work) -> None:
    if automatic(work.config):
        reviewer.queue_pass(work, "accepted")


def plan_changed(work, changed) -> None:
    if automatic(work.config):
        reviewer.queue_pass(work, "plan_changed")


def turn_finished(work, turn) -> None:
    """A turn whose runs stored an assumption no pass has seen starts a pass. Layer 4's hook ran first; the runs'
    assumptions are stored here too, in case it had nothing to say."""
    if not automatic(work.config) or not turn.runs:
        return
    for run_id in turn.runs:
        row = work.conn.execute("SELECT assumptions FROM calc_runs WHERE id = ?", (run_id,)).fetchone()
        if row is not None:
            marks.of_run(work.conn, run_id, json.loads(row["assumptions"]))
    if reviewer.new_assumptions(work.conn, turn.runs):
        reviewer.queue_pass(work, "assumptions")


# --- The state document ---

def view_of(row) -> dict:
    return {"id": f"c{row['id']}", "step": row["step_id"], "kind": row["kind"], "concern": row["concern"],
            "proposal": row["proposal"], "change": row["change"], "impact": row["impact"], "rank": row["rank"],
            "sources": json.loads(row["sources"]), "status": row["status"], "pass": row["pass"]}


def contribute(view, state: dict) -> None:
    """`challenges` on every step (the open ones), `challenge` on every thread, review threads in `threads`, and
    `review`. Threads another layer already drew are kept; the reviewer's are added if they are not there."""
    rows = reviewer.challenge_rows(view.conn, view.conversation)
    by_thread = {row["thread_id"]: row for row in rows}
    for step in state["steps"]:
        step["challenges"] = [f"c{row['id']}" for row in sorted(rows, key=lambda each: (each["rank"], each["id"]))
                              if row["step_id"] == step["id"] and row["status"] == "open"]
    threads = state.setdefault("threads", [])
    drawn = {thread["id"] for thread in threads}
    threads.extend(thread for thread in list_threads(view.conn, view.conversation)
                   if thread["kind"] == "review" and thread["id"] not in drawn)
    for thread in threads:
        row = by_thread.get(thread["id"])
        thread["challenge"] = view_of(row) if row is not None else thread.get("challenge")
        for message in thread["messages"]:
            message.setdefault("sources", [])
    threads.sort(key=lambda thread: number_of(thread["id"], "t"))
    state["review"] = {"open": sum(len(step["challenges"]) for step in state["steps"]),
                       "running": view.session.lane("review") != "idle"}


# --- Use this, dismiss ---

def find_open(core, payload: dict):
    name = payload.get("challenge")
    if not isinstance(name, str):
        raise BadAction("challenge must be a challenge id")
    try:
        number = number_of(name, "c")
    except ValueError:
        raise BadAction("challenge must be a challenge id") from None
    row = core.conn.execute("SELECT * FROM challenges WHERE id = ? AND conversation = ?",
                            (number, core.conversation)).fetchone()
    if row is None:
        raise NotNow(NO_CHALLENGE.format(challenge=name))
    if row["status"] != "open":
        raise NotNow(NOT_OPEN.format(status=row["status"]))
    return row


def settle_challenge(core, row, status: str) -> None:
    core.conn.execute("UPDATE challenges SET status = ? WHERE id = ?", (status, row["id"]))
    core.conn.commit()
    set_thread_status(core.conn, row["thread_id"], status)
    core.record(f"review.{'used' if status == 'used' else 'dismissed'}",
                {"challenge": f"c{row['id']}", "pass": row["pass"], "step": row["step_id"],
                 "kind": row["kind"], "change": row["change"]}, "person")
    core.changed()


def use_challenge(core, payload: dict) -> None:
    """The challenge and its thread become used; the person's "use this" goes to the main chat with the step
    attached and is handled like any message of theirs (the analyst, or the step helper for a step that is not
    built). Nothing is changed in the person's name except through that visible message."""
    row = find_open(core, payload)
    if row["kind"] == "question":
        raise NotNow(A_QUESTION)
    if core.waiting is not None:
        raise NotNow(ANSWER_FIRST)              # the message would answer what the main lane waits for
    brief = plan_of(core.config)
    found = reviewer.step_number(core.conn, brief, row["step_id"]) if brief else None
    if found is None:
        raise NotNow(NO_STEP)
    settle_challenge(core, row, "used")
    text = USE_THIS.format(number=found[0], name=found[1], proposal=row["proposal"])
    core._say({"text": text, "step": row["step_id"]})


def dismiss_challenge(core, payload: dict) -> None:
    settle_challenge(core, find_open(core, payload), "dismissed")


# --- Replay expectation (SPEC 7.4) ---

def _validate_challenges(value):
    good = (isinstance(value, dict) and value and set(value) <= {"min", "max", "steps"}
            and all(isinstance(value[key], int) and not isinstance(value[key], bool) and value[key] >= 0
                    for key in ("min", "max") if key in value)
            and (not value.get("steps") or (isinstance(value["steps"], list)
                                            and all(isinstance(each, str) for each in value["steps"]))))
    return None if good else "challenges must be {min?, max?, steps?}: counts of 0 or more, steps a list of ids"


def _check_challenges(value, context) -> dict:
    """Challenges raised in the conversation, whatever became of them; `steps` each need at least one."""
    rows = reviewer.challenge_rows(context.conn, context.conversation)
    steps = {row["step_id"] for row in rows}
    missing = [each for each in value.get("steps", []) if each not in steps]
    count = len(rows)
    return {"what": f"challenges between {value.get('min', 0)} and {value.get('max', 'any')}"
                    + (f" on {', '.join(value['steps'])}" if value.get("steps") else ""),
            "passed": value.get("min", 0) <= count <= value.get("max", count) and not missing,
            "seen": f"{count} challenges on {', '.join(sorted(steps)) or 'no step'}"}


LAYER = Layer(
    number=5, name="review", schema=Path(__file__).with_name("schema.sql"),
    contribute=contribute, prompt=PROMPT,
    actions={"use_challenge": use_challenge, "dismiss_challenge": dismiss_challenge},
    hooks={"loaded": loaded, "plan_accepted": plan_accepted, "plan_changed": plan_changed,
           "turn_finished": turn_finished},
    expects={"challenges": Expect(_validate_challenges, _check_challenges)},
)
