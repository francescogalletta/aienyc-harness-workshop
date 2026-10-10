"""SPEC 9.2: the delimiter, the heading row and the roles of the columns."""
import pytest

import step5_helpers as s5
from step5_helpers import csv_text, read_ok, refusal

ROWS = [("2026-03-25", "Coffee", "-3.50"), ("2026-03-26", "Pay", "100.00")]


# ---- the delimiter ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("delimiter", [";", "\t"])
def test_each_delimiter_is_found(adapter, delimiter):
    reading = read_ok(adapter, csv_text(ROWS, delimiter=delimiter))
    assert reading["delimiter"] == delimiter
    assert [r["description"] for r in reading["rows"]] == ["Coffee", "Pay"]


def test_a_delimiter_inside_quotes_is_not_one(adapter):
    text = 'Date;Description;Amount\n2026-03-25;"Shop; branch 4, till 2";-3.50\n'
    reading = read_ok(adapter, text)
    assert reading["delimiter"] == ";"
    assert reading["rows"][0]["description"] == "Shop; branch 4, till 2"








def test_no_delimiter_has_a_heading(adapter):
    assert refusal(adapter, "just some words\nand more words\n") == s5.NO_HEADER
    assert refusal(adapter, "Date Description Amount\n2026-03-25 x 1\n") == s5.NO_HEADER


# ---- the heading row --------------------------------------------------------------------------------------------















def test_separate_money_in_and_money_out_columns_have_no_amount_column(adapter):
    text = "Date,Description,Debit,Credit\n2026-03-25,x,3.50,\n2026-03-26,y,,100.00\n"
    assert refusal(adapter, text) == s5.NO_HEADER




# ---- the roles --------------------------------------------------------------------------------------------------

def one_heading_file(role, heading):
    header = {"date": "Date", "description": "Description", "amount": "Amount", "balance": "Balance"}
    header[role] = heading
    if role != "balance":
        header.pop("balance")
    rows = [("2026-03-25", "Coffee", "-3.50", "10.00"), ("2026-03-26", "Pay", "100.00", "110.00")]
    keep = 4 if role == "balance" else 3
    return csv_text([r[:keep] for r in rows], header=tuple(header.values()))
























def test_the_columns_may_come_in_any_order(adapter):
    text = csv_text([("1.00", "x", "5.00", "2026-03-25")], header=("Amount", "Description", "Balance", "Date"))
    assert read_ok(adapter, text)["rows"] == [
        {"row": 2, "date": "2026-03-25", "amount": "1.00", "description": "x", "balance": "5.00"}]


