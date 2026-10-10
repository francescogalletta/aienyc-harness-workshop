"""SPEC 9.2, rule 5: the date formats."""
import pytest

import step5_helpers as s5
from step5_helpers import csv_text, read_ok, refusal


def dates_file(*cells, header=("Date", "Description", "Amount")):
    return csv_text([(cell, "x", "1.00") for cell in cells], header=header)


# ---- each format reads its dates ------------------------------------------------------------------------------

@pytest.mark.parametrize("cell, display, expected", [
    ("2026-03-25", "YYYY-MM-DD", "2026-03-25"),
    ("25/03/2026", "DD/MM/YYYY", "2026-03-25"),
    ("03/25/2026", "MM/DD/YYYY", "2026-03-25"),
    ("25.03.2026", "DD.MM.YYYY", "2026-03-25"),
    ("25-03-2026", "DD-MM-YYYY", "2026-03-25"),
    ("2026/03/25", "YYYY/MM/DD", "2026-03-25"),
])
def test_each_format_is_found_and_the_date_is_written_year_month_day(adapter, cell, display, expected):
    reading = read_ok(adapter, dates_file(cell))
    assert reading["date_format"] == display
    assert reading["rows"][0]["date"] == expected


def test_a_format_reads_what_strptime_reads(adapter):
    """`strptime` accepts a day or a month written without its zero."""
    reading = read_ok(adapter, dates_file("2026-3-5", "2026-03-06"))
    assert [r["date"] for r in reading["rows"]] == ["2026-03-05", "2026-03-06"]


def test_cells_are_stripped_before_they_are_read(adapter):
    reading = read_ok(adapter, 'Date,Description,Amount\n"  2026-03-25 ",x,1.00\n')
    assert reading["rows"][0]["date"] == "2026-03-25"


# ---- every cell has to fit ------------------------------------------------------------------------------------

def test_a_day_above_twelve_settles_day_first_against_month_first(adapter):
    reading = read_ok(adapter, dates_file("03/04/2026", "25/04/2026"))
    assert reading["date_format"] == "DD/MM/YYYY"
    assert [r["date"] for r in reading["rows"]] == ["2026-04-03", "2026-04-25"]


def test_a_second_number_above_twelve_settles_month_first(adapter):
    reading = read_ok(adapter, dates_file("03/04/2026", "04/25/2026"))
    assert reading["date_format"] == "MM/DD/YYYY"
    assert [r["date"] for r in reading["rows"]] == ["2026-03-04", "2026-04-25"]


def test_dates_that_fit_two_formats_and_give_the_same_dates_use_the_first_fitting_one(adapter):
    reading = read_ok(adapter, dates_file("05/05/2026", "12/12/2026"))
    assert reading["date_format"] == "DD/MM/YYYY"
    assert [r["date"] for r in reading["rows"]] == ["2026-05-05", "2026-12-12"]


def test_a_single_ambiguous_date_is_refused(adapter):
    text = dates_file("03/04/2026")
    assert refusal(adapter, text) == s5.AMBIGUOUS_DATES.format(first="DD/MM/YYYY", second="MM/DD/YYYY")


def test_ambiguity_is_refused_when_only_some_cells_differ(adapter):
    text = dates_file("05/05/2026", "03/04/2026", "01/01/2026")
    assert refusal(adapter, text) == s5.AMBIGUOUS_DATES.format(first="DD/MM/YYYY", second="MM/DD/YYYY")


def test_dates_are_not_ambiguous_when_separators_tell_the_formats_apart(adapter):
    for cell, display in (("03.04.2026", "DD.MM.YYYY"), ("03-04-2026", "DD-MM-YYYY"), ("2026/03/04", "YYYY/MM/DD"),
                          ("2026-03-04", "YYYY-MM-DD")):
        assert read_ok(adapter, dates_file(cell))["date_format"] == display


def test_a_cell_that_no_format_reads_is_refused_with_that_cell(adapter):
    assert refusal(adapter, dates_file("2026-03-25", "yesterday")) == s5.BAD_DATES.format(row=3, cell="yesterday")


@pytest.mark.parametrize("cell", ["31/02/2026", "2026-13-01", "25/03/26", "2026-03-25 10:00", "25 March 2026", "",
                                  "2026-03", "3/25/2026x"])
def test_cells_that_are_not_dates_are_bad_dates(adapter, cell):
    assert refusal(adapter, dates_file("2026-03-24", cell)) == s5.BAD_DATES.format(row=3, cell=cell)


def test_the_cell_is_shown_as_written_but_stripped(adapter):
    text = 'Date,Description,Amount\n2026-03-24,x,1.00\n"  tomorrow  ",x,1.00\n'
    assert refusal(adapter, text) == s5.BAD_DATES.format(row=3, cell="tomorrow")


def test_the_row_number_counts_from_the_start_of_the_file(adapter):
    text = "Statement\n" + dates_file("2026-03-24", "oops")
    assert refusal(adapter, text) == s5.BAD_DATES.format(row=4, cell="oops")


# ---- which cell is shown ---------------------------------------------------------------------------------------

def test_the_cell_shown_is_one_the_format_with_the_fewest_unread_cells_does_not_read(adapter):
    """Two ISO dates and one with slashes: the ISO format has one unread cell, the others two."""
    text = dates_file("2026-03-24", "25/03/2026", "2026-03-26")
    assert refusal(adapter, text) == s5.BAD_DATES.format(row=3, cell="25/03/2026")


def test_the_majority_format_decides_which_cell_is_blamed(adapter):
    text = dates_file("25/03/2026", "26/03/2026", "2026-03-27")
    assert refusal(adapter, text) == s5.BAD_DATES.format(row=4, cell="2026-03-27")


def test_on_a_tie_the_earlier_format_decides(adapter):
    """One slash date and one ISO date: YYYY-MM-DD (earlier in the list) leaves the slash date unread."""
    assert refusal(adapter, dates_file("25/03/2026", "2026-03-26")) == s5.BAD_DATES.format(row=2, cell="25/03/2026")
    assert refusal(adapter, dates_file("2026-03-26", "25/03/2026")) == s5.BAD_DATES.format(row=3, cell="25/03/2026")


def test_the_first_unread_cell_in_row_order_is_shown(adapter):
    text = dates_file("2026-03-24", "bad one", "bad two", "2026-03-25")
    assert refusal(adapter, text) == s5.BAD_DATES.format(row=3, cell="bad one")


# ---- which rows count ------------------------------------------------------------------------------------------

def test_a_repeated_heading_row_is_not_a_date_cell(adapter):
    text = dates_file("2026-03-24") + "Date,Description,Amount\n" + "2026-03-25,x,1.00\n"
    assert read_ok(adapter, text)["date_format"] == "YYYY-MM-DD"


def test_dates_are_read_before_amounts(adapter):
    text = csv_text([("nope", "x", "also nope")])
    assert refusal(adapter, text) == s5.BAD_DATES.format(row=2, cell="nope")


def test_a_short_row_is_refused_before_dates(adapter):
    text = "Date,Description,Amount\nnope,x,1.00\n2026-03-25,x\n"
    assert refusal(adapter, text) == s5.SHORT_ROW.format(row=3)
