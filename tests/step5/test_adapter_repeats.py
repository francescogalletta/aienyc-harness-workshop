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


def test_every_later_copy_is_left_out(adapter):
    row = ("2026-03-25", "Shop", "-5.00", "95.00")
    reading = read_ok(adapter, with_balance(row, row, row, ("2026-03-26", "Pay", "10.00", "105.00"), row))
    assert numbers(reading) == [2, 5]
    assert reading["dropped"] == [{"row": 3, **REPEAT}, {"row": 4, **REPEAT}, {"row": 6, **REPEAT}]


def test_the_first_of_the_equal_rows_is_the_one_kept(adapter):
    row = ("2026-03-25", "Shop", "-5.00", "95.00")
    reading = read_ok(adapter, with_balance(row, ("2026-03-24", "Other", "1.00", "96.00"), row))
    assert numbers(reading) == [2, 3]


def test_a_different_balance_makes_a_real_second_payment(adapter):
    reading = read_ok(adapter, with_balance(("2026-03-25", "Shop", "-5.00", "95.00"),
                                            ("2026-03-25", "Shop", "-5.00", "90.00")))
    assert numbers(reading) == [2, 3] and reading["dropped"] == []


def test_a_different_description_date_or_amount_is_a_different_row(adapter):
    base = ("2026-03-25", "Shop", "-5.00", "95.00")
    for other in (("2026-03-25", "Shop two", "-5.00", "95.00"), ("2026-03-26", "Shop", "-5.00", "95.00"),
                  ("2026-03-25", "Shop", "-6.00", "95.00"), ("2026-03-25", "shop", "-5.00", "95.00")):
        reading = read_ok(adapter, with_balance(base, other))
        assert numbers(reading) == [2, 3] and reading["dropped"] == []


def test_dates_are_compared_as_read(adapter):
    reading = read_ok(adapter, with_balance(("2026-3-5", "Shop", "-5.00", "95.00"),
                                            ("2026-03-05", "Shop", "-5.00", "95.00")))
    assert numbers(reading) == [2] and reading["dropped"] == [{"row": 3, **REPEAT}]


def test_values_are_compared_as_read(adapter):
    reading = read_ok(adapter, with_balance(("2026-03-05", "Shop", "-5.0", "95.00"),
                                            ("2026-03-05", "Shop", "-5.00", "95.0")))
    assert numbers(reading) == [2] and reading["dropped"] == [{"row": 3, **REPEAT}]


def test_descriptions_are_compared_after_they_are_made_one_line(adapter):
    text = ('Date,Description,Amount,Balance\n2026-03-05,Shop one,-5.00,95.00\n'
            '2026-03-05,"Shop   one ",-5.00,95.00\n')
    reading = read_ok(adapter, text)
    assert numbers(reading) == [2] and reading["dropped"] == [{"row": 3, **REPEAT}]


def test_a_row_without_a_balance_is_never_left_out(adapter):
    reading = read_ok(adapter, with_balance(("2026-03-25", "Shop", "-5.00", ""), ("2026-03-25", "Shop", "-5.00", ""),
                                            ("2026-03-25", "Shop", "-5.00", "95.00"),
                                            ("2026-03-25", "Shop", "-5.00", "95.00")))
    assert numbers(reading) == [2, 3, 4] and reading["dropped"] == [{"row": 5, **REPEAT}]


def test_a_row_with_a_balance_is_not_a_repeat_of_an_earlier_row_without_one(adapter):
    reading = read_ok(adapter, with_balance(("2026-03-25", "Shop", "-5.00", ""), ("2026-03-25", "Shop", "-5.00", "95.00")))
    assert numbers(reading) == [2, 3]


def test_a_repeated_row_is_left_out_whatever_comes_between(adapter):
    """The way the example file has it: a heading row, then rows already seen."""
    rows = [("2026-03-25", "Shop", "-5.00", "95.00"), ("2026-03-24", "Pay", "10.00", "100.00")]
    text = with_balance(*rows) + "Date,Description,Amount,Balance\n" + "\n".join(",".join(r) for r in rows) + "\n"
    reading = read_ok(adapter, text)
    assert numbers(reading) == [2, 3]
    assert reading["dropped"] == [{"row": 4, "reason": "repeated header"}, {"row": 5, **REPEAT}, {"row": 6, **REPEAT}]


def test_dropped_rows_are_listed_in_row_order(adapter):
    row = ("2026-03-25", "Shop", "-5.00", "95.00")
    text = with_balance(row, row) + "Date,Description,Amount,Balance\n" + ",".join(row) + "\n"
    reading = read_ok(adapter, text)
    assert [d["row"] for d in reading["dropped"]] == [3, 4, 5]
    assert [d["reason"] for d in reading["dropped"]] == ["repeated row", "repeated header", "repeated row"]


def test_blank_rows_are_not_reported_among_the_dropped(adapter):
    row = ("2026-03-25", "Shop", "-5.00", "95.00")
    text = with_balance(row) + "\n" + ",".join(row) + "\n"
    assert read_ok(adapter, text)["dropped"] == [{"row": 4, **REPEAT}]


def test_newest_first_looks_at_the_rows_that_were_kept(adapter):
    """The file ends with a copy of its first row; it is left out, and the last kept row is older."""
    first = ("2026-03-27", "A", "1.00", "10.00")
    reading = read_ok(adapter, with_balance(first, ("2026-03-26", "B", "1.00", "9.00"), first))
    assert reading["newest_first"] is True


# ---- without a balance column ----------------------------------------------------------------------------------------

def test_nothing_is_left_out_without_a_balance_column(adapter):
    row = ("2026-03-25", "Shop", "-5.00")
    reading = read_ok(adapter, without_balance(row, row))
    assert numbers(reading) == [2, 3] and reading["dropped"] == []


def test_the_later_equal_rows_are_listed_as_kept(adapter):
    row = ("2026-03-25", "Shop", "-5.00")
    reading = read_ok(adapter, without_balance(row, ("2026-03-26", "Pay", "1.00"), row, row))
    assert numbers(reading) == [2, 3, 4, 5]
    assert reading["same_kept"] == [4, 5]


def test_same_kept_is_in_row_order_and_counts_each_later_copy(adapter):
    a, b = ("2026-03-25", "A", "-1.00"), ("2026-03-25", "B", "-2.00")
    reading = read_ok(adapter, without_balance(a, b, b, a, a, b))
    assert reading["same_kept"] == [4, 5, 6, 7]


def test_rows_that_differ_are_not_listed(adapter):
    reading = read_ok(adapter, without_balance(("2026-03-25", "Shop", "-5.00"), ("2026-03-25", "Shop", "-6.00"),
                                               ("2026-03-26", "Shop", "-5.00"), ("2026-03-25", "Shop two", "-5.00")))
    assert reading["same_kept"] == []


def test_equal_rows_are_compared_as_read_without_a_balance_column(adapter):
    reading = read_ok(adapter, without_balance(("2026-3-5", "Shop", "-5.0"), ("2026-03-05", "Shop", "-5.00")))
    assert reading["same_kept"] == [3]


def test_a_repeated_heading_row_is_still_left_out_without_a_balance_column(adapter):
    row = ("2026-03-25", "Shop", "-5.00")
    text = without_balance(row) + "Date,Description,Amount\n"
    reading = read_ok(adapter, text)
    assert numbers(reading) == [2] and reading["dropped"] == [{"row": 3, "reason": "repeated header"}]


def test_a_balance_column_that_is_not_found_does_not_count(adapter):
    """A column the adapter does not know as the balance is ignored, so equal rows are kept."""
    text = csv_text([("2026-03-25", "Shop", "-5.00", "95.00")] * 2, header=("Date", "Description", "Amount", "Total"))
    reading = read_ok(adapter, text)
    assert numbers(reading) == [2, 3] and reading["same_kept"] == [3] and reading["dropped"] == []
