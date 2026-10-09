from decimal import Decimal
from module import calculate


def test_ordinary():
    assert calculate(upfront_cost=Decimal("5000"), savings_so_far=Decimal("1000"), monthly_saving=Decimal("500")) == 8


def test_rounds_up():
    assert calculate(upfront_cost=Decimal("1000"), savings_so_far=Decimal("0"), monthly_saving=Decimal("300")) == 4


def test_already_covered():
    assert calculate(upfront_cost=Decimal("1000"), savings_so_far=Decimal("1000"), monthly_saving=Decimal("300")) == 0


def test_zero_savings_exact():
    assert calculate(upfront_cost=Decimal("900"), savings_so_far=Decimal("0"), monthly_saving=Decimal("300")) == 3


def test_small_remainder():
    assert calculate(upfront_cost=Decimal("1000.01"), savings_so_far=Decimal("1000"), monthly_saving=Decimal("500")) == 1
