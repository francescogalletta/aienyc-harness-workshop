"""Added steps (SPEC 5.5): calculations the person needed that the brief has no step for."""
import sqlite3
from datetime import datetime, timezone

from .. import db

ADDED_PREFIX = "added_"
NOT_IN_BRIEF = "(not in the brief)"


def _step(row) -> dict:
    return {"id": f"{ADDED_PREFIX}{row['id']}", "name": row["name"], "kind": "calculation",
            "method": "arithmetic", "formula": row["formula"], "needs": [row["needs"]],
            "produces": row["produces"], "reason": row["reason"]}


def add_step(conn: sqlite3.Connection, *, name: str, formula: str, needs: str, produces: str,
             reason: str, session_id: str) -> dict:
    """Add a step to the process. Returns it as a dict."""
    values = [text.strip() for text in (name, formula, needs, produces, reason)]
    cursor = conn.execute(
        "INSERT INTO added_steps (ts, session_id, name, formula, needs, produces, reason)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), session_id, *values))
    conn.commit()
    step = _step(conn.execute("SELECT * FROM added_steps WHERE id = ?", (cursor.lastrowid,)).fetchone())
    db.record_event(conn, session_id=session_id, kind="calc.step_added", actor="harness",
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
