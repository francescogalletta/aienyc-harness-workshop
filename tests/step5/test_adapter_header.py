"""SPEC 9.2: the delimiter, the heading row and the roles of the columns."""
import pytest

import step5_helpers as s5
from step5_helpers import csv_text, read_ok, refusal

ROWS = [("2026-03-25", "Coffee", "-3.50"), ("2026-03-26", "Pay", "100.00")]


# ---- the delimiter ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_each_delimiter_is_found(adapter, delimiter):
    reading = read_ok(adapter, csv_text(ROWS, delimiter=delimiter))
    assert reading["delimiter"] == delimiter
    assert [r["description"] for r in reading["rows"]] == ["Coffee", "Pay"]


def test_a_delimiter_inside_quotes_is_not_one(adapter):
    text = 'Date;Description;Amount\n2026-03-25;"Shop; branch 4, till 2";-3.50\n'
    reading = read_ok(adapter, text)
    assert reading["delimiter"] == ";"
    assert reading["rows"][0]["description"] == "Shop; branch 4, till 2"


def test_a_quoted_cell_may_hold_a_line_break_and_counts_as_one_record(adapter):
    text = 'Date,Description,Amount\n2026-03-25,"Two\nlines",-3.50\n2026-03-26,Pay,100.00\n'
    reading = read_ok(adapter, text)
    assert [(r["row"], r["description"]) for r in reading["rows"]] == [(2, "Two lines"), (3, "Pay")]


def test_the_first_delimiter_with_a_heading_row_wins(adapter):
    """The heading is read under ',' only at record 3, and under ';' at record 1: the comma is tried first."""
    text = "Date;Description;Amount\n2026-03-25;x;1\nDate,Description,Amount\n2026-03-26,y,2.00\n"
    reading = read_ok(adapter, text)
    assert reading["delimiter"] == ","
    assert reading["header_row"] == 3
    assert [(r["row"], r["description"]) for r in reading["rows"]] == [(4, "y")]


def test_the_semicolon_comes_before_the_tab_and_the_bar(adapter):
    text = "Date|Description|Amount\n2026-03-25|x|1\nDate;Description;Amount\n2026-03-26;y;2.00\n"
    reading = read_ok(adapter, text)
    assert reading["delimiter"] == ";" and reading["header_row"] == 3


def test_no_delimiter_has_a_heading(adapter):
    assert refusal(adapter, "just some words\nand more words\n") == s5.NO_HEADER
    assert refusal(adapter, "Date Description Amount\n2026-03-25 x 1\n") == s5.NO_HEADER


# ---- the heading row --------------------------------------------------------------------------------------------

def test_the_heading_is_on_row_one_usually(adapter):
    assert read_ok(adapter, csv_text(ROWS))["header_row"] == 1


def test_lines_above_the_heading_row_are_ignored(adapter):
    text = "Statement of account\nIssued 2026-04-01\n" + csv_text(ROWS)
    reading = read_ok(adapter, text)
    assert reading["header_row"] == 3
    assert [r["row"] for r in reading["rows"]] == [4, 5]


def test_the_first_row_with_all_three_roles_is_the_heading_row(adapter):
    text = "Date,Description,Notes\nDate,Description,Amount\n2026-03-25,x,1.00\n"
    reading = read_ok(adapter, text)
    assert reading["header_row"] == 2
    assert [r["row"] for r in reading["rows"]] == [3]


def test_blank_records_count_in_the_search_and_in_the_numbers(adapter):
    text = "\n\n" + csv_text(ROWS)
    reading = read_ok(adapter, text)
    assert reading["header_row"] == 3
    assert [r["row"] for r in reading["rows"]] == [4, 5]


def test_the_heading_may_be_on_record_20_but_not_on_21(adapter):
    on_20 = "\n" * 19 + csv_text(ROWS)
    assert read_ok(adapter, on_20)["header_row"] == 20
    on_21 = "\n" * 20 + csv_text(ROWS)
    assert refusal(adapter, on_21) == s5.NO_HEADER


def test_the_search_looks_at_records_not_lines(adapter):
    """A quoted cell with line breaks is one record, so the heading after 19 such records is on record 20."""
    junk = '"a\nb\nc"\n' * 19
    assert read_ok(adapter, junk + csv_text(ROWS))["header_row"] == 20


def test_a_file_with_only_a_date_and_an_amount_has_no_heading(adapter):
    assert refusal(adapter, "Date,Amount\n2026-03-25,1.00\n") == s5.NO_HEADER


def test_separate_money_in_and_money_out_columns_have_no_amount_column(adapter):
    text = "Date,Description,Debit,Credit\n2026-03-25,x,3.50,\n2026-03-26,y,,100.00\n"
    assert refusal(adapter, text) == s5.NO_HEADER


def test_a_heading_with_other_words_is_no_heading(adapter):
    assert refusal(adapter, "Day,What,Value\n2026-03-25,x,1\n") == s5.NO_HEADER


# ---- the roles --------------------------------------------------------------------------------------------------

def one_heading_file(role, heading):
    header = {"date": "Date", "description": "Description", "amount": "Amount", "balance": "Balance"}
    header[role] = heading
    if role != "balance":
        header.pop("balance")
    rows = [("2026-03-25", "Coffee", "-3.50", "10.00"), ("2026-03-26", "Pay", "100.00", "110.00")]
    keep = 4 if role == "balance" else 3
    return csv_text([r[:keep] for r in rows], header=tuple(header.values()))


@pytest.mark.parametrize("role, heading", [(role, name) for role, names in s5.COLUMN_NAMES.items() for name in names])
def test_every_heading_of_the_vocabulary_finds_its_role(adapter, role, heading):
    for written in (heading, heading.title(), heading.upper()):
        reading = read_ok(adapter, one_heading_file(role, written))
        assert reading["columns"][role] == written
        assert len(reading["rows"]) == 2


@pytest.mark.parametrize("heading, role, expected", [
    ("Fecha Operación", "date", "fecha operacion"),
    ("Fecha de Operación", "date", "fecha de operacion"),
    ("Running Bal.", "balance", "running bal"),
    ("  Transaction-Date ", "date", "transaction date"),
    ("TRANSACTION_AMOUNT", "amount", "transaction amount"),
    ("Descripción", "description", "descripcion"),
    ("Saldo   disponible", "balance", "saldo disponible"),
    ("BOOKING / DATE", "date", "booking date"),
])
def test_a_heading_is_normalised_before_it_is_looked_up(adapter, heading, role, expected):
    reading = read_ok(adapter, one_heading_file(role, heading))
    assert reading["columns"][role] == heading.strip()                      # the heading cell as written, stripped
    assert expected in s5.COLUMN_NAMES[role]


def test_columns_hold_the_heading_cells_as_written_and_stripped(adapter):
    text = "  Fecha ;Concepto; Importe ; Saldo\n25/03/2026;x;1,00;2,00\n"
    reading = read_ok(adapter, text)
    assert reading["columns"] == {"date": "Fecha", "description": "Concepto", "amount": "Importe", "balance": "Saldo"}


@pytest.mark.parametrize("heading", ["Amount (EUR)", "Amount in euros", "Total amount", "Date of birth", "Amounts"])
def test_a_heading_that_only_contains_a_name_is_not_the_name(adapter, heading):
    text = csv_text([("2026-03-25", "x", "1.00")], header=("Date", "Description", heading))
    if heading.startswith("Date"):
        text = csv_text([("2026-03-25", "x", "1.00")], header=(heading, "Description", "Amount"))
    assert refusal(adapter, text) == s5.NO_HEADER


def test_the_role_goes_to_the_name_that_comes_first_in_the_list(adapter):
    """`date` comes before `posting date` in the list, so the later column is the date column."""
    text = csv_text([("2026-03-25", "2026-03-20", "x", "1.00")], header=("Posting Date", "Date", "Description", "Amount"))
    reading = read_ok(adapter, text)
    assert reading["columns"]["date"] == "Date"
    assert reading["rows"][0]["date"] == "2026-03-20"


def test_description_names_in_the_order_of_the_list(adapter):
    """`payee` comes before `memo` in the list."""
    text = csv_text([("2026-03-25", "the memo", "the payee", "1.00")], header=("Date", "Memo", "Payee", "Amount"))
    reading = read_ok(adapter, text)
    assert reading["columns"]["description"] == "Payee" and reading["rows"][0]["description"] == "the payee"


def test_amount_names_in_the_order_of_the_list(adapter):
    text = csv_text([("2026-03-25", "x", "2.00", "1.00")], header=("Date", "Description", "Importe", "Amount"))
    reading = read_ok(adapter, text)
    assert reading["columns"]["amount"] == "Amount" and reading["rows"][0]["amount"] == "1.00"


def test_balance_names_in_the_order_of_the_list(adapter):
    text = csv_text([("2026-03-25", "x", "1.00", "9.00", "8.00")],
                    header=("Date", "Description", "Amount", "Saldo", "Balance"))
    reading = read_ok(adapter, text)
    assert reading["columns"]["balance"] == "Balance" and reading["rows"][0]["balance"] == "8.00"


def test_between_cells_with_the_same_name_the_leftmost_wins(adapter):
    text = csv_text([("2026-03-25", "2026-04-01", "x", "1.00")], header=("Date", "date", "Description", "Amount"))
    reading = read_ok(adapter, text)
    assert reading["columns"]["date"] == "Date" and reading["rows"][0]["date"] == "2026-03-25"


def test_names_that_differ_only_in_case_or_marks_are_the_same_name(adapter):
    text = csv_text([("2026-03-25", "2026-04-01", "x", "1.00")], header=("DATE", "Dáte", "Description", "Amount"))
    reading = read_ok(adapter, text)
    assert reading["columns"]["date"] == "DATE"


def test_other_columns_are_ignored(adapter):
    text = csv_text([("2026-03-25", "x", "1.00", "EUR", "12.00", "USD", "food")],
                    header=("Date", "Description", "Amount", "Currency", "Original", "Original currency", "Category"))
    reading = read_ok(adapter, text)
    assert reading["rows"] == [{"row": 2, "date": "2026-03-25", "amount": "1.00", "description": "x", "balance": None}]


def test_the_columns_may_come_in_any_order(adapter):
    text = csv_text([("1.00", "x", "5.00", "2026-03-25")], header=("Amount", "Description", "Balance", "Date"))
    assert read_ok(adapter, text)["rows"] == [
        {"row": 2, "date": "2026-03-25", "amount": "1.00", "description": "x", "balance": "5.00"}]


def test_balance_is_optional_and_null_without_it(adapter):
    assert read_ok(adapter, csv_text(ROWS))["columns"]["balance"] is None
