"""SPEC 9.2, rule 4: the records after the heading row, and rule 8: the order."""
import pytest

import step5_helpers as s5
from step5_helpers import csv_text, read_ok, refusal

HEADER = "Date,Description,Amount\n"


def rows(reading):
    return [(r["row"], r["description"]) for r in reading["rows"]]


# ---- blank records ----------------------------------------------------------------------------------------------





# ---- repeated heading rows --------------------------------------------------------------------------------------

def test_a_repeated_heading_row_is_left_out_and_reported(adapter):
    text = HEADER + "2026-03-25,a,1.00\nDate,Description,Amount\n2026-03-26,b,2.00\n"
    reading = read_ok(adapter, text)
    assert rows(reading) == [(2, "a"), (4, "b")]
    assert reading["dropped"] == [{"row": 3, "reason": "repeated header"}]












# ---- too short --------------------------------------------------------------------------------------------------















# ---- no rows ----------------------------------------------------------------------------------------------------



# ---- the cells of a data row ------------------------------------------------------------------------------------









# ---- the order of the file --------------------------------------------------------------------------------------

@pytest.mark.parametrize("dates, newest_first", [(["2026-03-27", "2026-03-26", "2026-03-25"], True)])
def test_newest_first_compares_the_first_and_the_last_kept_row(adapter, dates, newest_first):
    text = csv_text([(d, "x", "1.00") for d in dates])
    assert read_ok(adapter, text)["newest_first"] is newest_first


