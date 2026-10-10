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








# ---- the finding of kind brief --------------------------------------------------------------------------------------------







# ---- the finding of kind earlier ----------------------------------------------------------------------------------------------











# ---- open_finding ---------------------------------------------------------------------------------------------------------











# ---- close_finding --------------------------------------------------------------------------------------------------------

def close(findings, conn, finding, choice, saved=False, words=None, session_id=SESSION):
    decision = decide(conn, finding, choice=choice, words=words or choice)
    return decision, findings.close_finding(conn, finding["id"], decision_id=decision["id"], choice=choice, saved=saved,
                                            session_id=session_id)
















# ---- list_findings and open_findings ---------------------------------------------------------------------------------------





def test_open_findings_are_those_of_the_session_not_yet_decided_oldest_first(findings, conn):
    first = open_brief(findings, conn)
    second = open_brief(findings, conn, claim_figure="1,500")
    open_brief(findings, conn, session_id="elsewhere")
    assert [f["id"] for f in findings.open_findings(conn, session_id=SESSION)] == [first["id"], second["id"]]
    close(findings, conn, first, "1")
    assert [f["id"] for f in findings.open_findings(conn, session_id=SESSION)] == [second["id"]]
    assert [f["status"] for f in findings.list_findings(conn, session_id=SESSION)] == ["decided", "open"]




