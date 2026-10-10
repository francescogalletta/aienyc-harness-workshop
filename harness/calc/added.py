"""Added steps (SPEC 5.5): calculations the person needed that the brief has no step for."""
import re
import sqlite3
from datetime import datetime, timezone

from .. import db

ADDED_PREFIX = "added_"
NOT_IN_BRIEF = "(not in the brief)"
ADDED_ID = re.compile(r"^added_([1-9][0-9]*)$")


def _step(row) -> dict:
    return {"id": f"{ADDED_PREFIX}{row['id']}", "name": row["name"], "kind": "calculation",
            "method": "arithmetic", "formula": row["formula"], "needs": [row["needs"]],
            "produces": row["produces"], "reason": row["reason"]}


def add_step(conn: sqlite3.Connection, *, name: str, formula: str, needs: str, produces: str,
             reason: str, session_id: str, step_id: str | None = None) -> dict:
    """Add a step to the process. Returns it as a dict.

    With `step_id` (`added_<n>`) the step keeps that id, as when a module is adopted (SPEC 5.5).
    """
    values = [text.strip() for text in (name, formula, needs, produces, reason)]
    number = None
    if step_id is not None:
        found = ADDED_ID.match(step_id) if isinstance(step_id, str) else None
        if not found:
            raise ValueError(f"an added step id must look like added_1, not {step_id!r}")
        number = int(found.group(1))
        if conn.execute("SELECT 1 FROM added_steps WHERE id = ?", (number,)).fetchone():
            raise ValueError(f"there is already an added step {step_id}")
    cursor = conn.execute(
        "INSERT INTO added_steps (id, ts, session_id, name, formula, needs, produces, reason)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (number, datetime.now(timezone.utc).isoformat(), session_id, *values))
    conn.commit()
    step = _step(conn.execute("SELECT * FROM added_steps WHERE id = ?", (cursor.lastrowid,)).fetchone())
    db.record_event(conn, session_id=session_id, kind="build.step_added", actor="harness",
                    payload={"step": step})
    return step


def list_added_steps(conn: sqlite3.Connection) -> list[dict]:
    """Every added step, from any session, oldest first."""
    return [_step(row) for row in conn.execute("SELECT * FROM added_steps ORDER BY id")]


def process_steps(conn: sqlite3.Connection, brief: dict) -> list[dict]:
    """The process: the brief's steps in order, then the added steps."""
    return [*brief["process"], *list_added_steps(conn)]


def step_label(step_id: str) -> str:
    """A step id as the person sees it: an added step is marked as not in the brief."""
    return f"{step_id} {NOT_IN_BRIEF}" if step_id.startswith(ADDED_PREFIX) else step_id
