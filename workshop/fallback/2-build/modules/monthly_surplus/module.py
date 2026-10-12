from decimal import Decimal


def calculate(net_monthly_income, monthly_spending):
    return Decimal(net_monthly_income) - Decimal(monthly_spending)
