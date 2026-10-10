"""SPEC 9.2, rule 4: the records after the heading row, and rule 8: the order."""
import pytest

import step5_helpers as s5
from step5_helpers import csv_text, read_ok, refusal

HEADER = "Date,Description,Amount\n"


def rows(reading):
    return [(r["row"], r["description"]) for r in reading["rows"]]


# ---- blank records ----------------------------------------------------------------------------------------------

def test_blank_records_are_skipped_and_not_reported(adapter):
    text = HEADER + "2026-03-25,a,1.00\n\n,,\n  , ,  \n2026-03-26,b,2.00\n\n"
    reading = read_ok(adapter, text)
    assert rows(reading) == [(2, "a"), (6, "b")]                       # blank records count in the numbers
    assert reading["dropped"] == []


def test_a_record_of_empty_cells_in_a_file_with_more_columns_is_blank(adapter):
    text = "Date;Description;Amount;Balance\n2026-03-25;a;1,00;5,00\n; ;;\n2026-03-26;b;2,00;7,00\n"
    reading = read_ok(adapter, text)
    assert rows(reading) == [(2, "a"), (4, "b")] and reading["dropped"] == []


# ---- repeated heading rows --------------------------------------------------------------------------------------

def test_a_repeated_heading_row_is_left_out_and_reported(adapter):
    text = HEADER + "2026-03-25,a,1.00\nDate,Description,Amount\n2026-03-26,b,2.00\n"
    reading = read_ok(adapter, text)
    assert rows(reading) == [(2, "a"), (4, "b")]
    assert reading["dropped"] == [{"row": 3, "reason": "repeated header"}]


def test_a_repeated_heading_row_may_differ_in_white_space(adapter):
    text = HEADER + "2026-03-25,a,1.00\n  Date , Description,Amount  \n2026-03-26,b,2.00\n"
    assert read_ok(adapter, text)["dropped"] == [{"row": 3, "reason": "repeated header"}]


def test_a_repeated_heading_row_is_compared_with_the_case_kept(adapter):
    text = HEADER + "2026-03-25,a,1.00\ndate,description,amount\n2026-03-26,b,2.00\n"
    assert refusal(adapter, text) == s5.BAD_DATES.format(row=3, cell="date")


def test_a_row_with_the_heading_cells_and_more_is_not_a_repeated_heading(adapter):
    text = HEADER + "2026-03-25,a,1.00\nDate,Description,Amount,extra\n2026-03-26,b,2.00\n"
    assert refusal(adapter, text) == s5.BAD_DATES.format(row=3, cell="Date")


def test_several_repeated_headings_and_the_dropped_list_is_in_row_order(adapter):
    text = (HEADER + "2026-03-25,a,1.00\n" + HEADER + "2026-03-26,b,2.00\n" + HEADER)
    reading = read_ok(adapter, text)
    assert rows(reading) == [(2, "a"), (4, "b")]
    assert reading["dropped"] == [{"row": 3, "reason": "repeated header"}, {"row": 5, "reason": "repeated header"}]


def test_only_headings_that_repeat_the_whole_heading_row_are_dropped(adapter):
    """The heading row has 4 cells; the repeat has 4 equal cells. Rows are numbered from the start of the file."""
    text = "Fecha;Concepto;Importe;Saldo\n25/03/2026;a;1,00;5,00\nFecha;Concepto;Importe;Saldo\n26/03/2026;b;2,00;7,00\n"
    reading = read_ok(adapter, text)
    assert reading["dropped"] == [{"row": 3, "reason": "repeated header"}]
    assert rows(reading) == [(2, "a"), (4, "b")]


# ---- too short --------------------------------------------------------------------------------------------------

def test_a_row_with_no_cell_at_the_place_of_a_found_column_is_a_short_row(adapter):
    text = HEADER + "2026-03-25,a,1.00\n2026-03-26,b\n"
    assert refusal(adapter, text) == s5.SHORT_ROW.format(row=3)


def test_the_first_short_record_is_the_one_reported(adapter):
    text = HEADER + "2026-03-25,a,1.00\n2026-03-26,b\n2026-03-27\n"
    assert refusal(adapter, text) == s5.SHORT_ROW.format(row=3)


def test_the_balance_column_counts_when_it_was_found(adapter):
    text = "Date,Description,Amount,Balance\n2026-03-25,a,1.00,5.00\n2026-03-26,b,2.00\n"
    assert refusal(adapter, text) == s5.SHORT_ROW.format(row=3)


def test_a_missing_balance_cell_is_fine_when_there_is_no_balance_column(adapter):
    reading = read_ok(adapter, HEADER + "2026-03-25,a,1.00\n2026-03-26,b,2.00,extra,more\n")
    assert rows(reading) == [(2, "a"), (3, "b")]


def test_a_short_row_is_refused_before_the_dates_are_looked_at(adapter):
    text = HEADER + "not a date,a,1.00\n2026-03-26,b\n"
    assert refusal(adapter, text) == s5.SHORT_ROW.format(row=3)


def test_a_row_short_only_in_a_column_that_is_not_found_is_fine(adapter):
    text = "Date,Description,Amount,Category\n2026-03-25,a,1.00\n"
    assert rows(read_ok(adapter, text)) == [(2, "a")]


def test_the_columns_are_places_in_the_heading_row_not_the_first_cells(adapter):
    text = "Notes,Date,Description,Amount\nn,2026-03-25,a\n"
    assert refusal(adapter, text) == s5.SHORT_ROW.format(row=2)


# ---- no rows ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [HEADER, HEADER + "\n\n", HEADER + ",,\n", HEADER + HEADER + HEADER])
def test_no_data_row_is_no_rows(adapter, text):
    assert refusal(adapter, text) == s5.NO_ROWS


# ---- the cells of a data row ------------------------------------------------------------------------------------

def test_the_cells_are_stripped_and_the_description_is_made_one_line(adapter):
    text = 'Date,Description,Amount\n  2026-03-25 ,"  Shop \t  one\n two  ", -3.50 \n'
    [row] = read_ok(adapter, text)["rows"]
    assert row == {"row": 2, "date": "2026-03-25", "amount": "-3.50", "description": "Shop one two", "balance": None}


def test_an_empty_description_is_allowed(adapter):
    [row] = read_ok(adapter, HEADER + "2026-03-25,,1.00\n")["rows"]
    assert row["description"] == ""


def test_an_empty_balance_cell_is_no_balance(adapter):
    text = "Date,Description,Amount,Balance\n2026-03-25,a,1.00,\n2026-03-26,b,2.00, \n2026-03-27,c,3.00,6.00\n"
    reading = read_ok(adapter, text)
    assert [r["balance"] for r in reading["rows"]] == [None, None, "6.00"]
    assert reading["columns"]["balance"] == "Balance"


def test_rows_are_kept_in_file_order(adapter):
    text = HEADER + "2026-03-27,c,3.00\n2026-03-25,a,1.00\n2026-03-26,b,2.00\n"
    assert rows(read_ok(adapter, text)) == [(2, "c"), (3, "a"), (4, "b")]


# ---- the order of the file --------------------------------------------------------------------------------------

@pytest.mark.parametrize("dates, newest_first", [
    (["2026-03-27", "2026-03-26", "2026-03-25"], True),
    (["2026-03-25", "2026-03-26", "2026-03-27"], False),
    (["2026-03-25", "2026-03-25"], False),                      # equal dates: not later
    (["2026-03-25"], False),
    (["2026-03-27", "2026-03-30", "2026-03-26"], True),         # only the first and the last kept row count
    (["2026-03-25", "2026-03-20", "2026-03-27"], False),
])
def test_newest_first_compares_the_first_and_the_last_kept_row(adapter, dates, newest_first):
    text = csv_text([(d, "x", "1.00") for d in dates])
    assert read_ok(adapter, text)["newest_first"] is newest_first


def test_newest_first_looks_at_kept_rows_only(adapter):
    """The last record is a repeated heading, which is left out; the last kept row is the one before it."""
    text = HEADER + "2026-03-27,a,1.00\n2026-03-26,b,2.00\n" + HEADER
    assert read_ok(adapter, text)["newest_first"] is True
