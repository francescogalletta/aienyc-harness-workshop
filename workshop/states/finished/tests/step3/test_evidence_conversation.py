"""SPEC 7.3 and 7.4: `GET /api/work/conversation`, one conversation as it happened, with its numbers traced."""

import pytest

import step3_helpers as s3
from step3_evidence_helpers import (CONVERSATION_KEYS, TRACE_KEYS, add_session)
from step3_helpers import CHAT1, traced


def get(api, session):
    return api.get(f"/api/work/conversation?session={session}")


def numbers_by_id(body):
    return {e["id"]: e["numbers"] for e in body["events"]}


# ---- the shape -----------------------------------------------------------------------------------------------------

def test_the_keys_of_a_conversation(api):
    status, body = get(api, CHAT1)
    assert status == 200 and set(CONVERSATION_KEYS) <= set(body) and body["session_id"] == CHAT1


# ---- which events have numbers ------------------------------------------------------------------------------------------


def test_the_numbers_of_a_reply(api):
    _, body = get(api, CHAT1)
    reply = next(e for e in body["events"] if e["id"] == 25)
    assert reply["numbers"] == traced(s3.GOOD_REPLY, s3.GOOD_REPLY_NUMBERS)
    assert all(set(TRACE_KEYS) <= set(item) for item in reply["numbers"])
    for item in reply["numbers"]:
        assert s3.GOOD_REPLY[item["start"]:item["end"]] == item["text"]


# ---- the sources, one by one, in sessions made for the purpose --------------------------------------------------------------

@pytest.fixture
def probe(api, world):
    """Record a conversation and read it back. `probe(events)` -> the body; each entry is (kind, payload[, actor]).

    The session is new, so every event of the recorded story is earlier than its events.
    """
    from harness import db
    counter = [0]

    def make(*entries, session=None):
        counter[0] += 1
        session = session or f"probe-{counter[0]}"
        conn = db.connect()
        try:
            ids = add_session(conn, session, *entries)
        finally:
            conn.close()
        status, body = get(api, session)
        assert status == 200, body
        make.ids, make.session = ids, session
        return body

    return make


def message(text):
    return ("ask.message", {"text": text}, "person")


def started(day):
    return ("ask.started", {"today": day}, "harness")


def reply(text):
    return ("ask.reply", {"text": text}, "agent")


def ran(run_id, inputs, output, module="monthly_surplus"):
    return ("calc.run", {"module": module, "run_id": run_id, "test_run_id": 1, "inputs": inputs, "output": output}, "harness")


def labels(body, event_id_or_index=-1):
    event = body["events"][event_id_or_index]
    return [(item["text"], item["source"], item["run_id"]) for item in event["numbers"]]


# ---- the order of the labels -----------------------------------------------------------------------------------------------

LABEL_ORDER = [
    ("run beats input", [ran(81, {"x": "4321"}, "1"), ("ask.input_saved", {"name": "n", "value": "4321", "note": ""}, "agent")], "run", 81),
    ("run beats person", [ran(82, {"x": "4321"}, "1"), message("it is 4321")], "run", 82),
    ("input beats note", [("ask.input_saved", {"name": "n", "value": "4321", "note": ""}, "agent"),
                           ("calc.note_saved", {"id": 9, "step": "s1", "text": "4321"}, "person")], "input", None),
    ("note beats person", [("calc.note_saved", {"id": 9, "step": "s1", "text": "4321"}, "person"), message("4321")], "note", None),
    ("person alone", [message("it is 4321")], "person", None),
]


# ---- small numbers -----------------------------------------------------------------------------------------------------------------


# ---- k and % --------------------------------------------------------------------------------------------------------------------------


# ---- dates ---------------------------------------------------------------------------------------------------------------------------------


# ---- every occurrence, in order, with places counted in code points ----------------------------------------------------------------------


# ---- the other traced kinds, in sessions made for the purpose ----------------------------------------------------------------------------------


# ---- errors ---------------------------------------------------------------------------------------------------------------------------------------
