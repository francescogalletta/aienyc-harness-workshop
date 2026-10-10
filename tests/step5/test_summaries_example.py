"""SPEC 9.4 with the real files of tests/fixtures/accounts/example/. The spec states the money out of all accounts over the last three full
months (4132.31, 4 transactions left out). The other figures are worked out from the files by the rules of 9.2 and 9.4, with
the files loaded in the order checking, savings, card."""
import pytest

import step5_helpers as s5

MONTHS = ["2026-06", "2026-07", "2026-08"]


def summarise(summaries, conn, **arguments):
    return summaries.summarise(conn, arguments)[1]


def by_month(output):
    return [(m["month"], m["value"]) for m in output["by_month"]]


def test_the_full_months_of_each_account_and_of_all(summaries, conn, example_loaded):
    assert summaries.full_months(conn, "checking_2026") == [f"2026-0{m}" for m in range(1, 9)]
    assert summaries.full_months(conn, "savings_2026") == [f"2026-0{m}" for m in range(2, 10)]
    assert summaries.full_months(conn, "card_2026") == [f"2026-0{m}" for m in range(2, 9)]
    assert summaries.full_months(conn, "all") == [f"2026-0{m}" for m in range(2, 9)]


def test_the_accounts(summaries, conn, example_loaded):
    found = summaries.accounts(conn)
    assert [(a["account"], a["files"], a["transactions"], a["first"], a["last"], a["balance"]) for a in found] == [
        ("card_2026", ["card_2026.csv"], 248, "2026-01-02", "2026-09-29", False),
        ("checking_2026", ["checking_2026.csv"], 112, "2026-01-01", "2026-09-29", True),
        ("savings_2026", ["savings_2026.csv"], 12, "2026-01-29", "2026-09-30", True)]


def test_the_example_of_the_spec(summaries, conn, example_loaded):
    output = summarise(summaries, conn, measure="money_out", account="all", months=3)
    assert output == {"measure": "money_out", "account": "all", "months": MONTHS,
                      "by_month": [{"month": "2026-06", "value": "3613.17"}, {"month": "2026-07", "value": "4658.17"},
                                   {"month": "2026-08", "value": "4125.59"}],
                      "value": "4132.31", "left_out": 4}


def test_the_describe_of_the_example(summaries, conn, example_loaded):
    output = summarise(summaries, conn, measure="money_out", account="all", months=3)
    assert summaries.describe(output) == "money out a month, on average over the 3 full months 2026-06 to 2026-08, all accounts"


def test_money_in_and_net_for_all_accounts(summaries, conn, example_loaded):
    money_in = summarise(summaries, conn, measure="money_in", account="all", months=3)
    assert by_month(money_in) == [("2026-06", "5375.43"), ("2026-07", "3200.14"), ("2026-08", "250.00")]
    assert money_in["value"] == "2941.86" and money_in["left_out"] == 4
    net = summarise(summaries, conn, measure="net", account="all", months=3)
    assert by_month(net) == [("2026-06", "1762.26"), ("2026-07", "-1458.03"), ("2026-08", "-3875.59")]
    assert net["value"] == "-1190.45"


def test_one_month_of_all_accounts(summaries, conn, example_loaded):
    output = summarise(summaries, conn, measure="money_out", account="all", month="2026-07")
    assert output["by_month"] == [{"month": "2026-07", "value": "4658.17"}]
    assert output["value"] == "4658.17" and output["left_out"] == 2


def test_the_card_alone(summaries, conn, example_loaded):
    out = summarise(summaries, conn, measure="money_out", account="card_2026", months=3)
    assert by_month(out) == [("2026-06", "1293.17"), ("2026-07", "890.36"), ("2026-08", "1744.34")]
    assert out["value"] == "1309.29" and out["left_out"] == 0


def test_the_current_account_alone_leaves_out_its_own_side_of_the_transfers(summaries, conn, example_loaded):
    out = summarise(summaries, conn, measure="money_out", account="checking_2026", months=3)
    assert by_month(out) == [("2026-06", "2320.00"), ("2026-07", "2767.81"), ("2026-08", "2381.25")]
    assert out["value"] == "2489.69" and out["left_out"] == 2


def test_the_savings_account_alone(summaries, conn, example_loaded):
    """Its full months run to September, so its latest three are July to September."""
    out = summarise(summaries, conn, measure="money_out", account="savings_2026", months=3)
    assert out["months"] == ["2026-07", "2026-08", "2026-09"]
    assert by_month(out) == [("2026-07", "1000.00"), ("2026-08", "0.00"), ("2026-09", "0.00")]
    assert out["value"] == "333.33" and out["left_out"] == 2
    money_in = summarise(summaries, conn, measure="money_in", account="savings_2026", months=3)
    assert by_month(money_in) == [("2026-07", "0.00"), ("2026-08", "0.00"), ("2026-09", "22.10")]
    assert money_in["value"] == "7.37"


def test_the_balances_of_the_key(summaries, conn, example_loaded):
    assert summarise(summaries, conn, measure="balance", account="checking_2026") == {
        "measure": "balance", "account": "checking_2026", "as_of": "2026-09-29", "value": "6318.60"}
    assert summarise(summaries, conn, measure="balance", account="savings_2026") == {
        "measure": "balance", "account": "savings_2026", "as_of": "2026-09-30", "value": "13353.39"}


def test_the_card_has_no_balance(summaries, conn, example_loaded):
    with pytest.raises(summaries.SummaryRefused) as error:
        summaries.summarise(conn, {"measure": "balance", "account": "card_2026"})
    assert str(error.value) == s5.SUMMARY_NO_BALANCE.format(account="card_2026")


def test_september_is_not_a_full_month_for_all(summaries, conn, example_loaded):
    with pytest.raises(summaries.SummaryRefused) as error:
        summaries.summarise(conn, {"measure": "money_out", "account": "all", "month": "2026-09"})
    assert str(error.value) == s5.SUMMARY_NOT_FULL.format(
        month="2026-09", scope="all accounts", months="2026-02, 2026-03, 2026-04, 2026-05, 2026-06, 2026-07, 2026-08")


def test_only_seven_full_months_are_loaded_for_all(summaries, conn, example_loaded):
    with pytest.raises(summaries.SummaryRefused) as error:
        summaries.summarise(conn, {"measure": "net", "account": "all", "months": 8})
    assert str(error.value).startswith("Only 7 full months are loaded for all accounts: 2026-02,")


def test_the_run_is_recorded_and_returned(summaries, conn, example_loaded):
    result = summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 3}, session_id="S")
    assert result["summary"] == 1 and result["value"] == "4132.31"
    [payload] = s5.payloads(conn, "data.summary")
    assert payload["imports"] == [1, 2, 3] and payload["output"]["left_out"] == 4
