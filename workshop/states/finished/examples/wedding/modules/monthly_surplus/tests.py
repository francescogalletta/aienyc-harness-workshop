from decimal import Decimal
from module import calculate


def test_ordinary():
    spending = [
        {"name": "rent", "amount": "800.50"},
        {"name": "food", "amount": "300"},
    ]
    assert calculate(net_monthly_income=Decimal("2000"), monthly_spending=spending) == Decimal("899.50")


def test_empty_list():
    assert calculate(net_monthly_income=Decimal("1500"), monthly_spending=[]) == Decimal("1500.00")


def test_negative_result():
    spending = [{"name": "all", "amount": "1200.25"}]
    assert calculate(net_monthly_income=Decimal("1000"), monthly_spending=spending) == Decimal("-200.25")


def test_exact_zero():
    spending = [{"name": "a", "amount": "400"}, {"name": "b", "amount": "600"}]
    assert calculate(net_monthly_income=Decimal("1000"), monthly_spending=spending) == Decimal("0.00")
