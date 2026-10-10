"""SPEC 9.2, rule 6: the number formats of the amount and balance cells."""
import pytest

import step5_helpers as s5
from step5_helpers import csv_text, read_ok, refusal

POINT, COMMA = "1,234.56", "1.234,56"


def quoted(cell):
    return '"' + cell + '"'                                  # a cell may hold the delimiter: 1.234,56


def amounts_file(*cells):
    return csv_text([("2026-03-25", "x", quoted(cell)) for cell in cells])


def balances_file(*pairs):
    return csv_text([("2026-03-25", "x", quoted(amount), quoted(balance)) for amount, balance in pairs],
                    header=("Date", "Description", "Amount", "Balance"))


def read_amounts(adapter, *cells):
    reading = read_ok(adapter, amounts_file(*cells))
    return reading["number_format"], [r["amount"] for r in reading["rows"]]


# ---- the point format ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cell, value", [("1,234.56", "1234.56")])
def test_the_point_format_reads_these(adapter, cell, value):
    assert read_amounts(adapter, cell) == (POINT, [value])


@pytest.mark.parametrize("cell, value", [("1.234,56", "1234.56")])
def test_the_comma_format_reads_these(adapter, cell, value):
    assert read_amounts(adapter, cell) == (COMMA, [value])








# ---- ambiguity ------------------------------------------------------------------------------------------------------









# ---- plain cells ----------------------------------------------------------------------------------------------------



# ---- cells nothing reads --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cell", ["abc"])
def test_cells_that_no_format_reads_are_bad_numbers(adapter, cell):
    assert refusal(adapter, amounts_file("1.00", cell)) == s5.BAD_NUMBERS.format(row=3, cell=cell.strip())






# ---- which cell is blamed -------------------------------------------------------------------------------------------







# ---- amounts and balances are read together -------------------------------------------------------------------------







def test_a_balance_can_settle_an_ambiguous_amount(adapter):
    reading = read_ok(adapter, balances_file(("1,150", "2,300.50")))
    assert reading["number_format"] == POINT and reading["rows"][0]["amount"] == "1150"
















