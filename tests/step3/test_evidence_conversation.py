"""SPEC 7.3 and 7.4: `GET /api/work/conversation`, one conversation as it happened, with its numbers traced."""
import json

import pytest

import step3_helpers as s3
from step3_evidence_helpers import (CONVERSATION_EVENT_KEYS, CONVERSATION_KEYS, TRACE_KEYS, add_session, events_where,
                                    event_of)
from step3_helpers import CHAT1, CHAT2, REPLAY, BUILD, ADOPT, h, traced


def get(api, session):
    return api.get(f"/api/work/conversation?session={session}")


def numbers_by_id(body):
    return {e["id"]: e["numbers"] for e in body["events"]}


# ---- the shape -----------------------------------------------------------------------------------------------------

def test_the_keys_of_a_conversation(api):
    status, body = get(api, CHAT1)
    assert status == 200 and list(body) == CONVERSATION_KEYS and body["session_id"] == CHAT1


def test_every_event_of_the_session_oldest_first_with_no_session_id_of_its_own(api, world):
    for session in (CHAT1, CHAT2, REPLAY):
        _, body = get(api, session)
        stored = events_where(world, "session_id = ?", (session,))
        assert [e["id"] for e in body["events"]] == [e["id"] for e in stored]
        for shown, row in zip(body["events"], stored):
            assert list(shown) == CONVERSATION_EVENT_KEYS
            assert {key: shown[key] for key in ("id", "ts", "kind", "actor", "payload")} == {
                key: row[key] for key in ("id", "ts", "kind", "actor", "payload")}


def test_the_build_inside_a_conversation_is_among_its_events(api):
    _, body = get(api, CHAT2)
    kinds = [e["kind"] for e in body["events"]]
    assert "calc.step_added" in kinds and "calc.module_registered" in kinds and "calc.golden_decision" in kinds
    assert [e["id"] for e in body["events"]] == list(range(26, 44))


def test_the_date_of_the_conversation_is_its_ask_started(api):
    assert get(api, CHAT1)[1]["today"] == "2026-03-14"
    assert get(api, CHAT2)[1]["today"] == "2026-04-02"
    assert get(api, REPLAY)[1]["today"] == "2026-05-05"


def test_a_replay_conversation_says_which_scenario(api):
    assert get(api, REPLAY)[1]["replay"] == {"example": "savings", "scenario": "first_look"}
    assert get(api, CHAT1)[1]["replay"] is None


def test_the_function_gives_the_same_body(api, world, evidence):
    from harness import db
    conn = db.connect()
    try:
        assert json.loads(json.dumps(evidence.conversation(conn, CHAT1))) == get(api, CHAT1)[1]
        assert evidence.conversation(conn, "nope") is None
        assert evidence.conversation(conn, BUILD) is None
    finally:
        conn.close()


def test_asking_records_nothing(api, world):
    before = world.counts()
    get(api, CHAT1)
    assert world.counts() == before


# ---- which events have numbers ------------------------------------------------------------------------------------------

def test_only_replies_withheld_texts_corrections_and_requests_are_traced(api):
    _, body = get(api, CHAT1)
    numbers = numbers_by_id(body)
    traced_ids = {event["id"] for event in body["events"] if event["numbers"] is not None}
    assert traced_ids == {22, 23, 25}
    assert [e["kind"] for e in body["events"] if e["id"] in traced_ids] == ["ask.correction", "ask.withheld", "ask.reply"]
    assert numbers[16] is None and numbers[18] is None and numbers[21] is None and numbers[24] is None


def test_the_numbers_of_a_reply(api):
    _, body = get(api, CHAT1)
    reply = next(e for e in body["events"] if e["id"] == 25)
    assert reply["numbers"] == traced(s3.GOOD_REPLY, s3.GOOD_REPLY_NUMBERS)
    assert all(list(item) == TRACE_KEYS for item in reply["numbers"])
    for item in reply["numbers"]:
        assert s3.GOOD_REPLY[item["start"]:item["end"]] == item["text"]


def test_every_source_label_has_a_reply_in_the_story(api):
    _, body = get(api, CHAT1)
    reply = next(e for e in body["events"] if e["id"] == 25)
    assert {item["source"] for item in reply["numbers"]} == {"run", "input", "note", "brief", "person", "today", "small"}


def test_the_run_of_a_number_is_the_latest_that_backs_it(api):
    _, body = get(api, CHAT1)
    items = {(item["text"], item["start"]): item for item in next(e for e in body["events"] if e["id"] == 25)["numbers"]}
    by_text = [(i["text"], i["source"], i["run_id"]) for i in items.values()]
    assert ("2,000", "run", 2) in by_text and ("5,000", "run", 1) in by_text and ("3,000", "run", 1) in by_text


def test_a_withheld_text_is_traced_and_its_unbacked_number_is_none(api):
    _, body = get(api, CHAT1)
    withheld = next(e for e in body["events"] if e["id"] == 23)
    assert withheld["kind"] == "ask.withheld"
    assert withheld["numbers"] == [{"text": "2,600", "start": 8, "end": 13, "source": "none", "run_id": None}]


def test_a_correction_for_a_reply_is_traced(api):
    _, body = get(api, CHAT1)
    correction = next(e for e in body["events"] if e["id"] == 22)
    assert correction["numbers"] == [{"text": "2,500", "start": 14, "end": 19, "source": "none", "run_id": None}]


def test_the_request_block_of_a_module_request_is_traced(api):
    _, body = get(api, CHAT2)
    request = next(e for e in body["events"] if e["kind"] == "ask.module_requested")
    text = request["payload"]["request"]
    assert request["numbers"] == traced(text, [("250", "person", None)])
    assert all(text[item["start"]:item["end"]] == item["text"] for item in request["numbers"])


def test_a_reply_after_a_run_in_the_same_conversation(api):
    _, body = get(api, CHAT2)
    reply = next(e for e in body["events"] if e["kind"] == "ask.reply")
    assert reply["numbers"] == traced(reply["payload"]["text"], [("3,000", "run", 3), ("250", "run", 3)])


def test_the_reply_of_a_replay_conversation(api):
    _, body = get(api, REPLAY)
    reply = next(e for e in body["events"] if e["kind"] == "ask.reply")
    assert reply["numbers"] == traced(s3.Q3_REPLY, [("500", "run", 4)])


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


def test_a_run_of_the_session_before_the_reply_backs_a_number(probe):
    body = probe(message("hello"), ran(77, {"x": "8000"}, "123456"), reply("It is 123,456 from 8,000."))
    assert labels(body) == [("123,456", "run", 77), ("8,000", "run", 77)]


def test_a_run_after_the_reply_does_not(probe):
    body = probe(message("hello"), reply("It is 123,456."), ran(77, {"x": "8000"}, "123456"))
    assert labels(body, 1) == [("123,456", "none", None)]


def test_a_run_of_another_session_does_not(probe):
    body = probe(message("hello"), reply("You keep 2,000 and 450 is saved."))
    assert [(t, s) for t, s, _ in labels(body)] == [("2,000", "none"), ("450", "input")]     # the story's run is in chat-1 only


def test_the_latest_run_that_backs_the_number_is_the_one_named(probe):
    body = probe(message("hello"), ran(11, {"x": "5555"}, "1"), ran(12, {"x": "5555"}, "2"), ran(13, {"x": "6"}, "1"),
                 reply("Using 5,555."))
    assert labels(body) == [("5,555", "run", 12)]


def test_an_output_backs_a_number_as_well(probe):
    body = probe(message("hello"), ran(31, {"x": "1"}, "9999.99"), reply("That is 9,999.99, or about 9,998."))
    assert labels(body) == [("9,999.99", "run", 31), ("9,998", "none", None)]


def test_a_number_within_half_the_precision_is_backed(probe):
    body = probe(message("hello"), ran(5, {"x": "1"}, "4583.33"), reply("About 4,583, or 4,583.33, or 4,584."))
    assert labels(body) == [("4,583", "run", 5), ("4,583.33", "run", 5), ("4,584", "none", None)]


def test_a_saved_input_of_another_session_before_the_reply_is_an_input(probe):
    body = probe(message("hello"), reply("You said 450."))
    assert labels(body) == [("450", "input", None)]


def test_a_saved_input_after_the_reply_is_not(probe):
    body = probe(message("hello"), reply("It is 7,777."), ("ask.input_saved", {"name": "x", "value": "7777", "note": "n"}, "agent"))
    assert labels(body, 1) == [("7,777", "none", None)]


def test_a_saved_input_of_this_session_counts_as_well(probe):
    body = probe(message("hello"), ("ask.input_saved", {"name": "x", "value": "7777", "note": "n"}, "agent"), reply("It is 7,777."))
    assert labels(body) == [("7,777", "input", None)]


def test_the_value_of_a_saved_input_may_be_a_number_not_text(probe):
    body = probe(message("hello"), ("ask.input_saved", {"name": "x", "value": 8123, "note": "n"}, "agent"), reply("It is 8,123."))
    assert labels(body) == [("8,123", "input", None)]


def test_a_note_of_any_session_is_a_note(probe):
    body = probe(message("hello"), reply("The car costs 700."))
    assert labels(body) == [("700", "note", None)]


def test_a_note_saved_later_is_not(probe):
    body = probe(message("hello"), reply("About 8,642."), ("calc.note_saved", {"id": 9, "step": "s1", "text": "8642 maybe"}, "person"))
    assert labels(body, 1) == [("8,642", "none", None)]


def test_a_note_saved_before_counts(probe):
    body = probe(("calc.note_saved", {"id": 9, "step": "s1", "text": "rent is 8642"}, "person"), message("hello"), reply("About 8,642."))
    assert labels(body) == [("8,642", "note", None)]


def test_the_brief_is_a_source(probe):
    body = probe(message("hello"), reply("The rent is 1,150."))
    assert labels(body) == [("1,150", "brief", None)]


def test_the_brief_is_read_now_not_as_it_was(probe, world):
    path = world.brief_dir / "domain_brief.json"
    path.write_text(path.read_text(encoding="utf-8").replace("1,150", "1,300"), encoding="utf-8")
    body = probe(message("hello"), reply("The rent is 1,150, not 1,300."))
    assert labels(body) == [("1,150", "none", None), ("1,300", "brief", None)]


def test_without_a_brief_there_is_no_brief_source(probe, world):
    (world.brief_dir / "domain_brief.json").unlink()
    body = probe(message("hello"), reply("The rent is 1,150."))
    assert labels(body) == [("1,150", "none", None)]


def test_a_message_of_the_person_in_the_session_is_a_source(probe):
    body = probe(message("I pay 9,876 for the flat"), reply("Your 9,876 is noted."))
    assert labels(body) == [("9,876", "person", None)]


def test_a_message_of_another_session_is_not(probe):
    body = probe(message("hello"), reply("You owe 900."))
    assert labels(body) == [("900", "none", None)]


def test_a_message_after_the_reply_is_not(probe):
    body = probe(message("hello"), reply("You owe 9,876."), message("I owe 9,876"))
    assert labels(body, 1) == [("9,876", "none", None)]


def test_the_text_of_a_module_decision_is_what_the_person_said(probe):
    body = probe(message("hello"), ("ask.module_decision", {"decision": "accepted", "text": "yes, with 6543"}, "person"),
                 reply("About 6,543."))
    assert labels(body) == [("6,543", "person", None)]


def test_the_date_of_the_conversation_is_a_source(probe):
    body = probe(started("2031-07-22"), message("hello"), reply("It is 2031-07-22 today."))
    assert labels(body) == [("2031-07-22", "today", None)]


def test_a_date_other_than_the_conversations_is_none(probe):
    body = probe(started("2031-07-22"), message("hello"), reply("Not 2031-07-23."))
    assert labels(body) == [("2031-07-23", "none", None)]


def test_without_ask_started_the_date_of_the_conversation_is_the_first_event_date(probe, world):
    body = probe(message("hello"), reply("hi"))
    first = world.sql("SELECT ts FROM events WHERE session_id = ? ORDER BY id LIMIT 1", (probe.session,))[0]["ts"]
    assert body["today"] == first[:10] and len(body["today"]) == 10


def test_a_conversation_whose_first_event_is_not_ask_started_still_uses_a_later_ask_started(probe):
    body = probe(message("hello"), started("2031-07-22"), reply("Today is 2031-07-22."))
    assert body["today"] == "2031-07-22"


# ---- the order of the labels -----------------------------------------------------------------------------------------------

LABEL_ORDER = [
    ("run beats input", [ran(81, {"x": "4321"}, "1"), ("ask.input_saved", {"name": "n", "value": "4321", "note": ""}, "agent")], "run", 81),
    ("run beats person", [ran(82, {"x": "4321"}, "1"), message("it is 4321")], "run", 82),
    ("input beats note", [("ask.input_saved", {"name": "n", "value": "4321", "note": ""}, "agent"),
                           ("calc.note_saved", {"id": 9, "step": "s1", "text": "4321"}, "person")], "input", None),
    ("note beats person", [("calc.note_saved", {"id": 9, "step": "s1", "text": "4321"}, "person"), message("4321")], "note", None),
    ("person alone", [message("it is 4321")], "person", None),
]


@pytest.mark.parametrize("name, before, source, run_id", LABEL_ORDER, ids=[c[0] for c in LABEL_ORDER])
def test_the_first_label_in_the_fixed_order_wins(probe, name, before, source, run_id):
    body = probe(message("hello"), *before, reply("It is 4,321."))
    assert labels(body) == [("4,321", source, run_id)]


def test_the_brief_comes_before_the_person_and_after_the_note(probe, world):
    path = world.brief_dir / "domain_brief.json"
    path.write_text(path.read_text(encoding="utf-8").replace("1,150", "4321"), encoding="utf-8")
    body = probe(message("it is 4321"), reply("It is 4,321."))
    assert labels(body) == [("4,321", "brief", None)]
    body = probe(("calc.note_saved", {"id": 9, "step": "s1", "text": "4321"}, "person"), message("it is 4321"), reply("It is 4,321."))
    assert labels(body) == [("4,321", "note", None)]


def test_the_person_comes_before_today(probe):
    body = probe(started("2031-07-22"), message("hello 2031"), reply("In 2031 and on 2031-07-22."))
    assert labels(body)[0] == ("2031", "person", None)
    assert labels(body)[1] == ("2031-07-22", "today", None)


# ---- small numbers -----------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["0", "1", "3", "7", "12"])
def test_a_bare_whole_number_up_to_12_is_small_whatever_the_sources(probe, text):
    body = probe(message("hello"), reply(f"There are {text} of them."))
    assert labels(body) == [(text, "small", None)]


def test_a_small_number_is_small_even_when_a_source_backs_it(probe):
    body = probe(message("I have 3 children"), reply("For your 3 children."))
    assert labels(body) == [("3", "small", None)]


@pytest.mark.parametrize("text", ["13", "12.5", "3.0", "€7", "7k"])
def test_a_number_that_is_not_a_bare_whole_number_up_to_12_needs_a_source(probe, text):
    body = probe(message("hello"), reply(f"It is {text} now."))
    assert [source for _, source, _ in labels(body)] == ["none"]


# ---- k and % --------------------------------------------------------------------------------------------------------------------------

def test_a_percentage_is_backed_by_the_value_divided_by_100(probe):
    body = probe(message("the rate is 0.375"), reply("That is 37.5%."))
    assert labels(body) == [("37.5%", "person", None)]


def test_a_number_with_k_is_read_as_thousands(probe):
    body = probe(message("I earn 5000"), reply("Your 5k is a lot."))
    assert labels(body) == [("5k", "person", None)]


def test_the_currency_sign_is_part_of_the_text_of_the_item(probe):
    body = probe(message("I earn 5000"), reply("Your $5,000 is a lot."))
    assert labels(body) == [("$5,000", "person", None)]
    assert "Your $5,000 is a lot."[body["events"][-1]["numbers"][0]["start"]] == "$"


# ---- dates ---------------------------------------------------------------------------------------------------------------------------------

def test_a_date_is_only_as_backed_as_its_least_backed_part(probe):
    body = probe(started("2031-07-22"), message("in 2031"), reply("On 2031-07-22 or 2031-07-23."))
    assert labels(body) == [("2031-07-22", "today", None), ("2031-07-23", "none", None)]


def test_a_date_takes_the_run_of_its_first_part_with_the_last_label(probe):
    body = probe(message("hello"), ran(91, {"year": "2031"}, "1"), ran(92, {"day": "22"}, "1"), reply("On 2031-07-22."))
    assert labels(body) == [("2031-07-22", "run", 91)]


def test_a_date_whose_parts_are_labelled_differently_takes_the_later_label(probe):
    body = probe(message("hello"), ran(91, {"year": "2031"}, "1"), ("ask.input_saved", {"name": "d", "value": "22", "note": ""}, "agent"),
                 reply("On 2031-07-22."))
    assert labels(body) == [("2031-07-22", "input", None)]


def test_the_parts_of_a_date_that_are_12_or_below_are_not_looked_at(probe):
    body = probe(message("hello"), ran(91, {"year": "2031", "day": "22"}, "1"), reply("On 2031-07-22 and 2031-05-22."))
    assert labels(body) == [("2031-07-22", "run", 91), ("2031-05-22", "run", 91)]


# ---- every occurrence, in order, with places counted in code points ----------------------------------------------------------------------

def test_every_occurrence_is_an_item_in_order_of_appearance(probe):
    body = probe(message("hello"), ran(5, {"x": "2500"}, "2500"), reply("2,500 then 2,500 and again 2,500."))
    items = body["events"][-1]["numbers"]
    assert [i["text"] for i in items] == ["2,500", "2,500", "2,500"]
    assert [i["start"] for i in items] == sorted(i["start"] for i in items) and len({i["start"] for i in items}) == 3


def test_a_place_counts_code_points_not_bytes_or_utf16_units(probe):
    text = "Voilà 😀😀 café: 9,431 et 😀 8,642."
    body = probe(message("hello"), ran(5, {"x": "9431"}, "1"), reply(text))
    items = body["events"][-1]["numbers"]
    assert [(i["text"], i["source"]) for i in items] == [("9,431", "run"), ("8,642", "none")]
    for item in items:
        assert text[item["start"]:item["end"]] == item["text"]
    assert items[0]["start"] == len("Voilà 😀😀 café: ")


def test_a_reply_with_no_numbers_has_an_empty_list_not_null(probe):
    body = probe(message("hello"), reply("Nothing to count here."))
    assert body["events"][-1]["numbers"] == []


# ---- the other traced kinds, in sessions made for the purpose ----------------------------------------------------------------------------------

def test_a_withheld_text_uses_the_sources_before_it(probe):
    body = probe(message("hello"), ran(5, {"x": "2500"}, "1"), ("ask.withheld", {"numbers": ["2,600"], "text": "2,500 or 2,600"}, "harness"))
    assert labels(body) == [("2,500", "run", 5), ("2,600", "none", None)]


def test_a_correction_for_a_reply_is_traced_but_one_for_a_tool_call_is_not(probe):
    body = probe(message("hello"), ("ask.correction", {"reason": "reply", "numbers": ["2,600"], "text": "It is 2,600"}, "harness"),
                 ("ask.correction", {"reason": "run_module", "numbers": ["2,600"], "text": "{\"x\": \"2,600\"}"}, "harness"),
                 ("ask.correction", {"reason": "save_input", "numbers": ["2,600"], "text": "{\"x\": \"2,600\"}"}, "harness"),
                 ("ask.correction", {"reason": "request_module", "numbers": ["2,600"], "text": "{}"}, "harness"))
    assert [e["numbers"] is not None for e in body["events"]] == [False, True, False, False, False]


def test_a_module_request_is_traced_on_its_request_field(probe):
    request = "The assistant asks to build a calculation.\n  Why now: you said 2,600 once"
    body = probe(message("hello"), ("ask.module_requested", {"arguments": {"why": "9,999"}, "request": request}, "agent"))
    assert body["events"][-1]["numbers"] == traced(request, [("2,600", "none", None)])


def test_other_kinds_are_not_traced_even_when_they_hold_numbers(probe):
    body = probe(message("hello 4,321"), ("ask.module_outcome", {"outcome": "built", "text": "4,321"}, "harness"),
                 ("ask.stopped", {"reason": "4,321"}, "harness"), ("calc.refused", {"module": "m", "reason": "4,321"}, "harness"))
    assert [e["numbers"] for e in body["events"]] == [None, None, None, None]


# ---- errors ---------------------------------------------------------------------------------------------------------------------------------------

def test_a_session_is_required(api):
    reply_ = api.sender("GET", "/api/work/conversation")
    assert reply_.status == 400 and reply_.json() == {"error": "session is required"}


def test_an_empty_session_counts_as_absent(api):
    reply_ = api.sender("GET", "/api/work/conversation?session=")
    assert reply_.status == 400 and reply_.json() == {"error": "session is required"}


def test_an_unknown_session_is_404(api):
    reply_ = api.sender("GET", "/api/work/conversation?session=nope")
    assert reply_.status == 404 and reply_.json() == {"error": "there is no conversation 'nope'"}


@pytest.mark.parametrize("session", [BUILD, ADOPT])
def test_a_session_without_a_message_is_not_a_conversation(api, session):
    reply_ = api.sender("GET", f"/api/work/conversation?session={session}")
    assert reply_.status == 404 and reply_.json() == {"error": f"there is no conversation '{session}'"}


def test_the_session_is_url_decoded(api):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, "a b&c", message("hello"))
    finally:
        conn.close()
    status, body = get(api, "a%20b%26c")
    assert status == 200 and body["session_id"] == "a b&c"
