from decimal import Decimal
from module import calculate


def test_ordinary():
    assert calculate(net_monthly_income=Decimal("3000"), monthly_spending=Decimal("2200")) == Decimal("800.00")


def test_zero_surplus():
    assert calculate(net_monthly_income=Decimal("1500.50"), monthly_spending=Decimal("1500.50")) == Decimal("0.00")


def test_negative():
    assert calculate(net_monthly_income=Decimal("2000"), monthly_spending=Decimal("2150.25")) == Decimal("-150.25")


def test_rounding_half_up():
    assert calculate(net_monthly_income=Decimal("100.005"), monthly_spending=Decimal("0")) == Decimal("100.01")
    assert calculate(net_monthly_income=Decimal("100.004"), monthly_spending=Decimal("0")) == Decimal("100.00")
