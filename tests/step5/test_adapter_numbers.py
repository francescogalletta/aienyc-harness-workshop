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

@pytest.mark.parametrize("cell, value", [
    ("1234.56", "1234.56"), ("1,234.56", "1234.56"), ("-1,234.56", "-1234.56"), ("+12.5", "12.5"),
    ("1,234,567.89", "1234567.89"), ("0.50", "0.50"), ("12.50", "12.50"), ("100", "100"), ("-3.5000", "-3.5000"),
    ("007.50", "7.50"), ("12345678901234567890.123", "12345678901234567890.123"),
])
def test_the_point_format_reads_these(adapter, cell, value):
    assert read_amounts(adapter, cell) == (POINT, [value])


@pytest.mark.parametrize("cell, value", [
    ("1.234,56", "1234.56"), ("-1.234,56", "-1234.56"), ("+12,5", "12.5"), ("1.234.567,89", "1234567.89"),
    ("0,50", "0.50"), ("12,50", "12.50"), ("1234,56", "1234.56"), ("3,5000", "3.5000"), ("1,23", "1.23"),
    ("1.234,5", "1234.5"),
])
def test_the_comma_format_reads_these(adapter, cell, value):
    assert read_amounts(adapter, cell) == (COMMA, [value])


def test_whole_numbers_fit_both_and_the_point_format_is_used(adapter):
    assert read_amounts(adapter, "5", "-10", "300") == (POINT, ["5", "-10", "300"])


def test_a_value_keeps_its_decimals_as_written(adapter):
    assert read_amounts(adapter, "5.10", "2.000") == (POINT, ["5.10", "2.000"])


def test_a_plus_sign_is_not_kept(adapter):
    assert read_amounts(adapter, "+5.00", "-5.00")[1] == ["5.00", "-5.00"]


# ---- ambiguity ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cell", ["1,150", "1.150", "1,234", "2.500", "12,345", "-1,150"])
def test_a_lone_number_with_a_group_of_three_is_ambiguous(adapter, cell):
    assert refusal(adapter, amounts_file(cell)) == s5.AMBIGUOUS_NUMBERS


def test_the_ambiguity_goes_away_when_another_cell_settles_it(adapter):
    assert read_amounts(adapter, "1,150", "2,300.50") == (POINT, ["1150", "2300.50"])
    assert read_amounts(adapter, "1,150", "2.300,50") == (COMMA, ["1.150", "2300.50"])


def test_two_ambiguous_cells_stay_ambiguous(adapter):
    assert refusal(adapter, amounts_file("1,150", "2,300")) == s5.AMBIGUOUS_NUMBERS


def test_both_formats_fitting_with_equal_values_is_not_ambiguous(adapter):
    assert read_amounts(adapter, "1", "22", "333") == (POINT, ["1", "22", "333"])


# ---- plain cells ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cell, number_format, value", [
    ("$5.00", POINT, "5.00"), ("€ 5.00", POINT, "5.00"), ("5.00 £", POINT, "5.00"), ("-€5.00", POINT, "-5.00"),
    ("€-5.00", POINT, "-5.00"), ("$ 1,234.50", POINT, "1234.50"), ("1.234,50 €", COMMA, "1234.50"),
    ("1 234,50", COMMA, "1234.50"), ("1 234,50", COMMA, "1234.50"), ("1 234.50", POINT, "1234.50"),
    ("\t5.00\t", POINT, "5.00"), ("1 234.50", POINT, "1234.50"),
])
def test_white_space_and_currency_signs_are_removed_first(adapter, cell, number_format, value):
    assert read_amounts(adapter, cell) == (number_format, [value])


# ---- cells nothing reads --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cell", ["abc", "(5.00)", "5.00-", "EUR 5.00", "5,00 EUR", "12%", ".5", "5.", "1e3", "--5",
                                  "1,2,3", "12,34.5", "1.2.3", "5.00.00", "NaN", "5 .00,"])
def test_cells_that_no_format_reads_are_bad_numbers(adapter, cell):
    assert refusal(adapter, amounts_file("1.00", cell)) == s5.BAD_NUMBERS.format(row=3, cell=cell.strip())


def test_an_empty_amount_cell_is_unread(adapter):
    assert refusal(adapter, amounts_file("1.00", "")) == s5.BAD_NUMBERS.format(row=3, cell="")


def test_the_cell_in_the_message_is_as_written_but_stripped(adapter):
    text = 'Date,Description,Amount\n2026-03-25,x,"  EUR 5  "\n'
    assert refusal(adapter, text) == s5.BAD_NUMBERS.format(row=2, cell="EUR 5")


# ---- which cell is blamed -------------------------------------------------------------------------------------------

def test_the_format_with_fewer_unread_cells_decides_the_blamed_cell(adapter):
    text = amounts_file("1.234,56", "2.345,67", "3,456.78")
    assert refusal(adapter, text) == s5.BAD_NUMBERS.format(row=4, cell="3,456.78")
    text = amounts_file("1,234.56", "2,345.67", "3.456,78")
    assert refusal(adapter, text) == s5.BAD_NUMBERS.format(row=4, cell="3.456,78")


def test_on_a_tie_the_point_format_decides(adapter):
    assert refusal(adapter, amounts_file("1,234.56", "2.345,67")) == s5.BAD_NUMBERS.format(row=3, cell="2.345,67")
    assert refusal(adapter, amounts_file("2.345,67", "1,234.56")) == s5.BAD_NUMBERS.format(row=2, cell="2.345,67")


def test_the_first_unread_cell_in_row_order_is_blamed(adapter):
    text = amounts_file("1.00", "oops", "worse", "2.00")
    assert refusal(adapter, text) == s5.BAD_NUMBERS.format(row=3, cell="oops")


# ---- amounts and balances are read together -------------------------------------------------------------------------

def test_balances_are_read_with_the_amounts(adapter):
    reading = read_ok(adapter, balances_file(("-5.00", "1,000.00"), ("10.00", "1,005.00")))
    assert reading["number_format"] == POINT
    assert [(r["amount"], r["balance"]) for r in reading["rows"]] == [("-5.00", "1000.00"), ("10.00", "1005.00")]


def test_a_balance_in_the_comma_format_with_amounts_in_the_point_format_is_refused(adapter):
    text = balances_file(("1.50", "1.234,56"), ("2.50", "2,000.00"))
    assert refusal(adapter, text) == s5.BAD_NUMBERS.format(row=2, cell="1.234,56")


def test_a_balance_can_make_a_whole_number_amount_ambiguous(adapter):
    assert refusal(adapter, balances_file(("5", "1,150"))) == s5.AMBIGUOUS_NUMBERS


def test_a_balance_can_settle_an_ambiguous_amount(adapter):
    reading = read_ok(adapter, balances_file(("1,150", "2,300.50")))
    assert reading["number_format"] == POINT and reading["rows"][0]["amount"] == "1150"


def test_in_a_row_the_amount_is_blamed_before_the_balance(adapter):
    text = balances_file(("1.00", "2.00"), ("x1", "y2"))
    assert refusal(adapter, text) == s5.BAD_NUMBERS.format(row=3, cell="x1")


def test_a_bad_balance_is_blamed_when_the_amount_is_fine(adapter):
    text = balances_file(("1.00", "2.00"), ("3.00", "y2"))
    assert refusal(adapter, text) == s5.BAD_NUMBERS.format(row=3, cell="y2")


def test_an_earlier_rows_balance_comes_before_a_later_rows_amount(adapter):
    text = balances_file(("1.00", "oops"), ("bad", "2.00"))
    assert refusal(adapter, text) == s5.BAD_NUMBERS.format(row=2, cell="oops")


def test_an_empty_balance_cell_is_not_read_and_is_no_balance(adapter):
    reading = read_ok(adapter, balances_file(("1.00", ""), ("2.00", "3.00")))
    assert [r["balance"] for r in reading["rows"]] == [None, "3.00"]


def test_an_empty_balance_does_not_take_part_in_ambiguity(adapter):
    reading = read_ok(adapter, balances_file(("1.50", ""), ("2.50", "")))
    assert reading["number_format"] == POINT


def test_a_balance_column_that_is_empty_everywhere_is_still_a_found_column(adapter):
    reading = read_ok(adapter, balances_file(("1.00", ""), ("2.00", "")))
    assert reading["columns"]["balance"] == "Balance"


def test_a_column_that_is_not_the_amount_or_the_balance_is_not_read(adapter):
    text = csv_text([("2026-03-25", "x", "1.00", "not a number", "also not")],
                    header=("Date", "Description", "Amount", "Category", "Other"))
    assert read_ok(adapter, text)["rows"][0]["amount"] == "1.00"


def test_numbers_are_read_after_dates_and_before_repeated_rows(adapter):
    text = balances_file(("bad", "1.00"), ("bad", "1.00"))
    assert refusal(adapter, text) == s5.BAD_NUMBERS.format(row=2, cell="bad")
