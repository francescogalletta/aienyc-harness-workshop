from decimal import Decimal, ROUND_HALF_UP


def calculate(guest_count, dinner_cost_per_guest, extra_costs):
    if guest_count < 0:
        raise ValueError("Guest count cannot be negative.")
    if dinner_cost_per_guest < 0:
        raise ValueError("Dinner cost per guest cannot be negative.")
    total = Decimal(guest_count) * dinner_cost_per_guest
    for item in extra_costs:
        total += Decimal(str(item["amount"]))
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
