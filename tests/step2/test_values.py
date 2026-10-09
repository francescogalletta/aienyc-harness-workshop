"""SPEC 5.1: values travel as JSON, and exact numbers travel as text."""
from datetime import date
from decimal import Decimal

import pytest

from harness.calc.values import TOLERANCE, TYPES, from_json, same, to_json


def test_the_types():
    assert TYPES == ("number", "integer", "date", "text", "boolean", "list", "object")
    assert TOLERANCE == Decimal("0.005")


@pytest.mark.parametrize("value, expected", [
    ("1234.50", Decimal("1234.50")),
    ("1,234.50", Decimal("1234.50")),          # commas are removed
    (5, Decimal("5")),
    (0.1, Decimal("0.1")),                     # a JSON number is not a binary float on the way in
])
def test_a_number_becomes_a_decimal(value, expected):
    assert from_json(value, "number") == expected
    assert isinstance(from_json(value, "number"), Decimal)


def test_each_type_is_converted():
    assert from_json("7", "integer") == 7 and isinstance(from_json("7", "integer"), int)
    assert from_json("2026-03-15", "date") == date(2026, 3, 15)
    assert from_json("words", "text") == "words"
    assert from_json(True, "boolean") is True


def test_a_list_and_an_object_are_passed_through_as_they_are():
    assert from_json(["1.5", "2026-01-01"], "list") == ["1.5", "2026-01-01"]
    assert from_json({"amount": "1.5"}, "object") == {"amount": "1.5"}


def test_a_value_that_does_not_fit_says_so_plainly():
    with pytest.raises(ValueError, match="expected a number, got 'abc'"):
        from_json("abc", "number")


@pytest.mark.parametrize("value, kind", [
    ("x", "integer"), (1.5, "integer"), ("2026-13-01", "date"), ("15/03/2026", "date"),
    ("yes", "boolean"), ({}, "list"), ([], "object"), ("abc", "number"),
])
def test_other_values_that_do_not_fit_raise_value_error(value, kind):
    with pytest.raises(ValueError):
        from_json(value, kind)


def test_to_json_writes_exact_numbers_as_text():
    assert to_json(Decimal("30000")) == "30000"
    assert to_json(Decimal("4583.33")) == "4583.33"
    assert to_json(12) == "12"
    assert to_json(date(2026, 3, 15)) == "2026-03-15"


def test_to_json_converts_containers_item_by_item():
    assert to_json([Decimal("1.5"), (2, date(2026, 1, 2))]) == ["1.5", ["2", "2026-01-02"]]
    assert to_json({"total": Decimal("10"), "when": date(2026, 1, 2)}) == {"total": "10", "when": "2026-01-02"}


def test_a_float_goes_through_its_repr():
    assert to_json(0.1 + 0.2) == "0.30000000000000004"
    assert to_json(0.1) == "0.1"


def test_text_and_booleans_stay_as_they_are():
    assert to_json("words") == "words"
    assert to_json(True) is True


def test_to_json_refuses_anything_else():
    with pytest.raises(ValueError):
        to_json(object())


@pytest.mark.parametrize("expected, actual", [
    ("4583.33", 4583.333),                     # text against a JSON number
    (100, "100.00"),
    ("1,000", "1000.004"),                     # within half a cent
    ("1000", "999.995"),                       # exactly half a cent apart still matches
])
def test_numbers_match_within_half_a_cent(expected, actual):
    assert same(expected, actual)


def test_numbers_further_apart_do_not_match():
    assert not same("1000", "1000.006")
    assert not same(1, 2)


def test_lists_match_item_by_item():
    assert same(["1.00", "2"], [1, "2.001"])
    assert not same(["1", "2"], ["1"])
    assert not same(["1", "2"], ["2", "1"])


def test_objects_match_key_by_key_with_the_same_keys():
    assert same({"a": "1", "b": "2"}, {"b": 2.001, "a": "1.000"})
    assert not same({"a": "1"}, {"a": "1", "b": "2"})
    assert not same({"a": "1"}, {"b": "1"})
    assert not same({"a": "1"}, {"a": "2"})


def test_booleans_match_only_booleans():
    assert same(True, True) and same(False, False)
    assert not same(True, False)
    assert not same(True, 1) and not same(1, True) and not same(False, 0)
    assert not same(True, "true")
