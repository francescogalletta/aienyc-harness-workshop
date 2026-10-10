"""SPEC 9.4: a full calendar month, `full_months`, and `accounts`."""
import pytest

import step5_helpers as s5
from step5_helpers import put_import


def put_span(conn, account, first, last, *, extra=()):
    """Rows on the first and last day given (and `extra` days between), so that the rows reach exactly that far."""
    rows = [(first, "1.00", "first"), *[(day, "1.00", "between") for day in extra], (last, "1.00", "last")]
    return put_import(conn, account, rows)


# ---- full_months ------------------------------------------------------------------------------------------------------

def test_no_transactions_no_full_month(summaries, conn):
    assert summaries.full_months(conn, "all") == []
    assert summaries.full_months(conn, "main") == []


def test_months_whose_first_and_last_day_the_rows_reach_are_full(summaries, conn):
    put_span(conn, "main", "2026-01-01", "2026-03-31")
    assert summaries.full_months(conn, "main") == ["2026-01", "2026-02", "2026-03"]


def test_a_first_month_started_late_is_not_full(summaries, conn):
    put_span(conn, "main", "2026-01-02", "2026-03-31")
    assert summaries.full_months(conn, "main") == ["2026-02", "2026-03"]


def test_a_last_month_ended_early_is_not_full(summaries, conn):
    put_span(conn, "main", "2026-01-01", "2026-03-30")
    assert summaries.full_months(conn, "main") == ["2026-01", "2026-02"]


def test_a_month_in_the_middle_with_no_rows_is_full(summaries, conn):
    put_span(conn, "main", "2026-01-01", "2026-04-30")
    assert summaries.full_months(conn, "main") == ["2026-01", "2026-02", "2026-03", "2026-04"]


def test_months_are_oldest_first_across_a_year_end(summaries, conn):
    put_span(conn, "main", "2025-11-01", "2026-02-28")
    assert summaries.full_months(conn, "main") == ["2025-11", "2025-12", "2026-01", "2026-02"]


@pytest.mark.parametrize("last, months", [("2024-02-28", ["2024-01"]), ("2024-02-29", ["2024-01", "2024-02"]),
                                          ("2023-02-28", ["2023-01", "2023-02"])])
def test_the_last_day_of_february_depends_on_the_year(summaries, conn, last, months):
    put_span(conn, "main", last[:4] + "-01-01", last)
    assert summaries.full_months(conn, "main") == months


@pytest.mark.parametrize("last", ["2026-04-30", "2026-05-01"])
def test_the_last_day_of_a_thirty_day_month(summaries, conn, last):
    put_span(conn, "main", "2026-04-01", last)
    assert summaries.full_months(conn, "main") == ["2026-04"]


def test_one_day_alone_makes_no_full_month_unless_it_is_both_ends(summaries, conn):
    put_span(conn, "main", "2026-03-15", "2026-03-15")
    assert summaries.full_months(conn, "main") == []


def test_the_order_of_the_rows_in_the_table_does_not_matter(summaries, conn):
    put_import(conn, "main", [("2026-03-31", "1.00", "late"), ("2026-03-15", "1.00", "mid"), ("2026-03-01", "1.00", "early")],
               newest_first=True)
    assert summaries.full_months(conn, "main") == ["2026-03"]


def test_only_the_transactions_of_the_account_count(summaries, conn):
    put_span(conn, "main", "2026-01-01", "2026-02-28")
    put_span(conn, "other", "2026-01-15", "2026-06-30")
    assert summaries.full_months(conn, "main") == ["2026-01", "2026-02"]
    assert summaries.full_months(conn, "other") == ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]


def test_two_files_of_one_account_count_together(summaries, conn):
    put_span(conn, "main", "2026-01-01", "2026-01-31")
    put_span(conn, "main", "2026-02-01", "2026-02-28")
    assert summaries.full_months(conn, "main") == ["2026-01", "2026-02"]


def test_an_account_that_is_not_loaded_has_no_full_month(summaries, conn):
    put_span(conn, "main", "2026-01-01", "2026-03-31")
    assert summaries.full_months(conn, "nowhere") == []


def test_for_all_a_month_is_full_when_it_is_full_for_every_account(summaries, conn):
    put_span(conn, "one", "2026-01-01", "2026-03-31")
    put_span(conn, "two", "2026-02-01", "2026-04-30")
    assert summaries.full_months(conn, "all") == ["2026-02", "2026-03"]


def test_for_all_accounts_that_do_not_overlap_give_no_month(summaries, conn):
    put_span(conn, "one", "2026-01-01", "2026-02-28")
    put_span(conn, "two", "2026-05-01", "2026-06-30")
    assert summaries.full_months(conn, "all") == []


def test_for_all_with_one_account_it_is_that_accounts_months(summaries, conn):
    put_span(conn, "one", "2026-01-01", "2026-03-31")
    assert summaries.full_months(conn, "all") == summaries.full_months(conn, "one")


# ---- accounts ----------------------------------------------------------------------------------------------------------

def test_no_accounts(summaries, conn):
    assert summaries.accounts(conn) == []


def test_an_account_as_a_dict(adapter, summaries, conn, tmp_path):
    folder = tmp_path / "files"
    s5.add_text(adapter, conn, folder, "one.csv", "Date,Description,Amount,Balance\n2026-01-01,a,1.00,5.00\n"
                                                  "2026-01-31,b,2.00,7.00\n", account="main")
    s5.add_text(adapter, conn, folder, "two.csv", "Date,Description,Amount\n2026-02-01,c,3.00\n2026-02-28,d,4.00\n",
                account="main")
    assert summaries.accounts(conn) == [{"account": "main", "files": ["one.csv", "two.csv"], "transactions": 4,
                                         "first": "2026-01-01", "last": "2026-02-28",
                                         "full_months": ["2026-01", "2026-02"], "balance": True}]


def test_accounts_are_sorted_by_name_and_say_whether_they_have_a_balance(adapter, summaries, conn, tmp_path):
    folder = tmp_path / "files"
    s5.add_text(adapter, conn, folder, "zeta.csv", s5.simple())
    s5.add_text(adapter, conn, folder, "alpha.csv", "Date,Description,Amount,Balance\n2026-03-01,a,1.00,5.00\n")
    found = summaries.accounts(conn)
    assert [a["account"] for a in found] == ["alpha", "zeta"]
    assert [a["balance"] for a in found] == [True, False]
    assert found[0]["files"] == ["alpha.csv"] and found[1]["files"] == ["zeta.csv"]


def test_files_are_listed_by_import_id(adapter, summaries, conn, tmp_path):
    folder = tmp_path / "files"
    s5.add_text(adapter, conn, folder, "b_second_name.csv", s5.simple(), account="main")
    s5.add_text(adapter, conn, folder, "a_first_name.csv", "Date,Description,Amount\n2026-03-30,x,1.00\n", account="main")
    assert summaries.accounts(conn)[0]["files"] == ["b_second_name.csv", "a_first_name.csv"]


def test_balance_is_true_when_some_transaction_has_a_balance(summaries, conn):
    put_import(conn, "main", [("2026-03-01", "1.00", "a"), ("2026-03-02", "1.00", "b", "5.00")])
    put_import(conn, "plain", [("2026-03-01", "1.00", "a")])
    assert {a["account"]: a["balance"] for a in summaries.accounts(conn)} == {"main": True, "plain": False}


def test_the_full_months_of_an_account_are_those_of_full_months(summaries, conn):
    put_span(conn, "main", "2026-01-01", "2026-03-31")
    assert summaries.accounts(conn)[0]["full_months"] == summaries.full_months(conn, "main")
