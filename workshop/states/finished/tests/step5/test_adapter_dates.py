"""SPEC 9.2, rule 5: the date formats."""
import pytest

import step5_helpers as s5
from step5_helpers import csv_text, read_ok, refusal


def dates_file(*cells, header=("Date", "Description", "Amount")):
    return csv_text([(cell, "x", "1.00") for cell in cells], header=header)


# ---- each format reads its dates ------------------------------------------------------------------------------

@pytest.mark.parametrize("cell, display, expected", [("2026-03-25", "YYYY-MM-DD", "2026-03-25"), ("03/25/2026", "MM/DD/YYYY", "2026-03-25")])
def test_each_format_is_found_and_the_date_is_written_year_month_day(adapter, cell, display, expected):
    reading = read_ok(adapter, dates_file(cell))
    assert reading["date_format"] == display
    assert reading["rows"][0]["date"] == expected






# ---- every cell has to fit ------------------------------------------------------------------------------------

def test_a_day_above_twelve_settles_day_first_against_month_first(adapter):
    reading = read_ok(adapter, dates_file("03/04/2026", "25/04/2026"))
    assert reading["date_format"] == "DD/MM/YYYY"
    assert [r["date"] for r in reading["rows"]] == ["2026-04-03", "2026-04-25"]






def test_a_single_ambiguous_date_is_refused(adapter):
    text = dates_file("03/04/2026")
    assert refusal(adapter, text) == s5.AMBIGUOUS_DATES.format(first="DD/MM/YYYY", second="MM/DD/YYYY")






def test_a_cell_that_no_format_reads_is_refused_with_that_cell(adapter):
    assert refusal(adapter, dates_file("2026-03-25", "yesterday")) == s5.BAD_DATES.format(row=3, cell="yesterday")








# ---- which cell is shown ---------------------------------------------------------------------------------------









# ---- which rows count ------------------------------------------------------------------------------------------





