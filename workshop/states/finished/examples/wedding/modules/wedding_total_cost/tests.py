from decimal import Decimal
from module import calculate


def test_ordinary():
    extras = [{"name": "DJ", "amount": "500"}, {"name": "Bar", "amount": "250.50"}]
    assert calculate(guest_count=10, dinner_cost_per_guest=Decimal("100"), extra_costs=extras) == Decimal("1750.50")


def test_empty_extras():
    assert calculate(guest_count=4, dinner_cost_per_guest=Decimal("25.25"), extra_costs=[]) == Decimal("101.00")


def test_zero_guests():
    extras = [{"name": "DJ", "amount": "300"}]
    assert calculate(guest_count=0, dinner_cost_per_guest=Decimal("80"), extra_costs=extras) == Decimal("300.00")


def test_rounding():
    extras = [{"name": "Flowers", "amount": "0.004"}]
    assert calculate(guest_count=3, dinner_cost_per_guest=Decimal("0.335"), extra_costs=extras) == Decimal("1.01")
