from decimal import Decimal, ROUND_HALF_UP


def calculate(net_monthly_income, monthly_spending):
    surplus = Decimal(net_monthly_income) - Decimal(monthly_spending)
    return surplus.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
