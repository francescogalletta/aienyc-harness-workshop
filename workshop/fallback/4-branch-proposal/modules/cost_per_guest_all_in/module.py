from decimal import Decimal, ROUND_HALF_UP


def calculate(total_cost, guest_count):
    if guest_count < 1:
        raise ValueError("The guest count must be at least 1.")
    result = Decimal(total_cost) / Decimal(guest_count)
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
