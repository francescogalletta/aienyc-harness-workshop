"""SPEC 8.1: the decisions table, `record_decision`, `list_decisions` and `choice_words`."""
import json
from datetime import datetime, timedelta

import pytest

import step4_helpers as s4
from harness import db
from step4_helpers import SESSION, h

MIGRATION = """\
-- Step 4: what the person decided in a conversation (SPEC 8.1).

CREATE TABLE decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,        -- UTC, ISO 8601
    session_id  TEXT NOT NULL,        -- the conversation
    kind        TEXT NOT NULL,        -- 'assumptions' | 'judgment' | 'build'
    step_id     TEXT,                 -- the step it belongs to, or NULL
    question    TEXT NOT NULL,        -- the block shown, exactly
    options     TEXT NOT NULL,        -- JSON list of the options shown; [] for a yes or no
    choice      TEXT NOT NULL,        -- 'yes' or 'no'; for a judgment '1' to '4' or 'something else'
    words       TEXT NOT NULL,        -- what the person typed, stripped
    runs        TEXT NOT NULL         -- JSON list of the calc_runs ids it rested on
);
"""
KEYS = ["id", "ts", "session_id", "kind", "step", "question", "options", "choice", "words", "runs"]
EVENT_KEYS = ["id", "kind", "step", "question", "options", "choice", "words", "runs"]


def record(decisions, conn, **changes):
    arguments = {"session_id": SESSION, "kind": "judgment", "step_id": "s2", "question": "Only you can decide this:",
                 "options": ["Keep the date", "Move the date"], "choice": "2", "words": "2", "runs": [1, 2]}
    arguments.update(changes)
    return decisions.record_decision(conn, **arguments)


# ---- the table -------------------------------------------------------------------------------------------

def test_the_migration_creates_the_table(conn):
    columns = [(r["name"], r["type"], r["notnull"], r["pk"]) for r in conn.execute("PRAGMA table_info(decisions)")]
    assert columns == [("id", "INTEGER", 0, 1), ("ts", "TEXT", 1, 0), ("session_id", "TEXT", 1, 0),
                       ("kind", "TEXT", 1, 0), ("step_id", "TEXT", 0, 0), ("question", "TEXT", 1, 0),
                       ("options", "TEXT", 1, 0), ("choice", "TEXT", 1, 0), ("words", "TEXT", 1, 0),
                       ("runs", "TEXT", 1, 0)]
    assert "0006_decisions.sql" in db.applied_migrations(conn)


def test_the_migration_file_is_the_one_of_the_spec():
    assert (db.MIGRATIONS / "0006_decisions.sql").read_text(encoding="utf-8").strip() == MIGRATION.strip()


def test_the_migrations_are_applied_in_order(conn):
    names = db.applied_migrations(conn)
    assert names == sorted(names) and names[-1] >= "0006_decisions.sql"


def test_the_constants(decisions):
    assert decisions.KINDS == ("assumptions", "judgment", "build")
    assert decisions.SOMETHING_ELSE == "something else"
    for name in ("GATE_INTRO", "GATE_QUESTION", "DECISION_INTRO", "DECISION_INTRO_STEP", "DECISION_SUGGESTS",
                 "DECISION_QUESTION", "DECISION_QUESTION_SUGGESTED"):
        assert getattr(decisions, name) == getattr(s4, name), name


# ---- record_decision --------------------------------------------------------------------------------------

def test_a_decision_is_a_dict_with_exactly_these_keys_in_order(decisions, conn):
    decision = record(decisions, conn)
    assert list(decision) == KEYS
    assert decision["step"] == "s2" and decision["options"] == ["Keep the date", "Move the date"]
    assert decision["runs"] == [1, 2] and decision["session_id"] == SESSION
    assert (decision["kind"], decision["choice"], decision["words"]) == ("judgment", "2", "2")
    assert datetime.fromisoformat(decision["ts"]).utcoffset() == timedelta(0)


def test_ids_are_the_row_ids_in_turn(decisions, conn):
    ids = [record(decisions, conn)["id"] for _ in range(3)]
    assert ids == [1, 2, 3]
    assert [r["id"] for r in h.rows(conn, "decisions")] == [1, 2, 3]


def test_the_row_holds_the_json_of_options_and_runs(decisions, conn):
    decision = record(decisions, conn)
    [row] = h.rows(conn, "decisions")
    assert (row["id"], row["session_id"], row["kind"], row["step_id"], row["question"], row["choice"], row["words"]) == (
        decision["id"], SESSION, "judgment", "s2", "Only you can decide this:", "2", "2")
    assert json.loads(row["options"]) == ["Keep the date", "Move the date"] and json.loads(row["runs"]) == [1, 2]
    assert row["ts"] == decision["ts"]


def test_a_step_of_none_is_stored_as_null_and_comes_back_as_none(decisions, conn):
    decision = record(decisions, conn, kind="assumptions", step_id=None, options=[], choice="yes", runs=[])
    assert decision["step"] is None and h.rows(conn, "decisions")[0]["step_id"] is None


@pytest.mark.parametrize("kind", ["assumption", "Judgment", "", "approval"])
def test_an_unknown_kind_is_refused_and_leaves_nothing(decisions, conn, kind):
    with pytest.raises(ValueError) as error:
        record(decisions, conn, kind=kind)
    assert str(error.value) == f"unknown kind: {kind}"
    assert h.rows(conn, "decisions") == [] and h.events(conn, "ask.decision") == []


@pytest.mark.parametrize("kind", ["assumptions", "judgment", "build"])
def test_every_kind_is_taken(decisions, conn, kind):
    assert record(decisions, conn, kind=kind)["kind"] == kind


def test_a_decision_is_committed(decisions, conn):
    record(decisions, conn)
    other = db.connect()
    try:
        assert [r["words"] for r in other.execute("SELECT words FROM decisions")] == ["2"]
    finally:
        other.close()


def test_it_records_the_event_ask_decision_of_the_person_without_ts_and_session(decisions, conn):
    decision = record(decisions, conn, step_id=None, choice="something else", words="Neither, please")
    [(kind, actor, payload)] = h.events(conn, "ask.decision")
    assert (kind, actor) == ("ask.decision", "person")
    assert list(payload) == EVENT_KEYS
    assert payload == {key: decision[key] for key in EVENT_KEYS}
    assert payload["step"] is None and payload["choice"] == "something else"
    assert [r["session_id"] for r in conn.execute("SELECT session_id FROM events WHERE kind = 'ask.decision'")] == [SESSION]


# ---- list_decisions -------------------------------------------------------------------------------------------

def test_no_decision_is_an_empty_list(decisions, conn):
    assert decisions.list_decisions(conn) == [] and decisions.list_decisions(conn, session_id="x") == []


def test_the_decisions_of_every_session_oldest_first(decisions, conn):
    made = [record(decisions, conn, session_id=s, words=str(n)) for n, s in enumerate(["a", "b", "a", "c"], 1)]
    listed = decisions.list_decisions(conn)
    assert listed == made and [d["id"] for d in listed] == [1, 2, 3, 4]
    assert all(list(d) == KEYS for d in listed)


def test_the_decisions_of_one_session(decisions, conn):
    for n, s in enumerate(["a", "b", "a", "c"], 1):
        record(decisions, conn, session_id=s, words=str(n))
    assert [d["words"] for d in decisions.list_decisions(conn, session_id="a")] == ["1", "3"]
    assert decisions.list_decisions(conn, session_id="c")[0]["id"] == 4
    assert decisions.list_decisions(conn, session_id="nobody") == []
    assert [d["id"] for d in decisions.list_decisions(conn, session_id=None)] == [1, 2, 3, 4]


def test_a_listed_decision_has_lists_for_options_and_runs(decisions, conn):
    record(decisions, conn, kind="build", step_id="s1", options=[], choice="no", words="not now", runs=[])
    [listed] = decisions.list_decisions(conn)
    assert listed["options"] == [] and listed["runs"] == [] and listed["step"] == "s1"


# ---- choice_words -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind, choice, expected", [
    ("assumptions", "yes", "yes"), ("assumptions", "no", "no"), ("build", "yes", "yes"), ("build", "no", "no")])
def test_a_yes_or_no_is_said_as_it_is(decisions, conn, kind, choice, expected):
    decision = record(decisions, conn, kind=kind, step_id=None, options=[], choice=choice, runs=[])
    assert decisions.choice_words(decision) == expected


def test_a_numbered_choice_gives_its_number_and_option(decisions, conn):
    assert decisions.choice_words(record(decisions, conn, choice="2")) == "2. Move the date"
    assert decisions.choice_words(record(decisions, conn, choice="1")) == "1. Keep the date"


def test_something_else_is_said_as_it_is(decisions, conn):
    assert decisions.choice_words(record(decisions, conn, choice="something else", words="neither")) == "something else"


def test_four_options(decisions, conn):
    options = ["Wait", "Move it", "Keep it", "Ask again"]
    assert decisions.choice_words(record(decisions, conn, options=options, choice="4")) == "4. Ask again"
