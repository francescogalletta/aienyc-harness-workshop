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

def test_the_result_is_the_summary_id_followed_by_the_output(summaries, conn, main):
    result = run(summaries, conn)
    _, output, _ = summaries.summarise(conn, ARGUMENTS)
    assert result == {"summary": 1, **output}
    assert list(result)[0] == "summary" and list(result)[1:] == list(output)


def test_the_ids_count_up(summaries, conn, main):
    assert [run(summaries, conn)["summary"] for _ in range(3)] == [1, 2, 3]


def test_a_row_is_inserted_into_data_summaries(summaries, conn, main):
    result = run(summaries, conn, session_id="the-chat")
    [row] = s5.summary_rows(conn)
    inputs, output, imports = summaries.summarise(conn, ARGUMENTS)
    assert row["id"] == result["summary"] and row["session_id"] == "the-chat"
    assert json.loads(row["inputs"]) == inputs == {"measure": "money_out", "account": "all", "months": 3}
    assert json.loads(row["output"]) == output
    assert json.loads(row["imports"]) == imports == [main]
    assert datetime.fromisoformat(row["ts"]).utcoffset() == timedelta(0)


def test_data_summary_is_recorded(summaries, conn, main):
    result = run(summaries, conn, session_id="the-chat")
    [(kind, actor, payload)] = s5.events(conn, "data.summary")
    _, output, imports = summaries.summarise(conn, ARGUMENTS)
    assert (kind, actor) == ("data.summary", "harness")
    assert payload == {"id": result["summary"], "inputs": ARGUMENTS, "output": output, "imports": imports}
    [row] = s5.sql_rows(conn, "SELECT session_id FROM events WHERE kind = 'data.summary'")
    assert row["session_id"] == "the-chat"


def test_the_summary_of_a_balance(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "a", "10.00")])
    result = summaries.run_summary(conn, {"measure": "balance", "account": "main"}, session_id="S")
    assert result == {"summary": 1, "measure": "balance", "account": "main", "as_of": "2026-03-05", "value": "10.00"}


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


def test_a_refused_summary_inserts_nothing_and_records_no_summary(summaries, conn, main):
    with pytest.raises(summaries.SummaryRefused):
        summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 99}, session_id="S")
    assert s5.summary_rows(conn) == [] and s5.events(conn, "data.summary") == []


def test_every_refusal_reason_is_recorded_as_sent(summaries, conn):
    with pytest.raises(summaries.SummaryRefused):
        summaries.run_summary(conn, {"measure": "money_in", "account": "all", "months": 1}, session_id="S")
    assert s5.payloads(conn, "data.summary_refused")[0]["error"] == s5.SUMMARY_NO_DATA


def test_the_summary_survives_data_clear(adapter, summaries, conn, tmp_path):
    s5.add_text(adapter, conn, tmp_path, "bank.csv", "Date,Description,Amount\n2026-03-01,a,1.00\n2026-03-31,b,2.00\n")
    result = summaries.run_summary(conn, {"measure": "money_in", "account": "all", "months": 1}, session_id="S")
    adapter.clear_data(conn, session_id="C")
    assert [r["id"] for r in s5.summary_rows(conn)] == [result["summary"]]
    assert json.loads(s5.summary_rows(conn)[0]["output"])["value"] == "3.00"


def test_a_second_summary_of_the_same_thing_is_a_new_row(summaries, conn, main):
    first, second = run(summaries, conn), run(summaries, conn)
    assert first["summary"] != second["summary"] and len(s5.summary_rows(conn)) == 2


# ---- describe ---------------------------------------------------------------------------------------------------------------

def test_the_spec_example(summaries):
    output = {"measure": "money_out", "account": "all", "months": ["2026-06", "2026-07", "2026-08"],
              "by_month": [{"month": "2026-06", "value": "3613.17"}, {"month": "2026-07", "value": "4658.17"},
                           {"month": "2026-08", "value": "4125.59"}], "value": "4132.31", "left_out": 4}
    assert summaries.describe(output) == "money out a month, on average over the 3 full months 2026-06 to 2026-08, all accounts"


@pytest.mark.parametrize("measure, words", [("money_in", "money in"), ("money_out", "money out"),
                                            ("net", "money in less money out")])
def test_the_words_of_each_measure(summaries, conn, measure, words):
    put_months(conn, "main", D1)
    _, output, _ = summaries.summarise(conn, {"measure": measure, "account": "main", "months": 2})
    assert summaries.describe(output) == f"{words} a month, on average over the 2 full months 2026-03 to 2026-04, account 'main'"


def test_one_month_is_described_by_its_name(summaries, conn):
    put_months(conn, "main", D1)
    _, output, _ = summaries.summarise(conn, {"measure": "money_out", "account": "all", "month": "2026-02"})
    assert summaries.describe(output) == "money out in 2026-02, all accounts"


def test_one_month_asked_for_with_months_is_one_month(summaries, conn):
    put_months(conn, "main", D1)
    _, output, _ = summaries.summarise(conn, {"measure": "net", "account": "main", "months": 1})
    assert summaries.describe(output) == "money in less money out in 2026-04, account 'main'"


def test_a_balance_is_described_with_its_date(summaries, conn):
    put_import(conn, "savings_2026", [("2026-09-30", "22.10", "a", "13353.39")])
    _, output, _ = summaries.summarise(conn, {"measure": "balance", "account": "savings_2026"})
    assert summaries.describe(output) == "the balance of account 'savings_2026' on 2026-09-30"


def test_describe_reads_only_the_output(summaries):
    output = {"measure": "money_in", "account": "joint", "months": ["2025-12", "2026-01"],
              "by_month": [], "value": "0.00", "left_out": 0}
    assert summaries.describe(output) == "money in a month, on average over the 2 full months 2025-12 to 2026-01, account 'joint'"
