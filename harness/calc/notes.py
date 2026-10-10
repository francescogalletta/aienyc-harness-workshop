"""Notes (SPEC 5.5): what the person said about their real situation during a build, kept for later."""
import sqlite3
from datetime import datetime, timezone

from .. import db


def add_note(conn: sqlite3.Connection, *, step_id: str, text: str, session_id: str) -> int:
    """Keep what the person said while step `step_id` was being built. Returns the note's id."""
    text = text.strip()
    if not text:
        raise ValueError("a note cannot be empty")
    cursor = conn.execute("INSERT INTO notes (ts, session_id, step_id, text) VALUES (?, ?, ?, ?)",
                          (datetime.now(timezone.utc).isoformat(), session_id, step_id, text))
    conn.commit()
    note_id = cursor.lastrowid
    db.record_event(conn, session_id=session_id, kind="build.note", actor="person",
                    payload={"id": note_id, "step": step_id, "text": text})
    return note_id


def list_notes(conn: sqlite3.Connection) -> list[dict]:
    """Every note, from any session, oldest first."""
    return [{"step": row["step_id"], "text": row["text"]}
            for row in conn.execute("SELECT step_id, text FROM notes ORDER BY id")]
