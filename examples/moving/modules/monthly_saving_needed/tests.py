from decimal import Decimal
from module import calculate


def test_ordinary():
    assert calculate(upfront_cost=Decimal("1000"), savings_so_far=Decimal("200"), months_until_move=4) == Decimal("200.00")


def test_rounds_up():
    assert calculate(upfront_cost=Decimal("100"), savings_so_far=Decimal("0"), months_until_move=3) == Decimal("33.34")


def test_savings_cover_cost():
    assert calculate(upfront_cost=Decimal("500"), savings_so_far=Decimal("500"), months_until_move=2) == Decimal("0.00")


def test_tiny_fraction_rounds_up():
    assert calculate(upfront_cost=Decimal("10.01"), savings_so_far=Decimal("10"), months_until_move=3) == Decimal("0.01")
