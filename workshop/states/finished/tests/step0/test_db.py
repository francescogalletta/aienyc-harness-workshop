"""SPEC 3.5: the local database."""
import json
import sqlite3
from datetime import datetime

import pytest

from harness import db


def test_connect_creates_the_folder_and_uses_the_configured_path(monkeypatch, tmp_path):
    path = tmp_path / "nested" / "folder" / "harness.db"
    monkeypatch.setenv("HARNESS_DB", str(path))
    conn = db.connect()
    assert path.exists()
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.row_factory is sqlite3.Row


def test_migrate_applies_once(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    first = db.migrate(conn)
    assert first and first[0] == "0001_init.sql"
    assert first == sorted(first)
    assert db.migrate(conn) == []
    assert db.applied_migrations(conn) == first
    names = [row["name"] for row in conn.execute("SELECT name FROM schema_migrations ORDER BY name")]
    assert names == first
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"events", "schema_migrations"} <= tables


def test_migrations_survive_reopening(tmp_path):
    path = tmp_path / "a.db"
    conn = db.connect(path)
    db.migrate(conn)
    db.record_event(conn, session_id="s", kind="k", actor="harness", payload={})
    conn.close()
    again = db.connect(path)
    assert db.migrate(again) == []
    assert len(db.list_events(again)) == 1


def test_record_and_list_events(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    db.migrate(conn)
    first = db.record_event(conn, session_id="s1", kind="thing.happened", actor="agent",
                            payload={"amount": "12.50", "nested": {"ok": True}})
    second = db.record_event(conn, session_id="s2", kind="other.thing", actor="person", payload={})
    assert isinstance(first, int) and second > first

    rows = db.list_events(conn)
    assert [row["id"] for row in rows] == [first, second]
    row = rows[0]
    assert (row["session_id"], row["kind"], row["actor"]) == ("s1", "thing.happened", "agent")
    assert json.loads(row["payload"]) == {"amount": "12.50", "nested": {"ok": True}}
    stamp = datetime.fromisoformat(row["ts"])
    assert stamp.utcoffset() is not None and stamp.utcoffset().total_seconds() == 0

    assert [r["id"] for r in db.list_events(conn, session_id="s2")] == [second]
    assert [r["id"] for r in db.list_events(conn, kind="thing.happened")] == [first]
    assert db.list_events(conn, session_id="s1", kind="other.thing") == []


def test_unknown_actor_is_refused(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    db.migrate(conn)
    with pytest.raises(ValueError):
        db.record_event(conn, session_id="s", kind="k", actor="somebody", payload={})
    assert db.list_events(conn) == []


def test_events_cannot_be_changed_or_removed(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    db.migrate(conn)
    db.record_event(conn, session_id="s", kind="k", actor="harness", payload={"v": 1})
    with pytest.raises(sqlite3.DatabaseError, match="events is append-only"):
        conn.execute("UPDATE events SET payload = '{}'")
    with pytest.raises(sqlite3.DatabaseError, match="events is append-only"):
        conn.execute("DELETE FROM events")
    assert json.loads(db.list_events(conn)[0]["payload"]) == {"v": 1}
