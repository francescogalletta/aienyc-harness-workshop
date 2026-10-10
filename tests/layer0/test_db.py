"""SPEC 2.2: the database. One schema file per layer, applied on connect; no migration history."""
import json
import sqlite3
from datetime import datetime

import pytest

from harness import db
from layer0_helpers import fake_layer


def tables(conn) -> set[str]:
    return {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_connect_creates_the_folder_and_sets_wal_busy_timeout_and_foreign_keys(monkeypatch, tmp_path):
    path = tmp_path / "nested" / "folder" / "harness.db"
    monkeypatch.setenv("HARNESS_DB", str(path))
    conn = db.connect()
    assert path.exists()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.row_factory is sqlite3.Row


def test_the_base_schema_makes_the_core_tables_and_can_be_applied_again(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    db.apply_schemas(conn, [])
    db.record_event(conn, session_id="s", kind="core.test", actor="harness", payload={})
    db.apply_schemas(conn, [])          # again: nothing is lost, nothing fails
    assert {"events", "meta", "messages", "threads"} <= tables(conn)
    assert len(db.list_events(conn)) == 1
    assert "schema_migrations" not in tables(conn)


def test_each_layer_schema_given_is_applied_and_a_layer_without_one_is_skipped(tmp_path):
    schema = tmp_path / "schema.sql"
    schema.write_text("CREATE TABLE IF NOT EXISTS fake_things (id INTEGER PRIMARY KEY);", encoding="utf-8")
    conn = db.connect(tmp_path / "a.db")
    db.apply_schemas(conn, [fake_layer(1, schema=schema), fake_layer(2)])
    assert {"events", "fake_things"} <= tables(conn)


def test_the_message_and_thread_tables_have_the_columns_of_the_contract(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    db.apply_schemas(conn, [])
    columns = {table: {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
               for table in ("meta", "messages", "threads")}
    assert columns["meta"] == {"key", "value"}
    assert columns["messages"] == {"id", "ts", "conversation", "thread", "who", "text", "step", "kind", "data"}
    assert columns["threads"] == {"id", "ts", "conversation", "kind", "step", "after", "title", "status"}


def test_record_and_list_events(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    db.apply_schemas(conn, [])
    first = db.record_event(conn, session_id="s1", kind="thing.happened", actor="agent",
                            payload={"amount": "12.50", "nested": {"ok": True}})
    second = db.record_event(conn, session_id="s2", kind="other.thing", actor="person", payload={})
    rows = db.list_events(conn)
    assert [row["id"] for row in rows] == [first, second]
    assert json.loads(rows[0]["payload"]) == {"amount": "12.50", "nested": {"ok": True}}
    assert datetime.fromisoformat(rows[0]["ts"]).utcoffset().total_seconds() == 0
    assert [r["id"] for r in db.list_events(conn, session_id="s2")] == [second]
    assert [r["id"] for r in db.list_events(conn, kind="thing.happened")] == [first]


def test_events_are_append_only_and_the_actor_is_checked(tmp_path):
    conn = db.connect(tmp_path / "a.db")
    db.apply_schemas(conn, [])
    db.record_event(conn, session_id="s", kind="k.k", actor="harness", payload={})
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE events SET kind = 'changed'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM events")
    with pytest.raises(ValueError):
        db.record_event(conn, session_id="s", kind="k.k", actor="somebody", payload={})
