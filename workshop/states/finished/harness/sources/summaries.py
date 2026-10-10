"""The data summaries (SPEC 9.4): a small fixed set of measures, about no domain.

Hand-written and tested like a module. They read only the `transactions` table.
"""
import calendar
import json
import re
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from .. import db

ALL_ACCOUNTS = "all"
MAX_MONTHS = 12
MEASURES = {
    "money_in":  "Money that came in, in each full calendar month. value is the average a month over the months asked for.",
    "money_out": "Money that went out, as a positive figure, in each full calendar month. value is the average a month over the months asked for.",
    "net":       "Money in less money out, in each full calendar month. value is the average a month over the months asked for.",
    "balance":   "The balance on the latest row of one account whose files have a balance column. value is that balance, as_of its date.",
}


class SummaryRefused(Exception):
    """A summary that cannot be made. The message is the reason."""


SUMMARY_NO_DATA = "No account files are loaded."
SUMMARY_MEASURE = "measure must be money_in, money_out, net or balance."
SUMMARY_ACCOUNT = "There is no account '{account}'. The accounts are: {accounts}; or all."
SUMMARY_BALANCE_ALL = "A balance is for one account. Name the account."
SUMMARY_NO_BALANCE = "The files of account '{account}' have no balance column."
SUMMARY_PERIOD = "Give either months, a whole number from 1 to 12, or month, written YYYY-MM."
SUMMARY_FEW_MONTHS = "Only {count} full months are loaded for {scope}: {months}."
SUMMARY_NOT_FULL = "{month} is not a full month loaded for {scope}. The full months are: {months}."
MEASURE_WORDS = {"money_in": "money in", "money_out": "money out", "net": "money in less money out"}
DESCRIBE_AVERAGE = "{words} a month, on average over the {count} full months {first} to {last}, {scope}"
DESCRIBE_MONTH = "{words} in {month}, {scope}"
DESCRIBE_BALANCE = "the balance of {scope} on {as_of}"
SCOPE_ALL = "all accounts"
SCOPE_ACCOUNT = "account '{account}'"

MONTH = re.compile(r"\d{4}-\d{2}")
CENTS = Decimal("0.01")


def _scope(account: str) -> str:
    return SCOPE_ALL if account == ALL_ACCOUNTS else SCOPE_ACCOUNT.format(account=account)


def _written(value: Decimal) -> str:
    """A figure rounded to cents, half up, with two decimals and never `-0.00`."""
    cents = value.quantize(CENTS, rounding=ROUND_HALF_UP)
    return format(abs(cents) if cents == 0 else cents, "f")


def _months_between(first: str, last: str) -> list[str]:
    year, month = int(first[:4]), int(first[5:7])
    found = []
    while f"{year:04d}-{month:02d}" <= last[:7]:
        found.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return found


def _full(first: str, last: str) -> list[str]:
    """The months a range of dates reaches at both ends."""
    found = []
    for month in _months_between(first, last):
        year, number = int(month[:4]), int(month[5:7])
        if first <= f"{month}-01" and last >= f"{month}-{calendar.monthrange(year, number)[1]:02d}":
            found.append(month)
    return found


def full_months(conn, account: str) -> list[str]:
    """The full calendar months of an account, or of all accounts together, as `YYYY-MM`, oldest first (SPEC 9.4)."""
    if account == ALL_ACCOUNTS:
        names = [row["account"] for row in conn.execute("SELECT DISTINCT account FROM transactions")]
        months = None
        for name in names:
            found = set(full_months(conn, name))
            months = found if months is None else months & found
        return sorted(months or [])
    row = conn.execute("SELECT MIN(date) AS first, MAX(date) AS last FROM transactions WHERE account = ?",
                       (account,)).fetchone()
    return _full(row["first"], row["last"]) if row["first"] is not None else []


def own_transfers(conn) -> set[int]:
    """The ids of the transactions in pairs of equal and opposite amounts on one day in two accounts (SPEC 9.4)."""
    rows = conn.execute("SELECT id, account, date, amount FROM transactions ORDER BY id").fetchall()
    waiting = {}        # (date, amount) -> [(id, account)], lowest id first
    for row in rows:
        waiting.setdefault((row["date"], Decimal(row["amount"])), []).append((row["id"], row["account"]))
    paired = set()
    for row in sorted(rows, key=lambda each: (each["date"], each["id"])):
        amount = Decimal(row["amount"])
        if amount >= 0:
            continue
        for other, account in waiting.get((row["date"], -amount), []):
            if other not in paired and account != row["account"]:
                paired.update((row["id"], other))
                break
    return paired


def accounts(conn) -> list[dict]:
    """One dict per loaded account, sorted by name (SPEC 9.4)."""
    found = []
    for row in conn.execute("SELECT account, COUNT(*) AS n, MIN(date) AS first, MAX(date) AS last,"
                            " COUNT(balance) AS balances FROM transactions GROUP BY account ORDER BY account"):
        files = [json.loads(each["report"])["name"] for each in conn.execute(
            "SELECT report FROM imports WHERE account = ? ORDER BY id", (row["account"],))]
        found.append({"account": row["account"], "files": files, "transactions": row["n"], "first": row["first"],
                      "last": row["last"], "full_months": full_months(conn, row["account"]),
                      "balance": row["balances"] > 0})
    return found


def _named(value) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def summarise(conn, arguments: dict) -> tuple[dict, dict, list[int]]:
    """Check the arguments and work one summary out. Returns (inputs, output, import ids) (SPEC 9.4)."""
    arguments = arguments if isinstance(arguments, dict) else {}
    if conn.execute("SELECT 1 FROM transactions LIMIT 1").fetchone() is None:
        raise SummaryRefused(SUMMARY_NO_DATA)
    measure = arguments.get("measure")
    if not isinstance(measure, str) or measure not in MEASURES:
        raise SummaryRefused(SUMMARY_MEASURE)
    names = sorted(row["account"] for row in conn.execute("SELECT DISTINCT account FROM transactions"))
    account = arguments.get("account")
    if not isinstance(account, str) or (account not in names and account != ALL_ACCOUNTS):
        raise SummaryRefused(SUMMARY_ACCOUNT.format(account=_named(account), accounts=", ".join(names)))
    scope = _scope(account)
    if measure == "balance":
        if account == ALL_ACCOUNTS:
            raise SummaryRefused(SUMMARY_BALANCE_ALL)
        if conn.execute("SELECT 1 FROM transactions WHERE account = ? AND balance IS NOT NULL LIMIT 1",
                        (account,)).fetchone() is None:
            raise SummaryRefused(SUMMARY_NO_BALANCE.format(account=account))
    else:
        months, month = arguments.get("months"), arguments.get("month")
        given = [each for each in (months, month) if each is not None]
        if (len(given) != 1 or (months is not None and (not isinstance(months, int) or isinstance(months, bool)
                                                         or not 1 <= months <= MAX_MONTHS))
                or (month is not None and (not isinstance(month, str) or not MONTH.fullmatch(month)))):
            raise SummaryRefused(SUMMARY_PERIOD)
        full = full_months(conn, account)
        listed = ", ".join(full) or "none"
        if months is not None and len(full) < months:
            raise SummaryRefused(SUMMARY_FEW_MONTHS.format(count=len(full), scope=scope, months=listed))
        if month is not None and month not in full:
            raise SummaryRefused(SUMMARY_NOT_FULL.format(month=month, scope=scope, months=listed))

    imports = [row["id"] for row in conn.execute(
        "SELECT id FROM imports WHERE (? = ? OR account = ?) ORDER BY id", (account, ALL_ACCOUNTS, account))]
    if measure == "balance":
        return ({"measure": measure, "account": account}, _balance(conn, account), imports)
    chosen = full[-months:] if months is not None else [month]
    inputs = {"measure": measure, "account": account, "months": months} if months is not None else {
        "measure": measure, "account": account, "month": month}
    return inputs, _monthly(conn, measure, account, chosen), imports


def _monthly(conn, measure: str, account: str, months: list[str]) -> dict:
    transfers = own_transfers(conn)
    rows = conn.execute("SELECT id, amount, substr(date, 1, 7) AS month FROM transactions"
                        " WHERE (? = ? OR account = ?) AND substr(date, 1, 7) IN (%s)" % ",".join("?" * len(months)),
                        (account, ALL_ACCOUNTS, account, *months)).fetchall()
    figures, left_out = [], 0
    for month in months:
        money_in = money_out = Decimal(0)
        for row in rows:
            if row["month"] != month:
                continue
            if row["id"] in transfers:
                left_out += 1
                continue
            amount = Decimal(row["amount"])
            if amount > 0:
                money_in += amount
            else:
                money_out -= amount
        figures.append({"money_in": money_in, "money_out": money_out, "net": money_in - money_out}[measure])
    return {"measure": measure, "account": account, "months": months,
            "by_month": [{"month": month, "value": _written(figure)} for month, figure in zip(months, figures)],
            "value": _written(sum(figures, Decimal(0)) / len(figures)), "left_out": left_out}


def _balance(conn, account: str) -> dict:
    newest = {row["id"]: bool(json.loads(row["report"])["newest_first"])
              for row in conn.execute("SELECT id, report FROM imports WHERE account = ?", (account,))}
    rows = conn.execute("SELECT date, import_id, row, balance FROM transactions"
                        " WHERE account = ? AND balance IS NOT NULL", (account,)).fetchall()
    latest = max(rows, key=lambda row: (row["date"], row["import_id"],
                                        -row["row"] if newest[row["import_id"]] else row["row"]))
    return {"measure": "balance", "account": account, "as_of": latest["date"],
            "value": _written(Decimal(latest["balance"]))}


def run_summary(conn, arguments: dict, *, session_id: str) -> dict:
    """Work a summary out and record it (SPEC 9.4). Returns `{"summary": <id>}` followed by the output."""
    try:
        inputs, output, imports = summarise(conn, arguments)
    except SummaryRefused as refused:
        db.record_event(conn, session_id=session_id, kind="data.summary_refused", actor="harness",
                        payload={"arguments": arguments, "error": str(refused)})
        raise
    cursor = conn.execute(
        "INSERT INTO data_summaries (ts, session_id, inputs, output, imports) VALUES (?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), session_id, json.dumps(inputs), json.dumps(output),
         json.dumps(imports)))
    conn.commit()
    db.record_event(conn, session_id=session_id, kind="data.summary", actor="harness",
                    payload={"id": cursor.lastrowid, "inputs": inputs, "output": output, "imports": imports})
    return {"summary": cursor.lastrowid, **output}


def describe(output: dict) -> str:
    """What a summary measured, in plain words (SPEC 9.4)."""
    scope = _scope(output["account"])
    if output["measure"] == "balance":
        return DESCRIBE_BALANCE.format(scope=scope, as_of=output["as_of"])
    months, words = output["months"], MEASURE_WORDS[output["measure"]]
    if len(months) > 1:
        return DESCRIBE_AVERAGE.format(words=words, count=len(months), first=months[0], last=months[-1],
                                       scope=scope)
    return DESCRIBE_MONTH.format(words=words, month=months[0], scope=scope)
