"""SPEC 5.1: values travel as JSON, and exact numbers travel as text."""
from datetime import date
from decimal import Decimal

from harness.calc.values import from_json, same, to_json


def test_a_number_becomes_a_decimal_with_its_commas_removed():
    assert from_json("1,234.50", "number") == Decimal("1234.50")
    assert isinstance(from_json("1,234.50", "number"), Decimal)


def test_to_json_writes_exact_numbers_as_text():
    assert to_json(Decimal("4583.33")) == "4583.33"
    assert to_json(date(2026, 3, 15)) == "2026-03-15"


def test_numbers_match_within_half_a_cent_and_not_further():
    assert same("1,000", "1000.004")
    assert not same("1000", "1000.006")
