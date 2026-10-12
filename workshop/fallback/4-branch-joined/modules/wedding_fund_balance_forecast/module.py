from decimal import Decimal, ROUND_HALF_UP
from datetime import date
import calendar


def _q(x):
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _saving_count(today, due):
    diff = (due.year - today.year) * 12 + due.month - today.month
    count = 0
    for k in range(1, diff + 2):
        idx = today.month - 1 + k
        y = today.year + idx // 12
        m = idx % 12 + 1
        d = min(today.day, calendar.monthrange(y, m)[1])
        if date(y, m, d) <= due:
            count += 1
    return count


def calculate(current_savings, monthly_saving, today, payments, contribution_amount, contribution_date):
    items = []
    for i, p in enumerate(payments):
        items.append((date.fromisoformat(str(p["due_date"])), i, p))
    items = sorted(items)
    result = []
    paid = Decimal("0")
    for due, _i, p in items:
        amount = Decimal(str(p["amount"]))
        n = _saving_count(today, due)
        before = current_savings + monthly_saving * n - paid
        if contribution_amount != 0 and contribution_date is not None and contribution_date <= due:
            before = before + contribution_amount
        after = before - amount
        shortfall = -after if after < 0 else Decimal("0")
        result.append({
            "name": p["name"],
            "due_date": due.isoformat(),
            "amount_due": _q(amount),
            "balance_before_payment": _q(before),
            "balance_after_payment": _q(after),
            "shortfall": _q(shortfall),
        })
        paid = paid + amount
    return result
