"""SPEC 5.5: notes, what the person said about their real situation, kept between sessions."""
from datetime import datetime, timedelta

import pytest

from harness import db
from step2_helpers import SESSION, events, rows


def test_the_notes_migration_creates_the_table(conn):
    columns = [(r["name"], r["type"], r["notnull"], r["pk"]) for r in conn.execute("PRAGMA table_info(notes)")]
    assert columns == [("id", "INTEGER", 0, 1), ("ts", "TEXT", 1, 0), ("session_id", "TEXT", 1, 0),
                       ("step_id", "TEXT", 1, 0), ("text", "TEXT", 1, 0)]
    assert "0004_notes.sql" in db.applied_migrations(conn)


def test_a_note_is_stored_with_its_step_session_and_time(conn, notes):
    note_id = notes.add_note(conn, step_id="s1", text="I have 3 flatmates", session_id=SESSION)
    [row] = rows(conn, "notes")
    assert row["id"] == note_id
    assert (row["step_id"], row["session_id"], row["text"]) == ("s1", SESSION, "I have 3 flatmates")
    assert datetime.fromisoformat(row["ts"]).utcoffset() == timedelta(0)           # UTC, ISO 8601


def test_ids_are_given_in_turn(conn, notes):
    first = notes.add_note(conn, step_id="s1", text="one", session_id=SESSION)
    second = notes.add_note(conn, step_id="s1", text="two", session_id=SESSION)
    assert second == first + 1


def test_the_text_is_stripped(conn, notes):
    notes.add_note(conn, step_id="s1", text="  \n spaced out \t ", session_id=SESSION)
    assert rows(conn, "notes")[0]["text"] == "spaced out"


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_an_empty_note_is_refused_and_leaves_nothing(conn, notes, text):
    with pytest.raises(ValueError) as error:
        notes.add_note(conn, step_id="s1", text=text, session_id=SESSION)
    assert str(error.value) == "a note cannot be empty"
    assert rows(conn, "notes") == [] and events(conn, "calc.note_saved") == []


def test_a_note_is_committed(conn, notes):
    notes.add_note(conn, step_id="s1", text="kept", session_id=SESSION)
    other = db.connect()
    try:
        assert [r["text"] for r in other.execute("SELECT text FROM notes")] == ["kept"]
    finally:
        other.close()


def test_adding_a_note_records_an_event_with_the_session_id(conn, notes):
    note_id = notes.add_note(conn, step_id="s2", text="  I rent a flat  ", session_id=SESSION)
    assert events(conn, "calc.note_saved") == [("calc.note_saved", "person", {
        "id": note_id, "step": "s2", "text": "I rent a flat"})]
    assert [r["session_id"] for r in conn.execute("SELECT session_id FROM events WHERE kind = 'calc.note_saved'")] == [SESSION]


def test_no_notes_is_an_empty_list(conn, notes):
    assert notes.list_notes(conn) == []


def test_notes_are_listed_oldest_first_from_every_session_as_step_and_text(conn, notes):
    notes.add_note(conn, step_id="s3", text="third step, first said", session_id="one")
    notes.add_note(conn, step_id="s1", text="first step, said second", session_id="two")
    notes.add_note(conn, step_id="s3", text="again", session_id=SESSION)
    assert notes.list_notes(conn) == [
        {"step": "s3", "text": "third step, first said"}, {"step": "s1", "text": "first step, said second"},
        {"step": "s3", "text": "again"}]
