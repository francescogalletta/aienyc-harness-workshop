"""SPEC 9.4: `summarise`: the checks in order, the figures, the balance and the inputs it returns."""
import pytest

import step5_helpers as s5
from step5_helpers import month_rows, put_import, put_months

MEASURES = ("money_in", "money_out", "net", "balance")

D1 = {"2026-01": (["1000"], ["200", "300.50"]),
      "2026-02": (["1000", "50.25"], ["400"]),
      "2026-03": ([], ["100"]),
      "2026-04": (["2000"], [])}


@pytest.fixture
def main(conn):
    put_months(conn, "main", D1)


def summarise(summaries, conn, **arguments):
    return summaries.summarise(conn, arguments)


def refusal(summaries, conn, **arguments):
    with pytest.raises(summaries.SummaryRefused) as error:
        summaries.summarise(conn, arguments)
    return str(error.value)


# ---- the constants ----------------------------------------------------------------------------------------------------------

def test_the_constants_and_the_measures(summaries):
    assert summaries.ALL_ACCOUNTS == "all" and summaries.MAX_MONTHS == 12
    assert summaries.MEASURES == s5.MEASURES
    assert list(summaries.MEASURES) == list(MEASURES)
    assert issubclass(summaries.SummaryRefused, Exception)


@pytest.mark.parametrize("name", ["SUMMARY_NO_DATA", "SUMMARY_MEASURE", "SUMMARY_ACCOUNT", "SUMMARY_BALANCE_ALL",
                                  "SUMMARY_NO_BALANCE", "SUMMARY_PERIOD", "SUMMARY_FEW_MONTHS", "SUMMARY_NOT_FULL",
                                  "MEASURE_WORDS", "DESCRIBE_AVERAGE", "DESCRIBE_MONTH", "DESCRIBE_BALANCE",
                                  "SCOPE_ALL", "SCOPE_ACCOUNT"])
def test_the_messages_of_the_summaries(summaries, name):
    assert getattr(summaries, name) == getattr(s5, name)


# ---- the checks, in order ---------------------------------------------------------------------------------------------------

def test_nothing_loaded(summaries, conn):
    assert refusal(summaries, conn, measure="money_in", account="all", months=1) == s5.SUMMARY_NO_DATA
    assert refusal(summaries, conn, measure="nonsense", account="nowhere") == s5.SUMMARY_NO_DATA


def test_nothing_loaded_after_the_files_are_cleared(adapter, summaries, conn, tmp_path):
    s5.add_text(adapter, conn, tmp_path, "bank.csv", s5.simple())
    adapter.clear_data(conn, session_id="C")
    assert refusal(summaries, conn, measure="money_in", account="all", months=1) == s5.SUMMARY_NO_DATA


@pytest.mark.parametrize("measure", ["spending", "", "MONEY_IN", "money in", None, 5, ["money_in"], {"a": 1}, True])
def test_the_measure_must_be_one_of_the_measures(summaries, conn, main, measure):
    assert refusal(summaries, conn, measure=measure, account="main", months=1) == s5.SUMMARY_MEASURE


def test_a_missing_measure(summaries, conn, main):
    assert refusal(summaries, conn, account="main", months=1) == s5.SUMMARY_MEASURE


@pytest.mark.parametrize("account", ["nowhere", "ALL", "Main", " main", ""])
def test_the_account_must_be_a_loaded_account_or_all(summaries, conn, main, account):
    assert refusal(summaries, conn, measure="money_in", account=account, months=1) == s5.SUMMARY_ACCOUNT.format(
        account=account, accounts="main")


def test_a_missing_account(summaries, conn, main):
    assert refusal(summaries, conn, measure="money_in", months=1).startswith("There is no account '")


def test_the_accounts_are_listed_sorted_and_joined(summaries, conn):
    put_months(conn, "zebra", {"2026-03": ([], [])})
    put_months(conn, "apple", {"2026-03": ([], [])})
    put_months(conn, "mango", {"2026-03": ([], [])})
    assert refusal(summaries, conn, measure="money_in", account="x", months=1) == s5.SUMMARY_ACCOUNT.format(
        account="x", accounts="apple, mango, zebra")


def test_the_measure_is_checked_before_the_account(summaries, conn, main):
    assert refusal(summaries, conn, measure="x", account="nowhere", months=1) == s5.SUMMARY_MEASURE


def test_a_balance_is_for_one_account(summaries, conn):
    put_import(conn, "main", [("2026-03-01", "1.00", "a", "5.00")])
    assert refusal(summaries, conn, measure="balance", account="all") == s5.SUMMARY_BALANCE_ALL


def test_a_balance_needs_a_balance_column(summaries, conn):
    put_import(conn, "plain", [("2026-03-01", "1.00", "a")])
    assert refusal(summaries, conn, measure="balance", account="plain") == s5.SUMMARY_NO_BALANCE.format(account="plain")


def test_the_account_is_checked_before_the_balance_rules(summaries, conn):
    put_import(conn, "main", [("2026-03-01", "1.00", "a", "5.00")])
    assert refusal(summaries, conn, measure="balance", account="nowhere") == s5.SUMMARY_ACCOUNT.format(
        account="nowhere", accounts="main")


def test_a_balance_ignores_months_and_month(summaries, conn):
    put_import(conn, "main", [("2026-03-01", "1.00", "a", "5.00")])
    for options in ({}, {"months": 99}, {"months": "x", "month": "y"}, {"months": 1, "month": "2026-03"}):
        _, output, _ = summarise(summaries, conn, measure="balance", account="main", **options)
        assert output["value"] == "5.00"


@pytest.mark.parametrize("period", [
    {}, {"months": None}, {"month": None}, {"months": None, "month": None},
    {"months": 1, "month": "2026-01"}, {"months": 0}, {"months": 13}, {"months": -1}, {"months": True},
    {"months": False}, {"months": 3.0}, {"months": "3"}, {"months": [3]},
    {"month": "2026-1"}, {"month": "2026-01-01"}, {"month": "26-01"}, {"month": 202601}, {"month": " 2026-01"},
    {"month": ""}, {"month": "January"}, {"month": True},
])
def test_exactly_one_of_months_and_month_in_range(summaries, conn, main, period):
    assert refusal(summaries, conn, measure="money_out", account="main", **period) == s5.SUMMARY_PERIOD


@pytest.mark.parametrize("period", [{"months": 1}, {"months": 4}, {"months": 3, "month": None},
                                    {"month": "2026-02"}, {"months": None, "month": "2026-02"}])
def test_the_periods_that_are_accepted(summaries, conn, main, period):
    inputs, output, _ = summarise(summaries, conn, measure="money_out", account="main", **period)
    assert output["measure"] == "money_out"


def test_months_up_to_twelve_are_a_period_and_more_than_loaded_is_too_few(summaries, conn, main):
    assert refusal(summaries, conn, measure="money_out", account="main", months=12) == s5.SUMMARY_FEW_MONTHS.format(
        count=4, scope="account 'main'", months="2026-01, 2026-02, 2026-03, 2026-04")


def test_too_few_full_months_for_all_accounts(summaries, conn, main):
    assert refusal(summaries, conn, measure="net", account="all", months=5) == s5.SUMMARY_FEW_MONTHS.format(
        count=4, scope="all accounts", months="2026-01, 2026-02, 2026-03, 2026-04")


def test_too_few_with_no_full_month_says_none(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "a"), ("2026-03-09", "1.00", "b")])
    assert refusal(summaries, conn, measure="net", account="main", months=1) == s5.SUMMARY_FEW_MONTHS.format(
        count=0, scope="account 'main'", months="none")


def test_the_period_is_checked_before_the_number_of_months(summaries, conn, main):
    assert refusal(summaries, conn, measure="net", account="main", months=13) == s5.SUMMARY_PERIOD


@pytest.mark.parametrize("month", ["2025-12", "2026-05", "2026-13", "2026-00", "0000-01"])
def test_a_month_that_is_not_a_full_month_of_the_scope(summaries, conn, main, month):
    assert refusal(summaries, conn, measure="net", account="main", month=month) == s5.SUMMARY_NOT_FULL.format(
        month=month, scope="account 'main'", months="2026-01, 2026-02, 2026-03, 2026-04")


def test_a_month_that_is_full_for_one_account_but_not_for_all(summaries, conn, main):
    put_months(conn, "short", {"2026-03": ([], []), "2026-04": ([], [])})
    assert refusal(summaries, conn, measure="net", account="all", month="2026-01") == s5.SUMMARY_NOT_FULL.format(
        month="2026-01", scope="all accounts", months="2026-03, 2026-04")


# ---- what it returns --------------------------------------------------------------------------------------------------------

def test_the_inputs_are_what_was_used(summaries, conn, main):
    inputs, _, _ = summarise(summaries, conn, measure="money_in", account="main", months=3)
    assert inputs == {"measure": "money_in", "account": "main", "months": 3}
    inputs, _, _ = summarise(summaries, conn, measure="money_in", account="all", month="2026-02")
    assert inputs == {"measure": "money_in", "account": "all", "month": "2026-02"}


def test_the_inputs_leave_out_a_null_period_and_extra_keys(summaries, conn, main):
    inputs, _, _ = summarise(summaries, conn, measure="net", account="main", months=2, month=None, comment="hello")
    assert inputs == {"measure": "net", "account": "main", "months": 2}


def test_the_inputs_of_a_balance_are_the_measure_and_the_account(summaries, conn):
    put_import(conn, "main", [("2026-03-01", "1.00", "a", "5.00")])
    inputs, _, _ = summarise(summaries, conn, measure="balance", account="main", months=3)
    assert inputs == {"measure": "balance", "account": "main"}


def test_the_imports_are_the_ids_of_the_scope_by_id(summaries, conn):
    first, _ = put_months(conn, "main", {"2026-03": ([], [])})
    second, _ = put_months(conn, "other", {"2026-03": ([], [])})
    third, _ = put_import(conn, "main", month_rows("2026-03"), name="again.csv")
    assert summarise(summaries, conn, measure="net", account="all", months=1)[2] == [first, second, third]
    assert summarise(summaries, conn, measure="net", account="main", months=1)[2] == [first, third]
    assert summarise(summaries, conn, measure="net", account="other", months=1)[2] == [second]


# ---- the monthly measures ---------------------------------------------------------------------------------------------------

def test_the_output_has_the_shape_of_the_contract(summaries, conn, main):
    _, output, _ = summarise(summaries, conn, measure="money_out", account="main", months=3)
    assert output == {"measure": "money_out", "account": "main", "months": ["2026-02", "2026-03", "2026-04"],
                      "by_month": [{"month": "2026-02", "value": "400.00"}, {"month": "2026-03", "value": "100.00"},
                                   {"month": "2026-04", "value": "0.00"}],
                      "value": "166.67", "left_out": 0}
    assert list(output) == ["measure", "account", "months", "by_month", "value", "left_out"]


def test_money_in(summaries, conn, main):
    _, output, _ = summarise(summaries, conn, measure="money_in", account="main", months=3)
    assert [m["value"] for m in output["by_month"]] == ["1050.25", "0.00", "2000.00"]
    assert output["value"] == "1016.75"


def test_net_is_money_in_less_money_out(summaries, conn, main):
    _, output, _ = summarise(summaries, conn, measure="net", account="main", months=3)
    assert [m["value"] for m in output["by_month"]] == ["650.25", "-100.00", "2000.00"]
    assert output["value"] == "850.08"


def test_money_out_is_a_positive_figure(summaries, conn, main):
    _, output, _ = summarise(summaries, conn, measure="money_out", account="main", month="2026-01")
    assert output["by_month"] == [{"month": "2026-01", "value": "500.50"}]


def test_the_months_are_the_latest_full_months_oldest_first(summaries, conn, main):
    assert summarise(summaries, conn, measure="net", account="main", months=1)[1]["months"] == ["2026-04"]
    assert summarise(summaries, conn, measure="net", account="main", months=2)[1]["months"] == ["2026-03", "2026-04"]
    assert summarise(summaries, conn, measure="net", account="main", months=4)[1]["months"] == [
        "2026-01", "2026-02", "2026-03", "2026-04"]


def test_one_month_asked_for_by_name(summaries, conn, main):
    _, output, _ = summarise(summaries, conn, measure="money_in", account="main", month="2026-02")
    assert output == {"measure": "money_in", "account": "main", "months": ["2026-02"],
                      "by_month": [{"month": "2026-02", "value": "1050.25"}], "value": "1050.25", "left_out": 0}


def test_one_month_by_count_has_the_same_output_as_by_name(summaries, conn, main):
    by_count = summarise(summaries, conn, measure="money_in", account="main", months=1)[1]
    by_name = summarise(summaries, conn, measure="money_in", account="main", month="2026-04")[1]
    assert by_count == by_name


def test_value_is_the_sum_of_the_months_over_their_number(summaries, conn, main):
    _, output, _ = summarise(summaries, conn, measure="money_out", account="main", months=4)
    assert output["value"] == "250.13"                      # (500.50 + 400 + 100 + 0) / 4 = 250.125, half up


def test_only_transactions_dated_in_the_month_count(summaries, conn):
    put_import(conn, "main", month_rows("2026-03", outs=["10"]) + [("2026-02-28", "-999.00", "before"),
                                                                    ("2026-04-01", "-999.00", "after")])
    assert summarise(summaries, conn, measure="money_out", account="main", month="2026-03")[1]["value"] == "10.00"


def test_the_account_scope_counts_only_that_account(summaries, conn, main):
    put_months(conn, "other", {"2026-01": (["7"], ["3"]), "2026-02": ([], []), "2026-03": ([], []), "2026-04": ([], [])})
    assert summarise(summaries, conn, measure="money_in", account="main", month="2026-01")[1]["value"] == "1000.00"
    assert summarise(summaries, conn, measure="money_in", account="other", month="2026-01")[1]["value"] == "7.00"
    assert summarise(summaries, conn, measure="money_in", account="all", month="2026-01")[1]["value"] == "1007.00"
    assert summarise(summaries, conn, measure="money_out", account="all", month="2026-01")[1]["value"] == "503.50"


def test_all_uses_the_months_that_are_full_for_every_account(summaries, conn, main):
    put_months(conn, "short", {"2026-03": ([], []), "2026-04": ([], [])})
    _, output, _ = summarise(summaries, conn, measure="net", account="all", months=2)
    assert output["months"] == ["2026-03", "2026-04"]


def test_zero_amounts_are_neither_in_nor_out(summaries, conn):
    put_import(conn, "main", month_rows("2026-03"))
    for measure in ("money_in", "money_out", "net"):
        assert summarise(summaries, conn, measure=measure, account="main", month="2026-03")[1]["value"] == "0.00"


# ---- rounding and writing ---------------------------------------------------------------------------------------------------

def one_month_out(summaries, conn, amount):
    put_import(conn, "main", month_rows("2026-03") + [("2026-03-15", amount, "x")])
    return summarise(summaries, conn, measure="money_out", account="main", month="2026-03")[1]["value"]


@pytest.mark.parametrize("amount, written", [
    ("-0.005", "0.01"), ("-0.004", "0.00"), ("-0.015", "0.02"), ("-0.025", "0.03"), ("-2.675", "2.68"),
    ("-1234.5", "1234.50"), ("-1234567.891", "1234567.89"), ("-7", "7.00"), ("-0.0049", "0.00"),
])
def test_figures_are_rounded_half_up_to_cents_and_written_with_two_decimals(summaries, conn, amount, written):
    assert one_month_out(summaries, conn, amount) == written


def test_the_average_is_rounded_half_up_once_when_written(summaries, conn):
    """Two months of 0.01 and 0.00 average 0.005, which is written 0.01: not round-half-even, not 0.00."""
    put_months(conn, "main", {"2026-02": ([], ["0.01"]), "2026-03": ([], [])})
    _, output, _ = summarise(summaries, conn, measure="money_out", account="main", months=2)
    assert output["value"] == "0.01"


def test_the_average_is_worked_out_before_rounding(summaries, conn):
    """Months of 0.005 and 0.004 show as 0.01 and 0.00, but their average is 0.0045, which is written 0.00."""
    put_months(conn, "main", {"2026-02": ([], ["0.005"]), "2026-03": ([], ["0.004"])})
    _, output, _ = summarise(summaries, conn, measure="money_out", account="main", months=2)
    assert [m["value"] for m in output["by_month"]] == ["0.01", "0.00"]
    assert output["value"] == "0.00"


def test_a_negative_net_has_a_leading_minus_and_never_minus_zero(summaries, conn):
    put_months(conn, "main", {"2026-02": ([], ["5.5"]), "2026-03": ([], ["0.004"])})
    _, output, _ = summarise(summaries, conn, measure="net", account="main", months=2)
    assert output["by_month"] == [{"month": "2026-02", "value": "-5.50"}, {"month": "2026-03", "value": "0.00"}]
    assert output["value"] == "-2.75"


def test_no_thousands_separator(summaries, conn):
    put_months(conn, "main", {"2026-03": (["1234567.5"], [])})
    assert summarise(summaries, conn, measure="money_in", account="main", month="2026-03")[1]["value"] == "1234567.50"


# ---- balance ----------------------------------------------------------------------------------------------------------------

def balance(summaries, conn, account="main"):
    return summarise(summaries, conn, measure="balance", account=account)[1]


def test_the_balance_output(summaries, conn):
    put_import(conn, "savings_2026", [("2026-09-29", "400.00", "a", "13331.29"), ("2026-09-30", "22.10", "b", "13353.39")])
    assert balance(summaries, conn, "savings_2026") == {"measure": "balance", "account": "savings_2026",
                                                        "as_of": "2026-09-30", "value": "13353.39"}
    assert list(balance(summaries, conn, "savings_2026")) == ["measure", "account", "as_of", "value"]


def test_the_balance_is_that_of_the_latest_date(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "c", "30.00"), ("2026-03-01", "1.00", "a", "10.00"),
                              ("2026-03-03", "1.00", "b", "20.00")])
    assert balance(summaries, conn) == {"measure": "balance", "account": "main", "as_of": "2026-03-05", "value": "30.00"}


def test_on_one_date_the_higher_row_number_is_later(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "first", "10.00"), ("2026-03-05", "1.00", "second", "20.00")])
    assert balance(summaries, conn)["value"] == "20.00"


def test_on_one_date_the_lower_row_number_is_later_in_a_newest_first_file(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "newer", "20.00"), ("2026-03-05", "1.00", "older", "10.00")],
               newest_first=True)
    assert balance(summaries, conn)["value"] == "20.00"


def test_a_later_import_is_later_on_one_date(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "a", "10.00")], name="one.csv")
    put_import(conn, "main", [("2026-03-05", "1.00", "b", "20.00")], name="two.csv")
    assert balance(summaries, conn)["value"] == "20.00"


def test_the_date_comes_before_the_import(summaries, conn):
    put_import(conn, "main", [("2026-03-06", "1.00", "a", "10.00")], name="one.csv")
    put_import(conn, "main", [("2026-03-05", "1.00", "b", "20.00")], name="two.csv")
    assert balance(summaries, conn) == {"measure": "balance", "account": "main", "as_of": "2026-03-06", "value": "10.00"}


def test_the_import_comes_before_the_row_number(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "a", "10.00"), ("2026-03-05", "1.00", "b", "11.00")], name="one.csv")
    put_import(conn, "main", [("2026-03-05", "1.00", "c", "20.00")], name="two.csv")
    assert balance(summaries, conn)["value"] == "20.00"


def test_newest_first_reverses_only_within_its_own_import(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "a", "10.00"), ("2026-03-05", "1.00", "b", "11.00")],
               name="one.csv", newest_first=True)
    put_import(conn, "main", [("2026-03-05", "1.00", "c", "20.00")], name="two.csv")
    assert balance(summaries, conn)["value"] == "20.00"


def test_the_balance_of_one_account_ignores_the_others(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "a", "10.00")])
    put_import(conn, "other", [("2026-04-05", "1.00", "a", "99.00")])
    assert balance(summaries, conn)["value"] == "10.00"


def test_a_negative_balance(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "-50.00", "a", "-12.50")])
    assert balance(summaries, conn)["value"] == "-12.50"
