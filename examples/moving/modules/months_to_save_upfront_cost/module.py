from decimal import Decimal, ROUND_CEILING


def calculate(upfront_cost, savings_so_far, monthly_saving):
    if monthly_saving <= 0:
        raise ValueError("Monthly saving must be more than zero.")
    if savings_so_far >= upfront_cost:
        return 0
    months = (upfront_cost - savings_so_far) / monthly_saving
    return int(months.to_integral_value(rounding=ROUND_CEILING))
