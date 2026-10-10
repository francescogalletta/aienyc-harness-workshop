"""SPEC 8.9 (with 7.3 and 7.4): the evidence API over a conversation with a gate, a side conversation, a judgment and a
reply, served by the real server. The API gains no path and no key."""
import json

import pytest

import step4_helpers as s4
from step4_helpers import BONUS, CHAT, SET_ASIDE, h, side

EVENT_KEYS = ["id", "ts", "kind", "actor", "payload", "numbers"]
TRACE_KEYS = ["text", "start", "end", "source", "run_id"]
DECISION_EVENT_KEYS = ["id", "kind", "step", "question", "options", "choice", "words", "runs"]
GATE = s4.gate_block(s4.surplus_item(s4.ASSUME, "5000 less 3000"))
FINAL = "You will set 3,333 aside, from the 2,000 left each month."


@pytest.fixture
def story(conn, brief, installed):
    s4.tell_the_story(conn, brief)


@pytest.fixture
def body(story, api):
    status, body = api.get(f"/api/work/conversation?session={CHAT}")
    assert status == 200
    return body


def events_of(body, kind):
    return [e for e in body["events"] if e["kind"] == kind]


def counted(e):
    """The traced numbers of an event, without the small ones (list numbers and the like)."""
    return [(i["text"], i["source"], i["run_id"]) for i in e["numbers"] if i["source"] != "small"]


def test_the_kinds_in_order_with_both_decisions(body):
    kinds = [e["kind"] for e in body["events"]]
    order = ["ask.message", "ask.gate", "aside.opened", "aside.message", "aside.reply", "aside.closed", "ask.decision",
             "calc.run", "ask.decision_asked", "ask.decision", "ask.reply"]
    positions = []
    start = 0
    for kind in order:
        start = kinds.index(kind, start)
        positions.append(start)
        start += 1
    assert positions == sorted(positions)


def test_the_decision_block_is_traced_with_the_run_and_the_carried_text(body):
    [asked] = events_of(body, "ask.decision_asked")
    assert asked["actor"] == "agent" and set(asked["payload"]) == {"arguments", "block"}
    block = asked["payload"]["block"]
    for item in asked["numbers"]:
        assert block[item["start"]:item["end"]] == item["text"]
    assert counted(asked) == [("2,000", "run", 1), ("1,200", "person", None)]


@pytest.fixture
def api_after(served):
    """The api, started when asked for (after the test has made its conversation)."""
    class Late:
        @staticmethod
        def get(path):
            send = served()
            reply = send("GET", path)
            return reply.status, reply.json()
    return Late
