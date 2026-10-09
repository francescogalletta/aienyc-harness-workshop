from module import calculate
from decimal import Decimal
from datetime import date


def test_ordinary():
    r = calculate(total_cost=Decimal("10000"), first_payment_amount=Decimal("1000"), today=date(2027, 1, 1), first_payment_days_from_today=30, wedding_date=date(2027, 12, 31), second_payment_days_before_wedding=60, third_payment_days_before_wedding=14, second_payment_share=Decimal("0.5"))
    assert r == {
        "payment_1_amount": Decimal("1000.00"),
        "payment_1_due_date": "2027-01-31",
        "payment_2_amount": Decimal("4500.00"),
        "payment_2_due_date": "2027-11-01",
        "payment_3_amount": Decimal("4500.00"),
        "payment_3_due_date": "2027-12-17",
    }


def test_rounding_goes_to_payment_2_and_remainder_to_3():
    r = calculate(total_cost=Decimal("1000.01"), first_payment_amount=Decimal("0"), today=date(2027, 1, 1), first_payment_days_from_today=0, wedding_date=date(2027, 12, 31), second_payment_days_before_wedding=31, third_payment_days_before_wedding=0, second_payment_share=Decimal("0.5"))
    assert r["payment_2_amount"] == Decimal("500.01")
    assert r["payment_3_amount"] == Decimal("500.00")
    assert r["payment_1_due_date"] == "2027-01-01"
    assert r["payment_2_due_date"] == "2027-11-30"
    assert r["payment_3_due_date"] == "2027-12-31"


def test_total_equals_first_payment():
    r = calculate(total_cost=Decimal("500"), first_payment_amount=Decimal("500"), today=date(2027, 1, 1), first_payment_days_from_today=1, wedding_date=date(2027, 3, 1), second_payment_days_before_wedding=1, third_payment_days_before_wedding=2, second_payment_share=Decimal("0.3"))
    assert r["payment_2_amount"] == Decimal("0.00")
    assert r["payment_3_amount"] == Decimal("0.00")
    assert r["payment_2_due_date"] == "2027-02-28"
    assert r["payment_3_due_date"] == "2027-02-27"
