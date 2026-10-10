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


# ---- add_step --------------------------------------------------------------------------------


def test_the_id_is_added_and_the_row_id(conn):
    ids = [add_new_step(conn)["id"] for _ in range(3)]
    assert ids == ["added_1", "added_2", "added_3"]
    assert [r["id"] for r in rows(conn, "added_steps")] == [1, 2, 3]


# ---- list_added_steps, process_steps, step_label -----------------------------------------------


