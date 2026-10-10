"""SPEC 5.5: notes, what the person said about their real situation, kept between sessions."""
from datetime import datetime, timedelta

import pytest

from harness import db
from step2_helpers import SESSION, events, rows


def test_notes_are_listed_oldest_first_from_every_session_as_step_and_text(conn, notes):
    notes.add_note(conn, step_id="s3", text="third step, first said", session_id="one")
    notes.add_note(conn, step_id="s1", text="first step, said second", session_id="two")
    notes.add_note(conn, step_id="s3", text="again", session_id=SESSION)
    assert notes.list_notes(conn) == [
        {"step": "s3", "text": "third step, first said"}, {"step": "s1", "text": "first step, said second"},
        {"step": "s3", "text": "again"}]
