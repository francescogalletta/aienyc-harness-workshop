"""The local SQLite database: migrations and the append-only event log (SPEC 3.5)."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config

MIGRATIONS = Path(__file__).parent / "migrations"
ACTORS = ("harness", "agent", "person")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path=None) -> sqlite3.Connection:
    """Open the database at `path`, or at the configured path, creating its folder."""
    path = Path(path) if path is not None else load_config().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply every migration file not yet applied, in filename order. Return their names."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                 "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    done = set(applied_migrations(conn))
    applied = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in done:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                     (path.name, _now()))
        conn.commit()
        applied.append(path.name)
    return applied


def applied_migrations(conn: sqlite3.Connection) -> list[str]:
    """Every applied migration file name, in filename order."""
    return [row["name"] for row in conn.execute("SELECT name FROM schema_migrations ORDER BY name")]


def record_event(conn: sqlite3.Connection, *, session_id: str, kind: str, actor: str,
                 payload: dict) -> int:
    """Append one event and return its id."""
    if actor not in ACTORS:
        raise ValueError(f"actor must be one of {', '.join(ACTORS)}, not {actor!r}")
    cursor = conn.execute(
        "INSERT INTO events (ts, session_id, kind, actor, payload) VALUES (?, ?, ?, ?, ?)",
        (_now(), session_id, kind, actor, json.dumps(payload)))
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
