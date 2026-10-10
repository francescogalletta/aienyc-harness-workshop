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





# ---- the checks, in order ---------------------------------------------------------------------------------------------------































def test_too_few_full_months_for_all_accounts(summaries, conn, main):
    assert refusal(summaries, conn, measure="net", account="all", months=5) == s5.SUMMARY_FEW_MONTHS.format(
        count=4, scope="all accounts", months="2026-01, 2026-02, 2026-03, 2026-04")










# ---- what it returns --------------------------------------------------------------------------------------------------------









# ---- the monthly measures ---------------------------------------------------------------------------------------------------



def test_money_in(summaries, conn, main):
    _, output, _ = summarise(summaries, conn, measure="money_in", account="main", months=3)
    assert [m["value"] for m in output["by_month"]] == ["1050.25", "0.00", "2000.00"]
    assert output["value"] == "1016.75"


def test_net_is_money_in_less_money_out(summaries, conn, main):
    _, output, _ = summarise(summaries, conn, measure="net", account="main", months=3)
    assert [m["value"] for m in output["by_month"]] == ["650.25", "-100.00", "2000.00"]
    assert output["value"] == "850.08"




















# ---- rounding and writing ---------------------------------------------------------------------------------------------------

def one_month_out(summaries, conn, amount):
    put_import(conn, "main", month_rows("2026-03") + [("2026-03-15", amount, "x")])
    return summarise(summaries, conn, measure="money_out", account="main", month="2026-03")[1]["value"]












# ---- balance ----------------------------------------------------------------------------------------------------------------

def balance(summaries, conn, account="main"):
    return summarise(summaries, conn, measure="balance", account=account)[1]




def test_the_balance_is_that_of_the_latest_date(summaries, conn):
    put_import(conn, "main", [("2026-03-05", "1.00", "c", "30.00"), ("2026-03-01", "1.00", "a", "10.00"),
                              ("2026-03-03", "1.00", "b", "20.00")])
    assert balance(summaries, conn) == {"measure": "balance", "account": "main", "as_of": "2026-03-05", "value": "30.00"}
















