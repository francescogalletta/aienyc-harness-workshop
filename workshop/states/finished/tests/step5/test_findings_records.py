"""SPEC 9.5: findings: the table, the block, the options, `open_finding`, `close_finding`, `list_findings`."""
import json
from datetime import datetime, timedelta

import pytest

import step5_helpers as s5
from step5_helpers import (BRIEF_BLOCK, CLAIM, DATA_BLOCK, DIFFERENCE, OPTIONS_BRIEF, OPTIONS_DATA, RENT_CLAIM,
                           RENT_DIFFERENCE, RENT_QUOTE, SESSION, SPENDING, SPENDING_WORDS, h, put_months)

EARLIER = {"value": "3,500", "note": "said earlier", "ts": "2026-03-01T09:00:00+00:00", "session_id": "an-earlier-chat"}


@pytest.fixture
def summary_id(summaries, conn):
    """A real data summary of the conversation, so that a finding can point at it."""
    put_months(conn, "main", {"2026-06": ([], ["3613.17"]), "2026-07": ([], ["4658.17"]), "2026-08": ([], ["4125.59"])})
    return summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 3}, session_id=SESSION)["summary"]


def open_data(findings, conn, summary_id, **changes):
    arguments = dict(session_id=SESSION, kind="data", claim=CLAIM, claim_figure="5k", reference=SPENDING_WORDS,
                     reference_figure=SPENDING, summary_id=summary_id, difference=DIFFERENCE)
    arguments.update(changes)
    return findings.open_finding(conn, **arguments)


def open_brief(findings, conn, **changes):
    arguments = dict(session_id=SESSION, kind="brief", claim=RENT_CLAIM, claim_figure="1,400", reference=RENT_QUOTE,
                     reference_figure="1,150", difference=RENT_DIFFERENCE)
    arguments.update(changes)
    return findings.open_finding(conn, **arguments)


def open_earlier(findings, conn, **changes):
    arguments = dict(session_id=SESSION, kind="earlier", claim="4,000", claim_figure="4,000", reference="3,500",
                     reference_figure="3,500", input_name="monthly_spending", earlier=EARLIER, pending_note="said now")
    arguments.update(changes)
    return findings.open_finding(conn, **arguments)


def decide(conn, finding, choice="1", words="1", session_id=SESSION):
    from harness.calc import decisions
    return decisions.record_decision(conn, session_id=session_id, kind="finding", step_id=None, question=finding["block"],
                                     options=finding["options"], choice=choice, words=words, runs=[])


# ---- the finding of kind data ---------------------------------------------------------------------------------------------

def test_a_finding_has_exactly_these_keys_in_this_order(findings, conn, summary_id):
    finding = open_data(findings, conn, summary_id)
    assert list(finding) == s5.FINDING_KEYS


def test_a_data_finding(findings, conn, summary_id):
    finding = open_data(findings, conn, summary_id)
    assert finding["id"] == 1 and finding["session_id"] == SESSION and finding["kind"] == "data"
    assert finding["claim"] == CLAIM and finding["claim_figure"] == "5k"
    assert finding["reference"] == SPENDING_WORDS and finding["reference_figure"] == SPENDING
    assert finding["summary"] == summary_id and finding["input"] is None and finding["earlier"] is None
    assert finding["pending_note"] is None and finding["difference"] == DIFFERENCE
    assert finding["status"] == "open"
    assert finding["decision"] is None and finding["choice"] is None and finding["chosen"] is None
    assert datetime.fromisoformat(finding["ts"]).utcoffset() == timedelta(0)


def test_the_block_of_a_data_finding_is_byte_for_byte_the_example_of_the_spec(findings, conn, summary_id):
    finding = open_data(findings, conn, summary_id)
    assert finding["block"] == "\n".join([
        "Two figures for the same thing differ. Only you can decide which one to use:",
        "  You said: \"I spend about 5k a month\"",
        "  Your loaded files show 4132.31: money out a month, on average over the 3 full months 2026-06 to 2026-08, "
        "all accounts.",
        "  The loaded files show 4,132.31 going out a month on average over the last three full months.",
        "    1. Keep what I said: 5k",
        "    2. Use the figure from my files: 4132.31"])
    assert finding["block"] == DATA_BLOCK


def test_the_options_of_a_data_finding(findings, conn, summary_id):
    assert open_data(findings, conn, summary_id)["options"] == [
        "Keep what I said: 5k", "Use the figure from my files: 4132.31"] == OPTIONS_DATA


def test_every_text_in_the_block_is_made_one_line(findings, conn, summary_id):
    finding = open_data(findings, conn, summary_id, claim="I spend\n  about   5k a month",
                        reference="money out\ta month,  all accounts", difference=" It is\n 4,132.31 \n a month ")
    lines = finding["block"].split("\n")
    assert lines[1] == '  You said: "I spend about 5k a month"'
    assert lines[2] == "  Your loaded files show 4132.31: money out a month, all accounts."
    assert lines[3] == "  It is 4,132.31 a month"


def test_the_block_has_the_indents_of_a_decision_block(findings, conn, summary_id):
    lines = open_data(findings, conn, summary_id)["block"].split("\n")
    assert [len(l) - len(l.lstrip(" ")) for l in lines] == [0, 2, 2, 2, 4, 4]


# ---- the finding of kind brief --------------------------------------------------------------------------------------------

def test_a_brief_finding(findings, conn):
    finding = open_brief(findings, conn)
    assert finding["kind"] == "brief" and finding["claim"] == RENT_CLAIM and finding["claim_figure"] == "1,400"
    assert finding["reference"] == RENT_QUOTE and finding["reference_figure"] == "1,150"
    assert finding["summary"] is None and finding["input"] is None and finding["earlier"] is None
    assert finding["difference"] == RENT_DIFFERENCE and finding["status"] == "open"


def test_the_block_of_a_brief_finding(findings, conn):
    finding = open_brief(findings, conn)
    assert finding["block"] == "\n".join([
        "Two figures for the same thing differ. Only you can decide which one to use:",
        "  You said: \"My rent is 1,400 a month\"",
        "  The brief says: \"Rent is fixed at 1,150 a month\"",
        "  The brief gives the rent as 1,150 a month.",
        "    1. Keep what I said: 1,400",
        "    2. Use the figure in the brief: 1,150"])
    assert finding["block"] == BRIEF_BLOCK


def test_the_options_of_a_brief_finding(findings, conn):
    assert open_brief(findings, conn)["options"] == ["Keep what I said: 1,400", "Use the figure in the brief: 1,150"]
    assert open_brief(findings, conn)["options"] == OPTIONS_BRIEF


# ---- the finding of kind earlier ----------------------------------------------------------------------------------------------

def test_an_earlier_finding(findings, conn):
    finding = open_earlier(findings, conn)
    assert finding["kind"] == "earlier" and finding["claim"] == "4,000" and finding["claim_figure"] == "4,000"
    assert finding["reference"] == "3,500" and finding["reference_figure"] == "3,500"
    assert finding["input"] == "monthly_spending" and finding["earlier"] == EARLIER
    assert finding["pending_note"] == "said now" and finding["summary"] is None and finding["difference"] == ""


def test_the_block_of_an_earlier_finding_from_another_conversation(findings, conn):
    finding = open_earlier(findings, conn)
    assert finding["block"] == "\n".join([
        "Two figures for the same thing differ. Only you can decide which one to use:",
        "  To save now as monthly_spending: 4,000",
        "  Saved earlier (in an earlier conversation) as monthly_spending: 3,500",
        "    1. Use the new value: 4,000",
        "    2. Keep the earlier value: 3,500"])
    assert finding["block"] == s5.finding_block("earlier", claim="4,000", reference="3,500")


def test_the_block_of_an_earlier_finding_from_this_conversation(findings, conn):
    finding = open_earlier(findings, conn, earlier={**EARLIER, "session_id": SESSION})
    assert finding["block"].split("\n")[2] == "  Saved earlier (in this conversation) as monthly_spending: 3,500"


def test_the_options_of_an_earlier_finding(findings, conn):
    assert open_earlier(findings, conn)["options"] == ["Use the new value: 4,000", "Keep the earlier value: 3,500"]


def test_an_earlier_block_is_made_one_line_and_has_no_difference_line(findings, conn):
    finding = open_earlier(findings, conn, claim="deposit   4,000", reference="deposit\n3,500")
    assert finding["block"].split("\n")[1:3] == ["  To save now as monthly_spending: deposit 4,000",
                                                 "  Saved earlier (in an earlier conversation) as monthly_spending: deposit 3,500"]
    assert len(finding["block"].split("\n")) == 5


# ---- open_finding ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["other", "", "DATA", None, "decision"])
def test_a_kind_that_is_not_a_finding_kind_is_a_value_error(findings, conn, kind):
    with pytest.raises(ValueError):
        open_brief(findings, conn, kind=kind)
    assert s5.finding_rows(conn) == []


def test_the_row_in_the_table(findings, conn, summary_id):
    finding = open_data(findings, conn, summary_id)
    [row] = s5.finding_rows(conn)
    assert (row["id"], row["session_id"], row["kind"]) == (1, SESSION, "data")
    assert (row["claim"], row["claim_figure"], row["reference"], row["reference_figure"]) == (
        CLAIM, "5k", SPENDING_WORDS, SPENDING)
    assert row["summary_id"] == summary_id and row["input_name"] is None and row["earlier"] is None
    assert row["pending_note"] is None and row["difference"] == DIFFERENCE and row["block"] == finding["block"]
    assert json.loads(row["options"]) == finding["options"]
    assert (row["status"], row["decision_id"], row["choice"], row["chosen"]) == ("open", None, None, None)
    assert row["ts"] == finding["ts"]


def test_the_earlier_row_keeps_the_saved_row_as_json(findings, conn):
    open_earlier(findings, conn)
    [row] = s5.finding_rows(conn)
    assert json.loads(row["earlier"]) == EARLIER and row["input_name"] == "monthly_spending"
    assert row["pending_note"] == "said now"


def test_finding_opened_is_recorded_with_the_finding(findings, conn, summary_id):
    finding = open_data(findings, conn, summary_id)
    assert s5.events(conn, "finding.opened") == [("finding.opened", "harness", finding)]
    [row] = s5.sql_rows(conn, "SELECT session_id FROM events WHERE kind = 'finding.opened'")
    assert row["session_id"] == SESSION


def test_ids_count_up(findings, conn):
    assert [open_brief(findings, conn)["id"], open_brief(findings, conn)["id"]] == [1, 2]


# ---- close_finding --------------------------------------------------------------------------------------------------------

def close(findings, conn, finding, choice, saved=False, words=None, session_id=SESSION):
    decision = decide(conn, finding, choice=choice, words=words or choice)
    return decision, findings.close_finding(conn, finding["id"], decision_id=decision["id"], choice=choice, saved=saved,
                                            session_id=session_id)


@pytest.mark.parametrize("choice, chosen", [("1", "5000"), ("2", "4132.31"), ("something else", None)])
def test_closing_a_data_finding(findings, conn, summary_id, choice, chosen):
    finding = open_data(findings, conn, summary_id)
    decision, closed = close(findings, conn, finding, choice)
    assert list(closed) == s5.FINDING_KEYS
    assert closed["status"] == "decided" and closed["decision"] == decision["id"]
    assert closed["choice"] == choice and closed["chosen"] == chosen
    assert closed["claim"] == CLAIM and closed["block"] == finding["block"] and closed["options"] == finding["options"]


@pytest.mark.parametrize("choice, chosen", [("1", "1400"), ("2", "1150"), ("something else", None)])
def test_closing_a_brief_finding(findings, conn, choice, chosen):
    _, closed = close(findings, conn, open_brief(findings, conn), choice)
    assert closed["chosen"] == chosen and closed["choice"] == choice


@pytest.mark.parametrize("choice, chosen", [("1", "4,000"), ("2", "3,500"), ("something else", None)])
def test_closing_an_earlier_finding_takes_the_claim_or_the_reference_as_it_is(findings, conn, choice, chosen):
    _, closed = close(findings, conn, open_earlier(findings, conn), choice)
    assert closed["chosen"] == chosen


def test_closing_changes_the_row_once(findings, conn, summary_id):
    finding = open_data(findings, conn, summary_id)
    decision, _ = close(findings, conn, finding, "2")
    [row] = s5.finding_rows(conn)
    assert (row["status"], row["decision_id"], row["choice"], row["chosen"]) == ("decided", decision["id"], "2", SPENDING)
    assert row["claim"] == CLAIM and row["block"] == finding["block"] and row["summary_id"] == summary_id


def test_a_chosen_percentage_or_date_is_written_plain(findings, conn, summary_id):
    finding = open_brief(findings, conn, claim_figure="12%", reference_figure="2026-03-25")
    _, closed = close(findings, conn, finding, "1")
    assert closed["chosen"] == "12%"
    finding = open_brief(findings, conn, claim_figure="12%", reference_figure="2026-03-25")
    _, closed = close(findings, conn, finding, "2")
    assert closed["chosen"] == "2026-03-25"


def test_finding_closed_is_recorded(findings, conn, summary_id):
    finding = open_data(findings, conn, summary_id)
    decision, closed = close(findings, conn, finding, "2", saved=False, session_id="the-chat")
    assert s5.events(conn, "finding.closed") == [("finding.closed", "harness", {
        "finding": finding["id"], "decision": decision["id"], "choice": "2", "chosen": SPENDING, "saved": False})]
    [row] = s5.sql_rows(conn, "SELECT session_id FROM events WHERE kind = 'finding.closed'")
    assert row["session_id"] == "the-chat"


def test_saved_is_passed_on_to_the_event(findings, conn):
    finding = open_earlier(findings, conn)
    close(findings, conn, finding, "1", saved=True)
    assert s5.payloads(conn, "finding.closed")[0]["saved"] is True


# ---- list_findings and open_findings ---------------------------------------------------------------------------------------

def test_nothing_to_list(findings, conn):
    assert findings.list_findings(conn) == [] and findings.list_findings(conn, session_id=SESSION) == []
    assert findings.open_findings(conn, session_id=SESSION) == []


def test_findings_of_one_session_or_of_every_session_oldest_first(findings, conn):
    one = open_brief(findings, conn, session_id="chat-1")
    two = open_brief(findings, conn, session_id="chat-2", claim_figure="1,500")
    three = open_brief(findings, conn, session_id="chat-1", claim_figure="1,600")
    assert [f["id"] for f in findings.list_findings(conn)] == [1, 2, 3]
    assert [f["id"] for f in findings.list_findings(conn, session_id="chat-1")] == [1, 3]
    assert [f["id"] for f in findings.list_findings(conn, session_id="chat-2")] == [2]
    assert findings.list_findings(conn, session_id="chat-2") == [two]
    assert findings.list_findings(conn)[0] == one and findings.list_findings(conn)[2] == three


def test_open_findings_are_those_of_the_session_not_yet_decided_oldest_first(findings, conn):
    first = open_brief(findings, conn)
    second = open_brief(findings, conn, claim_figure="1,500")
    open_brief(findings, conn, session_id="elsewhere")
    assert [f["id"] for f in findings.open_findings(conn, session_id=SESSION)] == [first["id"], second["id"]]
    close(findings, conn, first, "1")
    assert [f["id"] for f in findings.open_findings(conn, session_id=SESSION)] == [second["id"]]
    assert [f["status"] for f in findings.list_findings(conn, session_id=SESSION)] == ["decided", "open"]


def test_a_finding_listed_is_the_finding_that_was_opened(findings, conn, summary_id):
    opened = open_data(findings, conn, summary_id)
    assert findings.list_findings(conn) == [opened]
    earlier = open_earlier(findings, conn)
    assert findings.list_findings(conn)[1] == earlier
    assert list(findings.list_findings(conn)[1]) == s5.FINDING_KEYS


def test_a_decided_finding_listed_has_the_decision_in_it(findings, conn, summary_id):
    opened = open_data(findings, conn, summary_id)
    decision, closed = close(findings, conn, opened, "1")
    [listed] = findings.list_findings(conn)
    assert listed == closed
    assert (listed["status"], listed["decision"], listed["choice"], listed["chosen"]) == ("decided", decision["id"], "1", "5000")
