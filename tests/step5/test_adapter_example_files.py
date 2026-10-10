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

def test_checking_is_read_as_the_spec_says(checking):
    assert checking["delimiter"] == ";" and checking["header_row"] == 1
    assert checking["columns"] == CHECKING_COLUMNS
    assert checking["date_format"] == "DD/MM/YYYY" and checking["number_format"] == "1.234,56"
    assert checking["newest_first"] is True


def test_checking_has_112_transactions_after_the_repeats_are_left_out(checking):
    assert len(checking["rows"]) == 112


def test_checking_row_38_is_a_repeated_heading_and_rows_39_and_40_are_repeated_rows(checking):
    assert checking["dropped"] == [{"row": 38, "reason": "repeated header"}, {"row": 39, "reason": "repeated row"},
                                   {"row": 40, "reason": "repeated row"}]
    assert checking["same_kept"] == []
    assert not {38, 39, 40} & {r["row"] for r in checking["rows"]}


def test_checking_first_and_last_rows(checking):
    first, last = checking["rows"][0], checking["rows"][-1]
    assert first == {"row": 2, "date": "2026-09-29", "amount": "-400.00", "description": "TRASPASO A CUENTA AHORRO",
                     "balance": "6318.60"}
    assert last["row"] == 116 and last["date"] == "2026-01-01" and last["balance"] == "5030.52"
    assert last["amount"] == "-1150.00"


def test_checking_balances_match_the_key(checking):
    """The balance after the newest row is 6318.60, and the balance before the oldest row is 6180.52: the amounts of
    the kept rows add up to the difference, which they would not if a repeat were kept or a real row left out."""
    assert checking["rows"][0]["balance"] == "6318.60"
    assert sum(Decimal(r["amount"]) for r in checking["rows"]) == Decimal("6318.60") - Decimal("6180.52")


def test_checking_dates_run_newest_first(checking):
    dates = [r["date"] for r in checking["rows"]]
    assert dates == sorted(dates, reverse=True)


def test_checking_description_whitespace_is_one_line(checking):
    assert all(r["description"] == " ".join(r["description"].split()) for r in checking["rows"])


# ---- the savings account --------------------------------------------------------------------------------------------

def test_savings_is_read_like_checking(savings):
    assert savings["delimiter"] == ";" and savings["columns"] == CHECKING_COLUMNS
    assert savings["date_format"] == "DD/MM/YYYY" and savings["number_format"] == "1.234,56"
    assert savings["newest_first"] is True
    assert savings["dropped"] == [] and savings["same_kept"] == []


def test_savings_has_12_rows_and_the_balances_of_the_key(savings):
    assert len(savings["rows"]) == 12
    assert savings["rows"][0]["date"] == "2026-09-30" and savings["rows"][0]["balance"] == "13353.39"
    assert sum(Decimal(r["amount"]) for r in savings["rows"]) == Decimal("13353.39") - Decimal("6200.00")


def test_savings_dates_reach_from_january_29_to_september_30(savings):
    dates = [r["date"] for r in savings["rows"]]
    assert (min(dates), max(dates)) == ("2026-01-29", "2026-09-30")


# ---- the card ------------------------------------------------------------------------------------------------------

def test_card_is_read_as_the_spec_says(card):
    assert card["delimiter"] == "," and card["header_row"] == 1
    assert card["columns"] == CARD_COLUMNS
    assert card["date_format"] == "YYYY-MM-DD" and card["number_format"] == "1,234.56"
    assert card["newest_first"] is False


def test_card_has_248_transactions_and_nothing_left_out(card):
    assert len(card["rows"]) == 248
    assert card["dropped"] == [] and card["same_kept"] == []
    assert all(r["balance"] is None for r in card["rows"])


def test_card_other_columns_are_ignored(card):
    assert set(card["rows"][0]) == {"row", "date", "amount", "description", "balance"}
    assert card["rows"][0] == {"row": 2, "date": "2026-01-02", "amount": "55.90", "description": "GLOVO*PEDIDO",
                               "balance": None}


def test_card_dates_run_oldest_first(card):
    dates = [r["date"] for r in card["rows"]]
    assert dates == sorted(dates) and dates[0] == "2026-01-02" and dates[-1] == "2026-09-29"


# ---- the budget kept by hand is not an account file ------------------------------------------------------------------

def test_the_hand_kept_budget_has_no_heading_row(adapter):
    with pytest.raises(adapter.NotLoaded) as error:
        reading_of(adapter, "wedding_budget.csv")
    assert str(error.value) == s5.NO_HEADER


# ---- loaded -------------------------------------------------------------------------------------------------------

def test_the_three_files_load_as_they_are(adapter, conn, example_loaded):
    assert [(i["account"], i["transactions"], i["first"], i["last"]) for i in example_loaded] == [
        ("checking_2026", 112, "2026-01-01", "2026-09-29"),
        ("savings_2026", 12, "2026-01-29", "2026-09-30"),
        ("card_2026", 248, "2026-01-02", "2026-09-29")]
    assert [i["sign"] for i in example_loaded] == ["out_negative", "out_negative", "out_positive"]
    assert [i["name"] for i in example_loaded] == ["checking_2026.csv", "savings_2026.csv", "card_2026.csv"]
    assert len(s5.transactions(conn)) == 112 + 12 + 248


def test_checking_balances_still_add_up_after_loading(adapter, conn, example_loaded):
    amounts = [Decimal(r["amount"]) for r in s5.transactions(conn, "checking_2026")]
    assert sum(amounts) == Decimal("138.08")


def test_the_card_is_stored_with_money_out_negative(adapter, conn, example_loaded):
    rows = s5.transactions(conn, "card_2026")
    assert rows[0]["amount"] == "-55.90" and rows[0]["date"] == "2026-01-02"
    september = sum(Decimal(r["amount"]) for r in rows if r["date"].startswith("2026-09"))
    assert september == Decimal("-2373.26")                                  # the key: September card spending


def test_the_savings_file_balances_are_stored_as_read(adapter, conn, example_loaded):
    first = s5.transactions(conn, "savings_2026")[0]
    assert (first["date"], first["amount"], first["balance"], first["row"]) == ("2026-09-30", "22.10", "13353.39", 2)
