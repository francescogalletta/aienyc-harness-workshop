"""SPEC 7.4: `GET /api/work/events`, the raw event log, newest first, a page at a time."""
import json
from urllib.parse import quote

import pytest

from step3_evidence_helpers import EVENT_KEYS, add_session, events_where
from step3_helpers import CHAT1, CHAT2

LIMIT_PROBLEM = "limit must be a whole number from 1 to 1000"
BEFORE_PROBLEM = "before must be a whole number"


def page(api, **query):
    path = "/api/work/events"
    if query:
        path += "?" + "&".join(f"{key}={quote(str(value), safe='')}" for key, value in query.items())
    status, body = api.get(path)
    assert status == 200, body
    return body


def ids(body):
    return [e["id"] for e in body["events"]]


@pytest.fixture
def stored(world):
    return events_where(world, newest_first=True)


# ---- the whole log -------------------------------------------------------------------------------------------------------

def test_the_body_holds_events_and_more(api):
    body = page(api)
    assert list(body) == ["events", "more"] and isinstance(body["more"], bool)


def test_the_events_are_newest_first_with_the_event_keys(api, stored):
    body = page(api)
    assert body["events"] == stored and body["more"] is False
    assert all(list(e) == EVENT_KEYS for e in body["events"])
    assert ids(body) == sorted(ids(body), reverse=True)


def test_the_default_limit_is_200(api, world):
    from harness import db
    conn = db.connect()
    try:
        for n in range(200):
            add_session(conn, "bulk", ("ask.message", {"text": f"message {n}"}, "person"))
    finally:
        conn.close()
    body = page(api)
    assert len(body["events"]) == 200 and body["more"] is True
    assert ids(body)[0] == 249 and ids(body)[-1] == 50


def test_the_payload_is_json(api):
    body = page(api, kind="ask.reply", session=CHAT1)
    assert body["events"][0]["payload"]["text"].startswith("You keep 2,000")


# ---- limit and more -------------------------------------------------------------------------------------------------------

def test_a_limit_gives_that_many_and_more(api, stored):
    body = page(api, limit=10)
    assert ids(body) == [e["id"] for e in stored][:10] == list(range(49, 39, -1)) and body["more"] is True


def test_more_is_false_when_the_page_ends_exactly_at_the_oldest(api, stored):
    assert page(api, limit=len(stored))["more"] is False
    assert page(api, limit=len(stored) - 1)["more"] is True
    assert len(page(api, limit=len(stored) + 5)["events"]) == len(stored)


def test_limit_one(api):
    body = page(api, limit=1)
    assert ids(body) == [49] and body["more"] is True


def test_the_largest_limit(api, stored):
    body = page(api, limit=1000)
    assert len(body["events"]) == len(stored) and body["more"] is False


@pytest.mark.parametrize("value", ["0", "1001", "-1", "abc", "1.5", "10x", "99999"])
def test_a_limit_out_of_range_or_not_a_number_is_400(api, value):
    reply = api.sender("GET", f"/api/work/events?limit={value}")
    assert reply.status == 400 and reply.json() == {"error": LIMIT_PROBLEM}


def test_paging_with_before_walks_the_whole_log_once(api, stored):
    seen, before = [], None
    for _ in range(20):
        body = page(api, limit=7, **({} if before is None else {"before": before}))
        seen += ids(body)
        if not body["more"]:
            break
        before = ids(body)[-1]
    assert seen == [e["id"] for e in stored] and len(set(seen)) == len(seen)


def test_before_is_events_with_a_smaller_id(api):
    body = page(api, before=20)
    assert ids(body)[0] == 19 and ids(body)[-1] == 1 and body["more"] is False and len(body["events"]) == 19


def test_before_the_first_event_is_empty(api):
    assert page(api, before=1) == {"events": [], "more": False}
    assert page(api, before=0) == {"events": [], "more": False}


@pytest.mark.parametrize("value", ["abc", "1.5", "x1"])
def test_a_before_that_is_not_a_whole_number_is_400(api, value):
    reply = api.sender("GET", f"/api/work/events?before={value}")
    assert reply.status == 400 and reply.json() == {"error": BEFORE_PROBLEM}


def test_an_empty_value_counts_as_absent(api, stored):
    body = page(api, kind="", session="", before="", limit="")
    assert body["events"] == stored


# ---- filters ----------------------------------------------------------------------------------------------------------------

def test_a_kind_is_exact(api, world):
    body = page(api, kind="ask.reply")
    assert ids(body) == [e["id"] for e in events_where(world, "kind = 'ask.reply'", newest_first=True)] == [49, 43, 25]
    assert {e["kind"] for e in body["events"]} == {"ask.reply"}


def test_an_exact_kind_is_not_a_prefix(api):
    assert page(api, kind="ask") == {"events": [], "more": False}
    assert page(api, kind="ask.rep") == {"events": [], "more": False}
    assert page(api, kind="ask.reply.x") == {"events": [], "more": False}


def test_a_kind_that_ends_with_a_dot_is_a_prefix(api, world):
    body = page(api, kind="ask.")
    expected = events_where(world, "kind LIKE 'ask.%'", newest_first=True)
    assert ids(body) == [e["id"] for e in expected] and len(expected) > 10
    assert all(e["kind"].startswith("ask.") for e in body["events"])


def test_the_prefix_is_the_whole_first_part(api):
    assert {e["kind"].split(".")[0] for e in page(api, kind="calc.")["events"]} == {"calc"}
    assert {e["kind"] for e in page(api, kind="replay.")["events"]} == {"replay.scenario"}


def test_a_prefix_takes_its_characters_literally(api, world):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, "odd", ("xa.one", {}), ("x_.two", {}), ("x%.three", {}), ("zzz.four", {}))
    finally:
        conn.close()
    assert [e["kind"] for e in page(api, kind="x_.")["events"]] == ["x_.two"]
    assert [e["kind"] for e in page(api, kind="x%.")["events"]] == ["x%.three"]
    assert [e["kind"] for e in page(api, kind="%.")["events"]] == []
    assert [e["kind"] for e in page(api, kind="x_.two")["events"]] == ["x_.two"]
    assert page(api, kind="x_.tw_") == {"events": [], "more": False}


def test_a_session_is_exact(api, world):
    body = page(api, session=CHAT2)
    assert ids(body) == list(range(43, 25, -1)) and {e["session_id"] for e in body["events"]} == {CHAT2}
    assert page(api, session="chat") == {"events": [], "more": False}
    assert page(api, session="chat-") == {"events": [], "more": False}


def test_a_kind_and_a_session_together(api):
    body = page(api, kind="calc.", session=CHAT2)
    assert ids(body) == [42, 41, 39, 38, 37, 36, 35, 34, 33, 32, 31, 30]


def test_filters_before_and_limit_together(api):
    body = page(api, kind="calc.run", before=45, limit=2)
    assert ids(body) == [42, 20] and body["more"] is True
    body = page(api, kind="calc.run", before=ids(body)[-1], limit=2)
    assert ids(body) == [18] and body["more"] is False


def test_more_looks_only_at_matching_events(api):
    body = page(api, kind="ask.started", limit=3)
    assert ids(body) == [45, 26, 15] and body["more"] is False


def test_a_filter_with_no_match_is_an_empty_page(api):
    assert page(api, session="nothing-here") == {"events": [], "more": False}


def test_a_value_is_decoded(api, world):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, "a b&c=d", ("ask.message", {"text": "x"}, "person"))
    finally:
        conn.close()
    assert [e["session_id"] for e in page(api, session="a b&c=d")["events"]] == ["a b&c=d"]


# ---- no limit elsewhere / nothing written -----------------------------------------------------------------------------------------

def test_reading_the_log_records_nothing(api, world):
    before = world.counts()
    page(api, limit=5)
    page(api, kind="ask.")
    assert world.counts() == before


def test_the_function_gives_the_same_body(api, world, evidence):
    from harness import db
    conn = db.connect()
    try:
        assert json.loads(json.dumps(evidence.events_page(conn, kind="calc.", session=CHAT2, before=40, limit=4))) == page(
            api, kind="calc.", session=CHAT2, before=40, limit=4)
        assert json.loads(json.dumps(evidence.events_page(conn))) == page(api)
    finally:
        conn.close()
