from decimal import Decimal, ROUND_HALF_UP


def calculate(deposit, van_hire, monthly_rent_old_home, overlap_months, other_one_off_costs):
    if overlap_months < 0:
        raise ValueError("Overlap months cannot be negative.")
    total = Decimal(deposit) + Decimal(van_hire) + Decimal(overlap_months) * Decimal(monthly_rent_old_home)
    for item in other_one_off_costs:
        total += Decimal(str(item["amount"]))
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
