from decimal import Decimal
from module import calculate


def test_ordinary():
    assert calculate(net_monthly_income=Decimal("3000"), monthly_spending=Decimal("2200")) == Decimal("800")


def test_zero_surplus():
    assert calculate(net_monthly_income=Decimal("1500.50"), monthly_spending=Decimal("1500.50")) == Decimal("0")


def test_negative_and_no_rounding():
    assert calculate(net_monthly_income=Decimal("1000.005"), monthly_spending=Decimal("1200.01")) == Decimal("-200.005")
