import calendar
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP


def _saving_date(today, k):
    total = today.year * 12 + (today.month - 1) + k
    y, m = divmod(total, 12)
    m += 1
    day = min(today.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def _months(today, due):
    if due <= today:
        return 0
    limit = (due.year - today.year) * 12 + due.month - today.month + 2
    count = 0
    for k in range(1, limit + 1):
        if _saving_date(today, k) <= due:
            count += 1
    return count


def calculate(today, payments):
    items = []
    for idx, p in enumerate(payments):
        due = date.fromisoformat(str(p["due_date"]))
        shortfall = Decimal(str(p["shortfall"]))
        items.append((due, idx, str(p["name"]), shortfall))
    items = sorted(items)
    result = []
    for due, idx, name, shortfall in items:
        months = _months(today, due)
        if shortfall <= 0:
            extra = Decimal("0.00")
        elif months == 0:
            extra = shortfall.quantize(Decimal("0.01"), rounding=ROUND_CEILING)
        else:
            extra = (shortfall / Decimal(months)).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
        result.append({
            "name": name,
            "due_date": due.isoformat(),
            "shortfall": shortfall.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "months_until_due": months,
            "extra_monthly_saving_needed": extra,
        })
    return result
