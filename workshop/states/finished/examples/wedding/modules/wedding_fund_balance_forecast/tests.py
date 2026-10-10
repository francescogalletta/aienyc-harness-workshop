from module import calculate
from decimal import Decimal
from datetime import date


def test_ordinary_case():
    r = calculate(current_savings=Decimal("1000"), monthly_saving=Decimal("100"), today=date(2026, 1, 31),
                  payments=[{"name": "A", "amount": "500", "due_date": "2026-03-31"}],
                  contribution_amount=Decimal("0"), contribution_date=date(2026, 1, 1))
    assert r[0]["balance_before_payment"] == Decimal("1200.00")
    assert r[0]["balance_after_payment"] == Decimal("700.00")
    assert r[0]["shortfall"] == Decimal("0.00")
    assert r[0]["due_date"] == "2026-03-31"


def test_month_end_clamping():
    r = calculate(current_savings=Decimal("0"), monthly_saving=Decimal("100"), today=date(2026, 1, 31),
                  payments=[{"name": "A", "amount": "10", "due_date": "2026-03-01"}],
                  contribution_amount=Decimal("0"), contribution_date=date(2026, 1, 1))
    assert r[0]["balance_before_payment"] == Decimal("100.00")


def test_shortfall_carries_over_and_sorting():
    r = calculate(current_savings=Decimal("0"), monthly_saving=Decimal("100"), today=date(2026, 1, 31),
                  payments=[{"name": "B", "amount": "50", "due_date": "2026-03-31"},
                            {"name": "A", "amount": "300", "due_date": "2026-02-28"}],
                  contribution_amount=Decimal("0"), contribution_date=date(2026, 1, 1))
    assert r[0]["name"] == "A"
    assert r[0]["balance_before_payment"] == Decimal("100.00")
    assert r[0]["balance_after_payment"] == Decimal("-200.00")
    assert r[0]["shortfall"] == Decimal("200.00")
    assert r[1]["balance_before_payment"] == Decimal("-100.00")
    assert r[1]["balance_after_payment"] == Decimal("-150.00")
    assert r[1]["shortfall"] == Decimal("150.00")


def test_contribution_on_due_date_included():
    r = calculate(current_savings=Decimal("0"), monthly_saving=Decimal("0"), today=date(2026, 1, 31),
                  payments=[{"name": "A", "amount": "100", "due_date": "2026-02-28"}],
                  contribution_amount=Decimal("500"), contribution_date=date(2026, 2, 28))
    assert r[0]["balance_before_payment"] == Decimal("500.00")
    assert r[0]["balance_after_payment"] == Decimal("400.00")


def test_empty_payments():
    assert calculate(current_savings=Decimal("5"), monthly_saving=Decimal("1"), today=date(2026, 1, 1),
                     payments=[], contribution_amount=Decimal("0"), contribution_date=date(2026, 1, 1)) == []
