"""SPEC 9.4: `run_summary`, the records it leaves, and `describe`."""
import json
from datetime import datetime, timedelta

import pytest

import step5_helpers as s5
from step5_helpers import month_rows, put_import, put_months

D1 = {"2026-01": (["1000"], ["200"]), "2026-02": (["1000"], ["400"]), "2026-03": ([], ["100"]), "2026-04": (["2000"], [])}
ARGUMENTS = {"measure": "money_out", "account": "all", "months": 3}


@pytest.fixture
def main(conn):
    return put_months(conn, "main", D1)[0]


def run(summaries, conn, session_id="S1", **arguments):
    return summaries.run_summary(conn, arguments or ARGUMENTS, session_id=session_id)


# ---- run_summary ------------------------------------------------------------------------------------------------------











def test_a_refused_summary_raises_and_records_the_refusal(summaries, conn, main):
    arguments = {"measure": "money_out", "account": "nowhere", "months": 3, "extra": [1, 2]}
    with pytest.raises(summaries.SummaryRefused) as error:
        summaries.run_summary(conn, arguments, session_id="the-chat")
    message = s5.SUMMARY_ACCOUNT.format(account="nowhere", accounts="main")
    assert str(error.value) == message
    assert s5.events(conn, "data.summary_refused") == [("data.summary_refused", "harness",
                                                         {"arguments": arguments, "error": message})]
    [row] = s5.sql_rows(conn, "SELECT session_id FROM events WHERE kind = 'data.summary_refused'")
    assert row["session_id"] == "the-chat"






def test_the_summary_survives_data_clear(adapter, summaries, conn, tmp_path):
    s5.add_text(adapter, conn, tmp_path, "bank.csv", "Date,Description,Amount\n2026-03-01,a,1.00\n2026-03-31,b,2.00\n")
    result = summaries.run_summary(conn, {"measure": "money_in", "account": "all", "months": 1}, session_id="S")
    adapter.clear_data(conn, session_id="C")
    assert [r["id"] for r in s5.summary_rows(conn)] == [result["summary"]]
    assert json.loads(s5.summary_rows(conn)[0]["output"])["value"] == "3.00"




# ---- describe ---------------------------------------------------------------------------------------------------------------

def test_the_spec_example(summaries):
    output = {"measure": "money_out", "account": "all", "months": ["2026-06", "2026-07", "2026-08"],
              "by_month": [{"month": "2026-06", "value": "3613.17"}, {"month": "2026-07", "value": "4658.17"},
                           {"month": "2026-08", "value": "4125.59"}], "value": "4132.31", "left_out": 4}
    assert summaries.describe(output) == "money out a month, on average over the 3 full months 2026-06 to 2026-08, all accounts"










