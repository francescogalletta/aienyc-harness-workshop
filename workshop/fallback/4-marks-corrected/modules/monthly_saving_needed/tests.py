from module import calculate
from decimal import Decimal
from datetime import date


def test_ordinary():
    r = calculate(today=date(2026, 10, 9), payments=[{"name": "payment 1", "due_date": "2026-12-09", "shortfall": "100"}])
    assert r == [{"name": "payment 1", "due_date": "2026-12-09", "shortfall": Decimal("100.00"), "months_until_due": 2, "extra_monthly_saving_needed": Decimal("50.00")}]


def test_short_month_and_round_up():
    r = calculate(today=date(2026, 1, 31), payments=[{"name": "a", "due_date": "2026-04-30", "shortfall": "100"}])
    assert r[0]["months_until_due"] == 3
    assert r[0]["extra_monthly_saving_needed"] == Decimal("33.34")


def test_zero_shortfall():
    r = calculate(today=date(2026, 10, 9), payments=[{"name": "a", "due_date": "2027-01-09", "shortfall": "0"}])
    assert r[0]["months_until_due"] == 3
    assert r[0]["extra_monthly_saving_needed"] == Decimal("0.00")


def test_zero_months():
    r = calculate(today=date(2026, 10, 9), payments=[{"name": "a", "due_date": "2026-10-09", "shortfall": "75.50"}])
    assert r[0]["months_until_due"] == 0
    assert r[0]["extra_monthly_saving_needed"] == Decimal("75.50")


def test_order_by_due_date():
    r = calculate(today=date(2026, 10, 9), payments=[
        {"name": "late", "due_date": "2026-12-20", "shortfall": "10"},
        {"name": "early", "due_date": "2026-11-08", "shortfall": "10"}])
    assert r[0]["name"] == "early"
    assert r[0]["months_until_due"] == 0
    assert r[1]["months_until_due"] == 2
    assert r[1]["extra_monthly_saving_needed"] == Decimal("5.00")
