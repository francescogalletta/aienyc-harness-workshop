from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta


def calculate(total_cost, first_payment_amount, today, first_payment_days_from_today, wedding_date, second_payment_days_before_wedding, third_payment_days_before_wedding, second_payment_share):
    if first_payment_amount < 0:
        raise ValueError("The first payment amount cannot be negative.")
    if total_cost < first_payment_amount:
        raise ValueError("The total cost must be at least the first payment amount.")
    if second_payment_share < 0 or second_payment_share > 1:
        raise ValueError("The second payment share must be between 0 and 1.")
    cent = Decimal("0.01")
    remaining = total_cost - first_payment_amount
    p2 = (remaining * second_payment_share).quantize(cent, rounding=ROUND_HALF_UP)
    p3 = remaining - p2
    p1 = first_payment_amount
    d1 = today + timedelta(days=first_payment_days_from_today)
    d2 = wedding_date - timedelta(days=second_payment_days_before_wedding)
    d3 = wedding_date - timedelta(days=third_payment_days_before_wedding)
    return {
        "payment_1_amount": p1.quantize(cent, rounding=ROUND_HALF_UP),
        "payment_1_due_date": d1.isoformat(),
        "payment_2_amount": p2,
        "payment_2_due_date": d2.isoformat(),
        "payment_3_amount": p3.quantize(cent, rounding=ROUND_HALF_UP),
        "payment_3_due_date": d3.isoformat(),
    }
