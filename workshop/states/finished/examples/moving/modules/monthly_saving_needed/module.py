from decimal import Decimal, ROUND_CEILING


def calculate(upfront_cost, savings_so_far, months_until_move):
    if months_until_move < 1:
        raise ValueError("Months until the move must be one or more.")
    if savings_so_far >= upfront_cost:
        return Decimal("0.00")
    amount = (upfront_cost - savings_so_far) / Decimal(months_until_move)
    return amount.quantize(Decimal("0.01"), rounding=ROUND_CEILING)
