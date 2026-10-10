from decimal import Decimal
from module import calculate


def test_ordinary():
    assert calculate(deposit=Decimal("1000"), van_hire=Decimal("150"), monthly_rent_old_home=Decimal("800"), overlap_months=1, other_one_off_costs=[{"name": "cleaning", "amount": "50"}, {"name": "boxes", "amount": "25.50"}]) == Decimal("2025.50")


def test_empty_and_zero_overlap():
    assert calculate(deposit=Decimal("500"), van_hire=Decimal("100"), monthly_rent_old_home=Decimal("700"), overlap_months=0, other_one_off_costs=[]) == Decimal("600.00")


def test_overlap_multiplication():
    assert calculate(deposit=Decimal("0"), van_hire=Decimal("0"), monthly_rent_old_home=Decimal("333.33"), overlap_months=3, other_one_off_costs=[]) == Decimal("999.99")
