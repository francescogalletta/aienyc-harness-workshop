"""Decisions: the record of what the person decided, and the blocks they are shown (SPEC 8.1 to 8.3).

Version 1's record; package A4a replaces it with harness/needs_you/calls.py. Two kinds are left: a
judgment put through `ask_decision`, and a build request.
`record_decision` writes the row and the `ask.decision` event together, so
the evidence reads decisions from the events.
"""
import json
import re
import sqlite3
from datetime import datetime, timezone

from .. import db
from .added import step_label
ACCEPT_WORDS = {"/accept", "yes", "y", "yes.", "ok", "okay", "si", "sí"}     # version 1; A4a replaces this file

KINDS = ("judgment", "build")
SOMETHING_ELSE = "something else"

DECISION_INTRO = "Only you can decide this:"
DECISION_INTRO_STEP = "Only you can decide this. It is step {step} of the plan: {name}."
DECISION_SUGGESTS = "The assistant suggests {n}: {why}"
DECISION_QUESTION = ("Type the number of your choice, or say in your own words what you want instead. "
                     "Type /aside to talk it through on the side first.")
DECISION_QUESTION_SUGGESTED = ("Type the number of your choice, or yes to take the suggestion, or say in your own "
                               "words what you want instead. Type /aside to talk it through on the side first.")

NUMBERED = re.compile(r"(?:option\s+)?([1-9])[.)]?", re.IGNORECASE)


def _decision(row) -> dict:
    return {"id": row["id"], "ts": row["ts"], "session_id": row["session_id"], "kind": row["kind"],
            "step": row["step_id"], "question": row["question"], "options": json.loads(row["options"]),
            "choice": row["choice"], "words": row["words"], "runs": json.loads(row["runs"])}


def record_decision(conn: sqlite3.Connection, *, session_id: str, kind: str, step_id, question: str,
                    options: list, choice: str, words: str, runs: list) -> dict:
    """Write one decision and its `ask.decision` event (SPEC 8.1). Checks only the kind."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    cursor = conn.execute(
        "INSERT INTO decisions (ts, session_id, kind, step_id, question, options, choice, words, runs)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), session_id, kind, step_id, question, json.dumps(options),
         choice, words, json.dumps(runs)))
    conn.commit()
    decision = _decision(conn.execute("SELECT * FROM decisions WHERE id = ?", (cursor.lastrowid,)).fetchone())
    db.record_event(conn, session_id=session_id, kind="ask.decision", actor="person",
                    payload={key: value for key, value in decision.items() if key not in ("ts", "session_id")})
    return decision


def list_decisions(conn: sqlite3.Connection, *, session_id=None) -> list[dict]:
    """The decisions of one session, or of every session, oldest first (SPEC 8.1)."""
    return [_decision(row) for row in conn.execute(
        "SELECT * FROM decisions WHERE (:session_id IS NULL OR session_id = :session_id) ORDER BY id",
        {"session_id": session_id})]


def choice_words(decision: dict) -> str:
    """The choice in words: yes or no, `something else`, or `2. Move the date` (SPEC 8.1)."""
    choice = decision["choice"]
    if decision["kind"] == "judgment" and choice != SOMETHING_ELSE:
        return f"{choice}. {decision['options'][int(choice) - 1]}"
    return choice


def one_line(text: str) -> str:
    """Trimmed, with every run of white space made one space (SPEC 8.1)."""
    return " ".join(text.split())


def decision_block(*, question: str, options: list[str], recommendation: int | None, why: str,
                   step: dict | None) -> str:
    """What the person sees at a judgment call (SPEC 8.3)."""
    if step is None:
        lines = [DECISION_INTRO]
    else:
        lines = [DECISION_INTRO_STEP.format(step=step_label(step["id"]), name=one_line(step["name"]))]
    lines.append(f"  {one_line(question)}")
    lines += [f"    {n}. {one_line(option)}" for n, option in enumerate(options, start=1)]
    if recommendation is not None:
        lines.append("  " + DECISION_SUGGESTS.format(n=recommendation, why=one_line(why)))
    return "\n".join(lines)


def read_choice(answer: str, options: list[str], recommendation: int | None) -> str:
    """Read the person's answer to a judgment call: an option's number, or `something else` (SPEC 8.3)."""
    said = one_line(answer)
    found = NUMBERED.fullmatch(said)
    if found and int(found.group(1)) <= len(options):
        return found.group(1)
    for number, option in enumerate(options, start=1):
        if said.casefold() == one_line(option).casefold():
            return str(number)
    if recommendation is not None and said.lower() in ACCEPT_WORDS:
        return str(recommendation)
    return SOMETHING_ELSE
