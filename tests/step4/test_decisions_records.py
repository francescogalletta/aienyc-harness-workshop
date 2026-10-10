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


@pytest.mark.parametrize("kind", ["assumptions", "judgment", "build"])
def test_every_kind_is_taken(decisions, conn, kind):
    assert record(decisions, conn, kind=kind)["kind"] == kind


def test_it_records_the_event_ask_decision_of_the_person_without_ts_and_session(decisions, conn):
    decision = record(decisions, conn, step_id=None, choice="something else", words="Neither, please")
    [(kind, actor, payload)] = h.events(conn, "ask.decision")
    assert (kind, actor) == ("ask.decision", "person")
    assert payload == {key: decision[key] for key in EVENT_KEYS}
    assert payload["step"] is None and payload["choice"] == "something else"
    assert [r["session_id"] for r in conn.execute("SELECT session_id FROM events WHERE kind = 'ask.decision'")] == [SESSION]
