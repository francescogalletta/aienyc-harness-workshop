"""SPEC 9.2, rule 7: repeated rows, with and without a balance column."""
from step5_helpers import csv_text, read_ok

WITH_BALANCE = ("Date", "Description", "Amount", "Balance")


def with_balance(*rows):
    return csv_text(rows, header=WITH_BALANCE)


def without_balance(*rows):
    return csv_text(rows)


def numbers(reading):
    return [r["row"] for r in reading["rows"]]


REPEAT = {"reason": "repeated row"}


# ---- with a balance column -------------------------------------------------------------------------------------------

def test_a_row_equal_to_an_earlier_one_in_every_field_is_left_out(adapter):
    reading = read_ok(adapter, with_balance(("2026-03-25", "Shop", "-5.00", "95.00"),
                                            ("2026-03-26", "Pay", "10.00", "105.00"),
                                            ("2026-03-25", "Shop", "-5.00", "95.00")))
    assert numbers(reading) == [2, 3]
    assert reading["dropped"] == [{"row": 4, **REPEAT}]
    assert reading["same_kept"] == []






def test_a_different_balance_makes_a_real_second_payment(adapter):
    reading = read_ok(adapter, with_balance(("2026-03-25", "Shop", "-5.00", "95.00"),
                                            ("2026-03-25", "Shop", "-5.00", "90.00")))
    assert numbers(reading) == [2, 3] and reading["dropped"] == []






















# ---- without a balance column ----------------------------------------------------------------------------------------

def test_nothing_is_left_out_without_a_balance_column(adapter):
    row = ("2026-03-25", "Shop", "-5.00")
    reading = read_ok(adapter, without_balance(row, row))
    assert numbers(reading) == [2, 3] and reading["dropped"] == []












