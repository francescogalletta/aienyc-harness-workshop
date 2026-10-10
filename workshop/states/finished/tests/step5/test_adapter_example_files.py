"""SPEC 9.2: the three account files of tests/fixtures/accounts/example/ load as they are. The figures are those of tests/fixtures/accounts/FACILITATOR_KEY.md,
which the file contents also give by the rules of 9.2 (counts, balances, the rows left out)."""
from decimal import Decimal

import pytest

import step5_helpers as s5
from step5_helpers import EXAMPLE_DATA

CHECKING_COLUMNS = {"date": "Fecha", "description": "Concepto", "amount": "Importe", "balance": "Saldo"}
CARD_COLUMNS = {"date": "date", "description": "description", "amount": "amount", "balance": None}


def reading_of(adapter, name):
    return adapter.read_table((EXAMPLE_DATA / name).read_bytes())


@pytest.fixture
def checking(adapter):
    return reading_of(adapter, "checking_2026.csv")


@pytest.fixture
def savings(adapter):
    return reading_of(adapter, "savings_2026.csv")


@pytest.fixture
def card(adapter):
    return reading_of(adapter, "card_2026.csv")


# ---- the current account --------------------------------------------------------------------------------------------















# ---- the savings account --------------------------------------------------------------------------------------------







# ---- the card ------------------------------------------------------------------------------------------------------









# ---- the budget kept by hand is not an account file ------------------------------------------------------------------



# ---- loaded -------------------------------------------------------------------------------------------------------

def test_the_three_files_load_as_they_are(adapter, conn, example_loaded):
    assert [(i["account"], i["transactions"], i["first"], i["last"]) for i in example_loaded] == [
        ("checking_2026", 112, "2026-01-01", "2026-09-29"),
        ("savings_2026", 12, "2026-01-29", "2026-09-30"),
        ("card_2026", 248, "2026-01-02", "2026-09-29")]
    assert [i["sign"] for i in example_loaded] == ["out_negative", "out_negative", "out_positive"]
    assert [i["name"] for i in example_loaded] == ["checking_2026.csv", "savings_2026.csv", "card_2026.csv"]
    assert len(s5.transactions(conn)) == 112 + 12 + 248
    # the balances of tests/fixtures/accounts/FACILITATOR_KEY.md: the newest row's balance, and the account before its first row
    checking, savings = s5.transactions(conn, "checking_2026"), s5.transactions(conn, "savings_2026")
    assert checking[0]["balance"] == "6318.60" and checking[-1]["balance"] == "5030.52"
    assert savings[0]["balance"] == "13353.39"
    assert Decimal(checking[0]["balance"]) - sum(Decimal(r["amount"]) for r in checking) == Decimal("6180.52")
    assert Decimal(savings[0]["balance"]) - sum(Decimal(r["amount"]) for r in savings) == Decimal("6200.00")






