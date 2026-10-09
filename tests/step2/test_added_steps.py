"""SPEC 5.5: added steps, the calculations the person needs that the brief has no step for."""
from datetime import datetime, timedelta

import pytest

from harness import db
from step2_helpers import ADDED_PREFIX, NEW_TEXTS, NOT_IN_BRIEF, SESSION, add_new_step, added_step, events, label, rows

MIGRATION = """\
-- Step 2: calculation steps added in a conversation, not in the brief (SPEC 5.5).

CREATE TABLE added_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,   -- the step id is 'added_<id>'
    ts          TEXT NOT NULL,        -- UTC, ISO 8601
    session_id  TEXT NOT NULL,        -- the conversation it was added in
    name        TEXT NOT NULL,        -- what it works out, in the agent's words
    formula     TEXT NOT NULL,
    needs       TEXT NOT NULL,        -- what it is worked out from, in the agent's words
    produces    TEXT NOT NULL,
    reason      TEXT NOT NULL         -- why the agent asked for it
);
"""


def test_the_migration_creates_the_table(conn):
    columns = [(r["name"], r["type"], r["notnull"], r["pk"]) for r in conn.execute("PRAGMA table_info(added_steps)")]
    assert columns == [("id", "INTEGER", 0, 1), ("ts", "TEXT", 1, 0), ("session_id", "TEXT", 1, 0),
                       ("name", "TEXT", 1, 0), ("formula", "TEXT", 1, 0), ("needs", "TEXT", 1, 0),
                       ("produces", "TEXT", 1, 0), ("reason", "TEXT", 1, 0)]
    assert "0005_added_steps.sql" in db.applied_migrations(conn)


def test_the_migration_file_is_the_one_of_the_spec():
    assert (db.MIGRATIONS / "0005_added_steps.sql").read_text(encoding="utf-8").strip() == MIGRATION.strip()


def test_the_constants(added):
    assert (added.ADDED_PREFIX, added.NOT_IN_BRIEF) == (ADDED_PREFIX, NOT_IN_BRIEF)


# ---- add_step --------------------------------------------------------------------------------

def test_a_step_is_returned_as_a_dict_with_its_keys_in_order(conn):
    step = add_new_step(conn, session_id=SESSION)
    assert step == added_step(1)
    assert list(step) == ["id", "name", "kind", "method", "formula", "needs", "produces", "reason"]


def test_the_id_is_added_and_the_row_id(conn):
    ids = [add_new_step(conn)["id"] for _ in range(3)]
    assert ids == ["added_1", "added_2", "added_3"]
    assert [r["id"] for r in rows(conn, "added_steps")] == [1, 2, 3]


def test_the_row_holds_the_texts_the_session_and_the_time(conn):
    add_new_step(conn, session_id=SESSION)
    [row] = rows(conn, "added_steps")
    assert (row["session_id"], row["name"], row["formula"], row["needs"], row["produces"], row["reason"]) == (
        SESSION, NEW_TEXTS["works_out"], NEW_TEXTS["formula"], NEW_TEXTS["from_what"], NEW_TEXTS["gives"],
        NEW_TEXTS["why"])
    assert datetime.fromisoformat(row["ts"]).utcoffset() == timedelta(0)


def test_each_text_is_stripped(conn):
    step = add_new_step(conn, name="  a name \n", formula=" f ", needs="\tn ", produces=" p\n", reason="  r  ")
    assert step == added_step(1, name="a name", formula="f", needs=["n"], produces="p", reason="r")
    assert rows(conn, "added_steps")[0]["name"] == "a name"


def test_a_step_is_committed(conn):
    add_new_step(conn)
    other = db.connect()
    try:
        assert other.execute("SELECT COUNT(*) FROM added_steps").fetchone()[0] == 1
    finally:
        other.close()


def test_adding_a_step_records_an_event_with_the_session_id(conn):
    step = add_new_step(conn, session_id=SESSION)
    assert events(conn, "calc.step_added") == [("calc.step_added", "harness", {"step": step})]
    assert [r["session_id"] for r in conn.execute("SELECT session_id FROM events WHERE kind = 'calc.step_added'")] == [SESSION]


# ---- list_added_steps, process_steps, step_label -----------------------------------------------

def test_no_added_steps_is_an_empty_list(conn, added):
    assert added.list_added_steps(conn) == []


def test_added_steps_are_listed_oldest_first_from_every_session(conn, added):
    add_new_step(conn, session_id="one", name="first")
    add_new_step(conn, session_id="two", name="second")
    assert [s["name"] for s in added.list_added_steps(conn)] == ["first", "second"]
    assert [s["id"] for s in added.list_added_steps(conn)] == ["added_1", "added_2"]


def test_the_process_is_the_brief_steps_and_then_the_added_steps(conn, added, brief):
    add_new_step(conn, name="first")
    add_new_step(conn, name="second")
    process = added.process_steps(conn, brief)
    assert process == brief["process"] + [added_step(1, name="first"), added_step(2, name="second")]


def test_without_added_steps_the_process_is_the_brief_process(conn, added, brief):
    assert added.process_steps(conn, brief) == brief["process"]


@pytest.mark.parametrize("step_id, expected", [
    ("s1", "s1"), ("added_1", "added_1 (not in the brief)"), ("added_", "added_ (not in the brief)"),
    ("xadded_1", "xadded_1"), ("s1_added_1", "s1_added_1")])
def test_step_label(added, step_id, expected):
    assert added.step_label(step_id) == expected == label(step_id)
