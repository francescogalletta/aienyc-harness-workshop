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


# ---- the conversation ---------------------------------------------------------------------------------------------------------

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


def test_every_event_has_the_same_keys_as_before(body):
    assert all(list(e) == EVENT_KEYS for e in body["events"])
    assert list(body) == ["session_id", "today", "replay", "events"]


def test_the_gate_event_holds_the_calls_as_sent_and_the_block(body):
    [gate] = events_of(body, "ask.gate")
    assert gate["actor"] == "agent" and set(gate["payload"]) == {"calls", "block"}
    assert gate["payload"]["calls"] == [s4.run_args(expected="5000 less 3000")]
    assert gate["payload"]["block"] == GATE


def test_the_gate_block_is_traced_over_the_block(body):
    [gate] = events_of(body, "ask.gate")
    assert all(list(item) == TRACE_KEYS for item in gate["numbers"])
    block = gate["payload"]["block"]
    for item in gate["numbers"]:
        assert block[item["start"]:item["end"]] == item["text"]
    assert counted(gate) == [("5000", "person", None), ("3000", "person", None)]


def test_the_decision_block_is_traced_with_the_run_and_the_carried_text(body):
    [asked] = events_of(body, "ask.decision_asked")
    assert asked["actor"] == "agent" and set(asked["payload"]) == {"arguments", "block"}
    block = asked["payload"]["block"]
    for item in asked["numbers"]:
        assert block[item["start"]:item["end"]] == item["text"]
    assert counted(asked) == [("2,000", "run", 1), ("1,200", "person", None)]


def test_the_reply_is_traced_to_the_words_of_the_decision_and_to_the_run(body):
    [reply] = events_of(body, "ask.reply")
    assert reply["payload"]["text"] == FINAL
    assert counted(reply) == [("3,333", "person", None), ("2,000", "run", 1)]


def test_everything_else_is_not_traced(body):
    traced = {"ask.reply", "ask.withheld", "ask.correction", "ask.module_requested", "ask.gate", "ask.decision_asked"}
    for event in body["events"]:
        if event["kind"] not in traced:
            assert event["numbers"] is None, event["kind"]


def test_the_decisions_are_events_of_the_person_without_numbers(body):
    decisions = events_of(body, "ask.decision")
    assert [d["actor"] for d in decisions] == ["person", "person"]
    assert [d["payload"]["kind"] for d in decisions] == ["assumptions", "judgment"]
    assert all(list(d["payload"]) == DECISION_EVENT_KEYS and d["numbers"] is None for d in decisions)
    assert decisions[1]["payload"]["words"] == SET_ASIDE and decisions[1]["payload"]["runs"] == [1]
    assert decisions[1]["payload"]["choice"] == "something else" and decisions[1]["payload"]["step"] == "s2"


def test_the_side_conversation_events_are_there_with_their_number(body):
    asides = [e for e in body["events"] if e["kind"].startswith("aside.")]
    assert [e["kind"] for e in asides] == ["aside.opened", "aside.message", "aside.reply", "aside.closed"]
    assert {e["payload"]["aside"] for e in asides} == {1}
    assert all(e["numbers"] is None for e in asides)
    closed = asides[-1]["payload"]
    assert closed == {"aside": 1, "turns": 1, "how": "back", "carried": BONUS}
    assert asides[0]["payload"]["looking_at"] == GATE


def test_the_carried_text_is_not_a_message_of_the_conversation(body):
    assert [e["payload"]["text"] for e in events_of(body, "ask.message")] == [h.QUESTION]


def test_the_function_gives_the_same_body(story, api, evidence, conn):
    expected = json.loads(json.dumps(evidence.conversation(conn, CHAT)))
    assert api.get(f"/api/work/conversation?session={CHAT}")[1] == expected


# ---- a side conversation's own texts are not traced ------------------------------------------------------------------------------------

def test_the_texts_a_side_conversation_corrected_or_held_back_are_not_traced(talk, api_after):
    script = [h.say_text("Hello."), side("You need 3,333."), side("Really 5,555.")]
    talk(script, ["/aside what?", "/back", "no", "/quit"])
    status, body = api_after.get(f"/api/work/conversation?session={h.SESSION}")
    assert status == 200
    asides = {e["kind"]: e for e in body["events"] if e["kind"].startswith("aside.")}
    assert {"aside.correction", "aside.withheld", "aside.opened", "aside.closed"} <= set(asides)
    assert asides["aside.correction"]["payload"]["numbers"] == ["3,333"] and asides["aside.correction"]["numbers"] is None
    assert asides["aside.withheld"]["payload"]["numbers"] == ["5,555"] and asides["aside.withheld"]["numbers"] is None
    assert "aside.reply" not in asides


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


def test_the_words_of_a_gate_answer_are_the_persons_for_the_trace(ask_agent, api_after):
    script = [s4.run(), h.say_text("Then I would use the 180.")]
    ask_agent(script, ["No, spending is really 180", "/quit"])
    _, body = api_after.get(f"/api/work/conversation?session={h.SESSION}")
    [reply] = events_of(body, "ask.reply")
    assert counted(reply) == [("180", "person", None)]


def test_the_words_of_a_request_answer_are_still_the_persons_for_the_trace(talk, installed, api_after):
    talk([h.request_module("new"), h.say_text("Then it is 4,321.")], ["no, I would rather pay 4,321", "/quit"])
    _, body = api_after.get(f"/api/work/conversation?session={h.SESSION}")
    [reply] = events_of(body, "ask.reply")
    assert counted(reply) == [("4,321", "person", None)]


def test_a_refused_decision_shows_in_the_conversation(ask_agent, api_after):
    ask_agent([s4.ask_decision(question=""), h.say_text("Hello.")], ["/quit"])
    _, body = api_after.get(f"/api/work/conversation?session={h.SESSION}")
    [refused] = events_of(body, "ask.decision_refused")
    assert refused["actor"] == "harness" and refused["numbers"] is None and refused["payload"]["error"] == s4.DECISION_NO_QUESTION


def test_a_decision_block_with_an_unbacked_number_is_a_correction_of_a_tool_not_a_traced_text(ask_agent, api_after):
    ask_agent([s4.ask_decision(question="Put 4,321 aside?"), h.say_text("Hello.")], ["/quit"])
    _, body = api_after.get(f"/api/work/conversation?session={h.SESSION}")
    [correction] = events_of(body, "ask.correction")
    assert correction["payload"]["reason"] == "ask_decision" and correction["numbers"] is None


# ---- the decisions, newest first ------------------------------------------------------------------------------------------------------

def test_the_decisions_are_the_events_of_the_kind_newest_first(story, api):
    status, body = api.get("/api/work/events?kind=ask.decision")
    assert status == 200 and list(body) == ["events", "more"] and body["more"] is False
    assert [e["payload"]["id"] for e in body["events"]] == [2, 1]
    assert [e["payload"]["kind"] for e in body["events"]] == ["judgment", "assumptions"]
    assert all(e["kind"] == "ask.decision" and e["actor"] == "person" and e["session_id"] == CHAT for e in body["events"])
    assert [e["id"] for e in body["events"]] == sorted((e["id"] for e in body["events"]), reverse=True)


def test_each_payload_is_the_decision_of_the_record(story, api, conn):
    _, body = api.get("/api/work/events?kind=ask.decision")
    records = {d["id"]: d for d in s4.decisions_of(conn)}
    for event in body["events"]:
        record = records[event["payload"]["id"]]
        assert event["payload"] == {key: record[key] for key in DECISION_EVENT_KEYS}


def test_the_judgment_has_its_options_and_the_runs_it_rested_on(story, api):
    _, body = api.get("/api/work/events?kind=ask.decision")
    judgment = body["events"][0]["payload"]
    assert judgment["options"] == ["Set aside all of 2,000", "Set aside the bonus of 1,200"]
    assert judgment["runs"] == [1] and judgment["question"].startswith("Only you can decide this. It is step s2 of the plan")


def test_the_decisions_of_one_session_and_the_limit_and_paging(story, api):
    _, body = api.get(f"/api/work/events?kind=ask.decision&session={CHAT}")
    assert len(body["events"]) == 2
    _, body = api.get("/api/work/events?kind=ask.decision&limit=1")
    assert len(body["events"]) == 1 and body["more"] is True and body["events"][0]["payload"]["id"] == 2
    _, rest = api.get(f"/api/work/events?kind=ask.decision&before={body['events'][-1]['id']}")
    assert [e["payload"]["id"] for e in rest["events"]] == [1] and rest["more"] is False
    _, none = api.get("/api/work/events?kind=ask.decision&session=nobody")
    assert none == {"events": [], "more": False}


def test_the_side_conversation_events_by_prefix(story, api):
    _, body = api.get("/api/work/events?kind=aside.")
    assert [e["kind"] for e in body["events"]] == ["aside.closed", "aside.reply", "aside.message", "aside.opened"]


def test_the_new_kinds_are_in_the_kinds_of_the_summary(story, api):
    _, summary = api.get("/api/work/summary")
    for kind in ("ask.gate", "ask.decision", "ask.decision_asked", "aside.opened", "aside.message", "aside.reply",
                 "aside.closed"):
        assert kind in summary["kinds"]
    assert summary["kinds"] == sorted(summary["kinds"])


def test_the_conversation_counts_of_the_summary_do_not_count_the_side_conversation(story, api):
    _, summary = api.get("/api/work/summary")
    [conversation] = [c for c in summary["conversations"] if c["session_id"] == CHAT]
    assert conversation["messages"] == 1 and conversation["replies"] == 1 and conversation["corrections"] == 0
    assert conversation["runs"] == 1 and conversation["withheld"] == 0


def test_the_session_list_counts_the_new_events(story, api, conn):
    _, summary = api.get("/api/work/summary")
    [session] = [s for s in summary["sessions"] if s["session_id"] == CHAT]
    assert session["events"] == conn.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (CHAT,)).fetchone()[0]


# ---- no new path and no new key ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/api/work/decisions", "/api/work/asides", "/api/work/decision?id=1",
                                  "/api/work/aside?id=1"])
def test_no_path_was_added(story, api, path):
    reply = api.sender("GET", path)
    assert reply.status == 404


def test_the_summary_has_the_keys_it_had(story, api):
    _, summary = api.get("/api/work/summary")
    assert list(summary) == ["interview", "database", "brief", "process", "modules", "conversations", "runs", "sessions", "kinds"]


def test_asking_records_nothing(story, api, conn):
    before = len(h.events(conn)), len(s4.decision_rows(conn))
    api.get(f"/api/work/conversation?session={CHAT}")
    api.get("/api/work/events?kind=ask.decision")
    assert (len(h.events(conn)), len(s4.decision_rows(conn))) == before
