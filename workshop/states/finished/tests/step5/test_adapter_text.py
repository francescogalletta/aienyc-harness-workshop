"""SPEC 9.2: the names of accounts, the constants of the adapter, and the first rule of `read_table`: the text."""
import pytest

import step5_helpers as s5
from step5_helpers import read_ok, refusal


# ---- the constants ----------------------------------------------------------------------------------------------









# ---- account names ----------------------------------------------------------------------------------------------







# ---- text: EMPTY and NOT_TEXT -----------------------------------------------------------------------------------



@pytest.mark.parametrize("data", [b"Date,Description,Amount\n2026-03-25,a\x00b,1.00\n"])
def test_bytes_that_are_not_text(adapter, data):
    assert refusal(adapter, data) == s5.NOT_TEXT




def test_windows_1252_is_the_second_choice(adapter):
    reading = read_ok(adapter, b"Date,Description,Amount\n2026-03-25,Caf\xe9 \x80,-3.50\n")
    assert reading["rows"][0]["description"] == "Café €"








