"""The local SQLite database: one schema file per layer, and the append-only event log (SPEC 2.2).

There is no migration history. Every schema file says `CREATE ... IF NOT
EXISTS` and is applied on connect for the enabled layers. After a schema
change, delete the database file.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config

BASE_SCHEMA = Path(__file__).with_name("schema.sql")
ACTORS = ("harness", "agent", "person")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path=None) -> sqlite3.Connection:
    """Open the database at `path`, or at the configured path, creating its folder.

    WAL mode and a busy timeout of five seconds let one thread read while another writes.
    The connection may be used only on the thread that opened it.
    """
    path = Path(path) if path is not None else load_config().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schemas(conn: sqlite3.Connection, layers=()) -> None:
    """Run harness/schema.sql, then the schema of each layer given, in order.

    `layers` holds Layer objects (their `schema`, which may be None) or paths.
    """
    done = set()
    for each in (BASE_SCHEMA, *layers):
        path = getattr(each, "schema", each)
        if path is None or Path(path).resolve() in done:
            continue
        done.add(Path(path).resolve())
        conn.executescript(Path(path).read_text(encoding="utf-8"))
    conn.commit()


def record_event(conn: sqlite3.Connection, *, session_id: str, kind: str, actor: str,
                 payload: dict) -> int:
    """Append one event and return its id."""
    if actor not in ACTORS:
        raise ValueError(f"actor must be one of {', '.join(ACTORS)}, not {actor!r}")
    cursor = conn.execute(
        "INSERT INTO events (ts, session_id, kind, actor, payload) VALUES (?, ?, ?, ?, ?)",
        (now(), session_id, kind, actor, json.dumps(payload)))
    conn.commit()
    return cursor.lastrowid


def list_events(conn: sqlite3.Connection, *, session_id=None, kind=None) -> list[sqlite3.Row]:
    """Events matching the given filters, oldest first."""
    return conn.execute(
        "SELECT * FROM events"
        " WHERE (:session_id IS NULL OR session_id = :session_id)"
        " AND (:kind IS NULL OR kind = :kind)"
        " ORDER BY id",
        {"session_id": session_id, "kind": kind}).fetchall()
