from decimal import Decimal
from module import calculate


def test_ordinary():
    assert calculate(total_cost=Decimal("10000"), guest_count=100) == Decimal("100.00")


def test_single_guest():
    assert calculate(total_cost=Decimal("1234.56"), guest_count=1) == Decimal("1234.56")


def test_rounding_half_up():
    assert calculate(total_cost=Decimal("1.00"), guest_count=8) == Decimal("0.13")


def test_rounding_repeating():
    assert calculate(total_cost=Decimal("100"), guest_count=3) == Decimal("33.33")


def test_zero_cost():
    assert calculate(total_cost=Decimal("0"), guest_count=5) == Decimal("0.00")
