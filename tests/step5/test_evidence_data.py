"""SPEC 7.3, 7.4 and 9.9: what the evidence API gains: three summary keys, `data_summary`, and the traced finding block,
through a real server."""
import json

import pytest

import step5_helpers as s5
from step5_helpers import DATA_BLOCK, MESSAGE, ask_finding, entry, h, report, summary_call

OK = "Noted."
SUMMARY_ITEM_KEYS = ["id", "ts", "session_id", "measure", "account", "value"]
DATA_SUMMARY_KEYS = ["id", "ts", "session_id", "inputs", "output", "imports", "findings"]


@pytest.fixture
def story(talk, conn, example_loaded):
    """The conversation of 9.7: a finding put to the person, who keeps what they said (so a figure of the summary is shown
    in the block and nowhere else)."""
    return talk([summary_call(), report(entry()), ask_finding(1), h.say_text(OK)], ["1", "/quit"])


def summary_of(api):
    status, body = api.get("/api/work/summary")
    assert status == 200
    return body


# ---- the summary keys --------------------------------------------------------------------------------------------------------

def test_the_summary_has_the_new_keys_after_the_old_ones(api):
    body = summary_of(api)
    keys = list(body)
    assert keys[-3:] == ["imports", "summaries", "findings"] and keys[:2] == ["interview", "database"]
    assert body["imports"] == body["summaries"] == body["findings"] == []


def test_imports_are_the_payloads_of_the_events_newest_first_with_loaded_now(api, conn, example_loaded):
    body = summary_of(api)
    events = s5.payloads(conn, "data.imported")
    assert len(body["imports"]) == 3
    assert [{k: v for k, v in item.items() if k != "loaded_now"} for item in body["imports"]] == events[::-1]
    assert all(list(item)[-1] == "loaded_now" and item["loaded_now"] is True for item in body["imports"])
    assert [item["id"] for item in body["imports"]] == [3, 2, 1]


def test_what_data_clear_removed_is_still_listed_but_not_loaded_now(api, adapter, conn, example_loaded):
    adapter.clear_data(conn, session_id="C")
    body = summary_of(api)
    assert [item["id"] for item in body["imports"]] == [3, 2, 1] and not any(i["loaded_now"] for i in body["imports"])
    assert all(len(item["dropped"]) >= 0 and item["file"] for item in body["imports"])


def test_a_file_loaded_again_after_a_clear_is_loaded_now_by_its_new_id(api, adapter, conn, example_loaded):
    adapter.clear_data(conn, session_id="C")
    s5.load_example(adapter, conn, which=("savings_2026.csv",))
    imports = summary_of(api)["imports"]
    assert [(i["file"].split("/")[-1], i["loaded_now"]) for i in imports] == [
        ("savings_2026.csv", True), ("card_2026.csv", False), ("savings_2026.csv", False), ("checking_2026.csv", False)]


def test_summaries_are_the_rows_newest_first(api, summaries, conn, example_loaded):
    summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 3}, session_id="a")
    summaries.run_summary(conn, {"measure": "balance", "account": "checking_2026"}, session_id="b")
    rows = summary_of(api)["summaries"]
    assert [list(r) for r in rows] == [SUMMARY_ITEM_KEYS] * 2
    stored = {r["id"]: r for r in s5.summary_rows(conn)}
    assert [r["id"] for r in rows] == [2, 1]
    assert (rows[1]["measure"], rows[1]["account"], rows[1]["value"], rows[1]["session_id"]) == (
        "money_out", "all", "4132.31", "a")
    assert (rows[0]["measure"], rows[0]["account"], rows[0]["session_id"]) == ("balance", "checking_2026", "b")
    assert rows[0]["value"] == json.loads(stored[2]["output"])["value"] and rows[0]["ts"] == stored[2]["ts"]


def test_findings_are_those_of_every_conversation_newest_first(api, story, findings, conn):
    findings.open_finding(conn, session_id="another", kind="brief", claim="x 1,400", claim_figure="1,400",
                          reference="y 1,150", reference_figure="1,150", difference="d")
    body = summary_of(api)
    assert body["findings"] == findings.list_findings(conn)[::-1]
    assert [f["id"] for f in body["findings"]] == [2, 1] and list(body["findings"][0]) == s5.FINDING_KEYS


def test_the_story_is_in_the_conversations_and_the_summaries(api, story):
    body = summary_of(api)
    [conversation] = body["conversations"]
    assert conversation["session_id"] == s5.SESSION and conversation["first_message"] == MESSAGE
    assert [s["measure"] for s in body["summaries"]] == ["money_out"]
    assert "finding.opened" in body["kinds"] and "verify.report" in body["kinds"] and "data.summary" in body["kinds"]


# ---- data_summary ------------------------------------------------------------------------------------------------------------------------

def test_one_summary(api, story, conn):
    status, body = api.get("/api/work/data_summary?id=1")
    row = s5.summary_rows(conn)[0]
    assert status == 200 and list(body) == DATA_SUMMARY_KEYS
    assert body == {"id": 1, "ts": row["ts"], "session_id": s5.SESSION, "inputs": json.loads(row["inputs"]),
                    "output": json.loads(row["output"]), "imports": json.loads(row["imports"]), "findings": [1]}
    assert body["inputs"] == {"measure": "money_out", "account": "all", "months": 3}
    assert body["output"]["value"] == "4132.31" and body["imports"] == [1, 2, 3]


def test_the_findings_of_a_summary_are_those_that_cite_it_by_id(api, story, summaries, findings, conn):
    summaries.run_summary(conn, {"measure": "net", "account": "all", "months": 3}, session_id=s5.SESSION)
    for claim in ("x 1,401", "x 1,402"):
        findings.open_finding(conn, session_id=s5.SESSION, kind="data", claim=claim, claim_figure=claim[2:],
                              reference="r", reference_figure="9", summary_id=1, difference="d")
    findings.open_finding(conn, session_id=s5.SESSION, kind="brief", claim="x 1,403", claim_figure="1,403", reference="r 1",
                          reference_figure="1", difference="d")
    assert api.get("/api/work/data_summary?id=1")[1]["findings"] == [1, 2, 3]
    assert api.get("/api/work/data_summary?id=2")[1]["findings"] == []


@pytest.mark.parametrize("value", ["abc", "1.5", "-", "1e2", " "])
def test_an_id_that_is_not_a_whole_number_is_400(api, value):
    reply = api.sender("GET", f"/api/work/data_summary?id={value}")
    assert reply.status == 400 and reply.json() == {"error": "id must be a whole number"}


def test_a_missing_id_is_400(api):
    assert api.sender("GET", "/api/work/data_summary").status == 400
    assert api.sender("GET", "/api/work/data_summary?id=").status == 400


@pytest.mark.parametrize("value", ["99", "0"])
def test_an_unknown_summary_is_404(api, story, value):
    reply = api.sender("GET", f"/api/work/data_summary?id={value}")
    assert reply.status == 404 and reply.json() == {"error": f"there is no data summary {value}"}


def test_it_needs_the_token(api, story):
    assert api.sender("GET", "/api/work/data_summary?id=1", token=None).status == 403
    assert api.sender("GET", "/api/work/data_summary?id=1", token="wrong").status == 403


def test_a_post_to_it_is_404(api, story):
    assert api.sender("POST", "/api/work/data_summary", {"id": 1}).status == 404


def test_the_function_gives_the_body_of_the_endpoint(evidence, api, story, conn):
    body = evidence.data_summary(conn, 1)
    assert body == api.get("/api/work/data_summary?id=1")[1]
    assert evidence.data_summary(conn, 99) is None


def test_reading_records_nothing(api, story, conn):
    before = len(h.events(conn))
    api.get("/api/work/summary")
    api.get("/api/work/data_summary?id=1")
    api.get(f"/api/work/conversation?session={s5.SESSION}")
    assert len(h.events(conn)) == before


# ---- the finding block, traced -------------------------------------------------------------------------------------------------------------

def block_event(api):
    status, body = api.get(f"/api/work/conversation?session={s5.SESSION}")
    assert status == 200
    [event] = [e for e in body["events"] if e["kind"] == "ask.decision_asked"]
    return event


def test_the_block_of_a_finding_is_traced_like_a_decision_block(api, story):
    event = block_event(api)
    assert event["payload"]["block"] == DATA_BLOCK and isinstance(event["numbers"], list)
    for item in event["numbers"]:
        assert DATA_BLOCK[item["start"]:item["end"]] == item["text"]


def test_every_figure_of_the_block_has_a_source(api, story):
    assert [i["text"] for i in block_event(api)["numbers"] if i["source"] == "none"] == []


def test_a_figure_of_the_summary_shows_as_data_with_the_id_of_the_summary(api, story):
    items = [i for i in block_event(api)["numbers"] if i["text"] == "4132.31"]
    assert items and all((i["source"], i["run_id"]) == ("data", 1) for i in items)


def test_the_figure_the_person_said_has_a_source(api, story):
    """`5k` is backed by the person's message, and also by a month of the summary: `data` comes first (7.1)."""
    items = [i for i in block_event(api)["numbers"] if i["text"] == "5k"]
    assert len(items) == 2 and all(i["source"] in ("data", "person") for i in items)


def test_the_figure_of_the_difference_sentence_is_data_too(api, story):
    items = [i for i in block_event(api)["numbers"] if i["text"] == "4,132.31"]
    assert items and all((i["source"], i["run_id"]) == ("data", 1) for i in items)


def test_a_brief_block_shows_the_figure_of_the_brief_as_brief(talk, api, conn, save_confirmed_brief):
    save_confirmed_brief()
    talk([report(s5.brief_entry()), ask_finding(1), h.say_text(OK)], ["1", "/quit"], question=s5.RENT_MESSAGE)
    items = block_event(api)["numbers"]
    assert {(i["text"], i["source"]) for i in items if i["text"] == "1,150"} == {("1,150", "brief")}
    assert {(i["text"], i["source"]) for i in items if i["text"] == "1,400"} == {("1,400", "person")}


def test_the_decision_of_a_finding_is_among_the_decisions(api, story):
    status, body = api.get("/api/work/events?kind=ask.decision")
    assert status == 200 and [e["payload"]["kind"] for e in body["events"]] == ["finding"]
    assert body["events"][0]["payload"]["question"] == DATA_BLOCK


def test_the_events_of_the_check_are_in_the_conversation(api, story):
    _, body = api.get(f"/api/work/conversation?session={s5.SESSION}")
    kinds = [e["kind"] for e in body["events"]]
    kinds = kinds[kinds.index("ask.started"):]
    assert kinds[:7] == ["ask.started", "ask.message", "data.summary", "verify.report", "finding.opened",
                         "ask.decision_asked", "ask.decision"]
    assert all(e["numbers"] is None for e in body["events"] if e["kind"] in ("data.summary", "verify.report",
                                                                            "finding.opened", "finding.closed"))
