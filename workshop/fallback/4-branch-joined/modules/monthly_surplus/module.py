from decimal import Decimal, ROUND_HALF_UP


def calculate(net_monthly_income, monthly_spending):
    total = Decimal("0")
    for item in monthly_spending:
        total += Decimal(str(item["amount"]))
    result = Decimal(net_monthly_income) - total
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
