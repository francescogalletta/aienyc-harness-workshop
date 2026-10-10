"""Run and mark (SPEC 6.1): what a run took as given is stored, shown under the answer and on the step,
and the person confirms it with one action or corrects it in their own words.

"Unconfirmed" means exactly: an assumption of a run whose status is not `confirmed`. A step shows it for its
last run (a `corrected` assumption used again counts), so a mark goes away only by confirming, or by a run
that no longer rests on it.
"""
import json

from .. import db
from ..answers.agent import Turn, step_of_module
from ..calc.added import process_steps
from ..calc.builder import plan_of
from ..core import NotNow, get_message, number_of

UNCONFIRMED, CONFIRMED, CORRECTED = "unconfirmed", "confirmed", "corrected"
CORRECTED_LINE = ("[harness] The person says this is not right: {assumptions}. Their words follow. "
                  "Run again the steps that rested on it.")
NOTHING_TO_CONFIRM = "Nothing under that answer is waiting to be confirmed."


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def key_of(text: str) -> str:
    return one_line(text).casefold()


def _assumption(row) -> dict:
    return {"id": f"a{row['id']}", "text": row["text"], "status": row["status"], "words": row["words"]}


def link_run(conn, run_id: int, sentences) -> list[dict]:
    """Store each sentence a run assumed (a new key is `unconfirmed`) and link it to the run. Idempotent.
    Returns the run's assumptions, in the order they were given."""
    found, seen = [], set()
    for sentence in sentences or []:
        text = one_line(sentence)
        if not text or key_of(text) in seen:
            continue
        seen.add(key_of(text))
        row = conn.execute("SELECT * FROM assumptions WHERE key = ?", (key_of(text),)).fetchone()
        if row is None:
            conn.execute("INSERT INTO assumptions (key, text, status, words, ts) VALUES (?, ?, ?, '', ?)",
                         (key_of(text), text, UNCONFIRMED, db.now()))
            row = conn.execute("SELECT * FROM assumptions WHERE key = ?", (key_of(text),)).fetchone()
        if conn.execute("SELECT 1 FROM run_assumptions WHERE run_id = ? AND assumption_id = ?",
                        (run_id, row["id"])).fetchone() is None:
            conn.execute("INSERT INTO run_assumptions (run_id, assumption_id) VALUES (?, ?)", (run_id, row["id"]))
        found.append(_assumption(row))
    conn.commit()
    return found


def of_run(conn, run_id: int, sentences) -> list[dict]:
    """The assumptions of a run with their status now. Stores them first if they are not stored yet."""
    wanted = {key_of(each) for each in sentences or [] if one_line(each)}
    known = conn.execute(
        "SELECT a.* FROM run_assumptions r JOIN assumptions a ON a.id = r.assumption_id WHERE r.run_id = ?"
        " ORDER BY a.id", (run_id,)).fetchall()
    if {row["key"] for row in known} != wanted:
        return link_run(conn, run_id, sentences)
    order = {key_of(each): n for n, each in enumerate(sentences or [])}
    return [_assumption(row) for row in sorted(known, key=lambda row: order.get(row["key"], 0))]


def unconfirmed_of_run(conn, run_id: int, sentences) -> list[dict]:
    return [each for each in of_run(conn, run_id, sentences) if each["status"] != CONFIRMED]


def get(conn, assumption_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM assumptions WHERE id = ?", (number_of(assumption_id, "a"),)).fetchone()
    return _assumption(row) if row else None


def set_status(conn, ids: list[str], status: str, words: str = "") -> None:
    for each in ids:
        conn.execute("UPDATE assumptions SET status = ?, words = ?, ts = ? WHERE id = ?",
                     (status, words, db.now(), number_of(each, "a")))
    conn.commit()


# --- The notice under an answer ---

def notice_status(conn, notice: dict) -> str:
    """A notice's status now: open, but with every assumption since confirmed (maybe under another answer),
    reads as confirmed."""
    if notice["status"] != "open":
        return notice["status"]
    rows = [get(conn, each["id"]) for each in notice["assumptions"]]
    return "open" if any(row and row["status"] != CONFIRMED for row in rows) else "confirmed"


def make_notice(turn: Turn) -> dict | None:
    """The notice of a finished turn: the unconfirmed assumptions of its runs and the steps of those runs."""
    conn = turn.conn
    brief = plan_of(turn.work.config)
    step_ids = {step["id"] for step in process_steps(conn, brief)} if brief else set()
    assumptions, steps = {}, []
    for run_id in turn.runs:
        row = conn.execute("SELECT module, assumptions FROM calc_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            continue
        loose = unconfirmed_of_run(conn, run_id, json.loads(row["assumptions"]))
        if not loose:
            continue
        for each in loose:
            assumptions.setdefault(each["id"], {"id": each["id"], "text": each["text"]})
        step = step_of_module(conn, row["module"], step_ids)
        if step and step not in steps:
            steps.append(step)
    if not assumptions:
        return None
    return {"assumptions": list(assumptions.values()), "steps": steps, "status": "open"}


def turn_finished(work, turn: Turn) -> None:
    """Hook: a turn that ran modules on unconfirmed assumptions gets a notice on its final message."""
    if not turn.runs or not turn.reply:
        return
    notice = make_notice(turn)
    if notice is not None:
        work.session.update_message(turn.reply, {"notice": notice})


# --- The person's two answers ---

def confirm(core, message_id: str) -> None:
    """The `confirm_assumptions` action (NotNow is raised by the caller's checks)."""
    message = get_message(core.conn, message_id)
    notice = (message or {}).get("notice")
    if not notice or notice_status(core.conn, notice) != "open":
        raise NotNow(NOTHING_TO_CONFIRM)
    ids = [each["id"] for each in notice["assumptions"]]
    set_status(core.conn, ids, CONFIRMED)
    core.update_message(message_id, {"notice": {**notice, "status": "confirmed"}})
    core.record("you.assumptions_confirmed", {"message": message_id, "assumptions": ids}, "person")


def correct(work, message_id: str, words: str) -> list[str]:
    """The person says in their own words that a notice's assumptions are not right. Those of the notice not
    yet confirmed become `corrected` (all of them when none is open any more: they changed their mind).
    Returns the corrected assumptions' texts."""
    notice = get_message(work.conn, message_id)["notice"]
    rows = [get(work.conn, each["id"]) for each in notice["assumptions"]]
    targets = [row for row in rows if row and row["status"] != CONFIRMED] or [row for row in rows if row]
    ids = [row["id"] for row in targets]
    set_status(work.conn, ids, CORRECTED, words)
    work.session.update_message(message_id, {"notice": {**notice, "status": "changed"}})
    work.record("you.assumptions_corrected", {"message": message_id, "assumptions": ids, "words": words}, "person")
    return [row["text"] for row in targets]


def correction_text(texts: list[str], words: str) -> str:
    return CORRECTED_LINE.format(assumptions=" ".join(texts)) + "\n\n" + words


def route(core, message: dict):
    """A message with a notice reference is the person's "Change it": the analyst turn that corrects it."""
    from ..answers.agent import answer
    from ..grounding.layer import phase_of

    notice_message = message.get("notice")
    if not notice_message or phase_of(core) != "accepted":
        return None
    found = get_message(core.conn, notice_message)
    if not found or not found.get("notice"):
        return None

    def handler(work, message: dict) -> None:
        texts = correct(work, notice_message, message["text"])
        answer(work, {**message, "text": correction_text(texts, message["text"])})

    handler.what = "answer"
    return handler
