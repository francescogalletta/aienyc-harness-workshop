"""The source adapter (SPEC 9.2): one delimited file of transactions into the canonical table.

Plain, tested code; no model reads a file. The rules run in the order of the
SPEC, so the same bytes always give the same result.
"""
import csv
import hashlib
import io
import json
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .. import db
from ..calc.decisions import one_line


class NotLoaded(Exception):
    """A file that was not loaded. The message is the reason, one line."""


SIGNS = ("out_negative", "out_positive")
SIGN_FROMS = ("flag", "asked", "scenario")
DELIMITERS = (",", ";", "\t", "|")
DELIMITER_WORDS = {",": "commas", ";": "semicolons", "\t": "tabs", "|": "bars"}
HEADER_SEARCH = 20

COLUMN_NAMES = {
    "date": ("date", "transaction date", "trans date", "booking date", "posting date", "posted date",
             "post date", "value date", "fecha", "fecha operacion", "fecha de operacion", "fecha valor",
             "fecha contable"),
    "description": ("description", "descripcion", "concepto", "payee", "merchant", "narrative", "memo",
                    "details", "detalle", "movimiento"),
    "amount": ("amount", "transaction amount", "importe", "cantidad", "monto"),
    "balance": ("balance", "running balance", "running bal", "saldo", "saldo disponible"),
}
DATE_FORMATS = (("%Y-%m-%d", "YYYY-MM-DD"), ("%d/%m/%Y", "DD/MM/YYYY"), ("%m/%d/%Y", "MM/DD/YYYY"),
                ("%d.%m.%Y", "DD.MM.YYYY"), ("%d-%m-%Y", "DD-MM-YYYY"), ("%Y/%m/%d", "YYYY/MM/DD"))
NUMBER_FORMATS = (
    ("1,234.56", re.compile(r"[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?")),
    ("1.234,56", re.compile(r"[+-]?(?:[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:,[0-9]+)?")),
)
ACCOUNT = re.compile(r"^[a-z][a-z0-9_]*$")

BAD_ACCOUNT = ("'{name}' cannot be an account name: use letters, digits and _, start with a letter, and do not "
               "use all. Name it with --account")
NOT_FOUND = "there is no file {path}"
ALREADY_LOADED = "this file is already loaded, into account '{account}'"
EMPTY = "the file is empty"
NOT_TEXT = "the file is not text"
NO_HEADER = ("no heading row was found in the first 20 rows. It needs a date, a description and an amount "
             "column, with headings such as Date, Description and Amount")
SHORT_ROW = "row {row} has fewer columns than the heading row"
NO_ROWS = "there are no rows under the heading row"
BAD_DATES = "the dates cannot all be read in one format: row {row} has '{cell}'"
AMBIGUOUS_DATES = "the dates could be {first} or {second}, and they give different dates"
BAD_NUMBERS = "the amounts cannot all be read in one format: row {row} has '{cell}'"
AMBIGUOUS_NUMBERS = ("the amounts could be written like 1,234.56 or like 1.234,56, and they give different "
                     "values")
NO_SIGN = "no answer was given on how it writes money going out"
SIGN_ROWS = "{name}: the first rows, as read:"
SIGN_QUESTION = ("In this file, is money going out written as a negative number (as on most bank statements) or "
                 "as a positive number (as on most card statements)? Type negative or positive.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Decimal) -> str:
    """A decimal as plain text, with its decimals as read."""
    return format(value, "f")


def _valid(name: str) -> bool:
    return bool(ACCOUNT.match(name)) and name != "all"


def account_name(path) -> str:
    """The account a file is named for: its stem, lower case, runs of other characters made `_` (SPEC 9.2)."""
    name = re.sub(r"[^a-z0-9]+", "_", Path(path).stem.lower()).strip("_")
    if not _valid(name):
        raise NotLoaded(BAD_ACCOUNT.format(name=name))
    return name


def _name(cell: str) -> str:
    """A heading cell as the column lists know it: no accents, case-folded, one space between words."""
    decomposed = unicodedata.normalize("NFKD", cell)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return " ".join("".join(char if char.isalnum() else " " for char in plain).split())


def _roles(record: list[str]) -> dict:
    """The column of each role found in a record: the cell whose name comes first in the role's list."""
    names = [_name(cell) for cell in record]
    found = {}
    for role, wanted in COLUMN_NAMES.items():
        for name in wanted:
            if name in names:
                found[role] = names.index(name)        # the leftmost cell of that name
                break
    return found


def _decode(data: bytes) -> str:
    if not data:
        raise NotLoaded(EMPTY)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1252")
        except UnicodeDecodeError:
            raise NotLoaded(NOT_TEXT) from None
    if not text.strip():
        raise NotLoaded(EMPTY)
    if "\x00" in text:
        raise NotLoaded(NOT_TEXT)
    return text


def _records(text: str, delimiter: str) -> list[list[str]] | None:
    try:
        return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    except csv.Error:
        return None


def _date(cell: str, form: str):
    try:
        return datetime.strptime(cell, form).date()
    except ValueError:
        return None


def _plain(cell: str) -> str:
    return "".join(char for char in cell if not char.isspace() and char not in "$€£")


def _number(cell: str, form: int) -> Decimal | None:
    plain = _plain(cell)
    if not NUMBER_FORMATS[form][1].fullmatch(plain):
        return None
    return Decimal(plain.replace(",", "") if form == 0 else plain.replace(".", "").replace(",", "."))


def _pick_dates(rows: list[dict]) -> tuple[str, list]:
    """Rule 5: the one format that reads every date cell. Returns (display name, the dates)."""
    cells = [row["date"] for row in rows]
    tried = [[_date(cell, form) for cell in cells] for form, _name_ in DATE_FORMATS]
    fits = [k for k, found in enumerate(tried) if None not in found]
    if not fits:
        best = min(range(len(tried)), key=lambda k: tried[k].count(None))          # the earlier on a tie
        k = tried[best].index(None)
        raise NotLoaded(BAD_DATES.format(row=rows[k]["row"], cell=cells[k]))
    first = fits[0]
    for other in fits[1:]:
        if tried[other] != tried[first]:
            raise NotLoaded(AMBIGUOUS_DATES.format(first=DATE_FORMATS[first][1], second=DATE_FORMATS[other][1]))
    return DATE_FORMATS[first][1], tried[first]


def _pick_numbers(rows: list[dict], has_balance: bool) -> tuple[str, list]:
    """Rule 6: the one format that reads every amount and balance cell. Returns (display name, values)."""
    cells = []          # (record number, cell, key): amount before balance in a row
    for row in rows:
        cells.append((row["row"], row["amount"], "amount"))
        if has_balance and row["balance"]:
            cells.append((row["row"], row["balance"], "balance"))
    tried = [[_number(cell, form) for _row, cell, _key in cells] for form in range(len(NUMBER_FORMATS))]
    fits = [form for form, found in enumerate(tried) if None not in found]
    if not fits:
        best = min(range(len(tried)), key=lambda form: tried[form].count(None))
        k = tried[best].index(None)
        raise NotLoaded(BAD_NUMBERS.format(row=cells[k][0], cell=cells[k][1]))
    if len(fits) > 1 and tried[fits[0]] != tried[fits[1]]:
        raise NotLoaded(AMBIGUOUS_NUMBERS)
    values = {(row, key): value for (row, _cell, key), value in zip(cells, tried[fits[0]])}
    return NUMBER_FORMATS[fits[0]][0], values


def _read(data: bytes) -> tuple[dict, dict]:
    """`read_table`, and the amount cell of each kept row as written, by record number (for the sign question)."""
    text = _decode(data)
    found = None
    for delimiter in DELIMITERS:
        records = _records(text, delimiter)
        if records is None:
            continue
        for k, record in enumerate(records[:HEADER_SEARCH]):
            roles = _roles(record)
            if all(role in roles for role in ("date", "description", "amount")):
                found = (delimiter, records, k, roles)
                break
        if found:
            break
    if not found:
        raise NotLoaded(NO_HEADER)
    delimiter, records, head, roles = found
    heading = [cell.strip() for cell in records[head]]

    rows, dropped = [], []
    for number, record in enumerate(records, start=1):
        if number <= head + 1:
            continue
        if all(not cell.strip() for cell in record):
            continue
        if len(record) == len(heading) and [cell.strip() for cell in record] == heading:
            dropped.append({"row": number, "reason": "repeated header"})
            continue
        if len(record) <= max(roles.values()):
            raise NotLoaded(SHORT_ROW.format(row=number))
        balance = record[roles["balance"]].strip() if "balance" in roles else ""
        rows.append({"row": number, "date": record[roles["date"]].strip(),
                     "amount": record[roles["amount"]].strip(),
                     "description": one_line(record[roles["description"]].strip()), "balance": balance})
    if not rows:
        raise NotLoaded(NO_ROWS)

    date_format, dates = _pick_dates(rows)
    number_format, values = _pick_numbers(rows, "balance" in roles)

    kept, same_kept, seen, earlier = [], [], set(), set()
    written = {}
    for row, day in zip(rows, dates):
        amount = values[(row["row"], "amount")]
        balance = values.get((row["row"], "balance"))
        if "balance" in roles:
            key = (day, amount, row["description"], balance)
            if balance is not None and key in seen:
                dropped.append({"row": row["row"], "reason": "repeated row"})
                continue
            seen.add(key)
        else:
            key = (day, amount, row["description"])
            if key in earlier:
                same_kept.append(row["row"])
            earlier.add(key)
        kept.append({"row": row["row"], "date": day.isoformat(), "amount": _text(amount),
                     "description": row["description"], "balance": None if balance is None else _text(balance)})
        written[row["row"]] = row["amount"]
    dropped.sort(key=lambda each: each["row"])

    reading = {"sha256": hashlib.sha256(data).hexdigest(), "delimiter": delimiter, "header_row": head + 1,
               "columns": {role: heading[roles[role]] if role in roles else None
                           for role in ("date", "description", "amount", "balance")},
               "date_format": date_format, "number_format": number_format,
               "newest_first": kept[0]["date"] > kept[-1]["date"],
               "rows": kept, "dropped": dropped, "same_kept": same_kept}
    return reading, written


def read_table(data: bytes) -> dict:
    """Read the bytes of a file into a reading (SPEC 9.2). Raises `NotLoaded` at the first rule that fails."""
    return _read(data)[0]


def _canonical(amount: str, sign: str) -> str:
    """The amount with money out negative; a zero has no minus."""
    value = Decimal(amount)
    if sign == "out_positive":
        value = -value
    return _text(abs(value) if value == 0 else value)


def load(conn, *, path, reading: dict, account: str, sign: str, sign_from: str, session_id: str) -> dict:
    """Write one reading into `imports` and `transactions`, and record `data.imported` (SPEC 9.2)."""
    if sign not in SIGNS:
        raise ValueError(f"sign must be one of {', '.join(SIGNS)}, not {sign!r}")
    if sign_from not in SIGN_FROMS:
        raise ValueError(f"sign_from must be one of {', '.join(SIGN_FROMS)}, not {sign_from!r}")
    row = conn.execute("SELECT account FROM imports WHERE sha256 = ?", (reading["sha256"],)).fetchone()
    if row is not None:
        raise NotLoaded(ALREADY_LOADED.format(account=row["account"]))
    kept = reading["rows"]
    ts = _now()
    dates = [each["date"] for each in kept]
    try:
        cursor = conn.execute(
            "INSERT INTO imports (ts, session_id, file, sha256, account, sign, report)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, session_id, str(path), reading["sha256"], account, sign, "{}"))
        import_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO transactions (import_id, account, date, amount, description, balance, row)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(import_id, account, each["date"], _canonical(each["amount"], sign), each["description"],
              each["balance"], each["row"]) for each in kept])
        imported = {"id": import_id, "ts": ts, "session_id": session_id, "file": str(path),
                    "name": Path(path).name, "sha256": reading["sha256"], "account": account, "sign": sign,
                    "sign_from": sign_from, "delimiter": reading["delimiter"],
                    "header_row": reading["header_row"], "columns": reading["columns"],
                    "date_format": reading["date_format"], "number_format": reading["number_format"],
                    "newest_first": reading["newest_first"], "transactions": len(kept), "first": min(dates),
                    "last": max(dates), "dropped": reading["dropped"], "same_kept": reading["same_kept"]}
        conn.execute("UPDATE imports SET report = ? WHERE id = ?", (json.dumps(imported), import_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    db.record_event(conn, session_id=session_id, kind="data.imported", actor="harness", payload=imported)
    return imported


def _ask_sign(name: str, reading: dict, written: dict, ask, say) -> str:
    """Show the first rows as read and ask how money going out is written (SPEC 9.2, step 5)."""
    say(SIGN_ROWS.format(name=name))
    for each in reading["rows"][:3]:
        say(f"  {each['date']}  {written[each['row']]}  {each['description']}")
    if ask is None:
        raise NotLoaded(NO_SIGN)
    while True:
        answer = ask(SIGN_QUESTION).strip().lower()
        if answer in ("negative", "neg", "-"):
            return "out_negative"
        if answer in ("positive", "pos", "+"):
            return "out_positive"
        if answer == "/quit":
            raise NotLoaded(NO_SIGN)


def add_file(conn, path, *, account=None, sign=None, sign_from, ask=None, say=print, session_id) -> dict:
    """Read and load one file. At the first failure it records `data.refused` and raises `NotLoaded` (SPEC 9.2)."""
    try:
        if not Path(path).is_file():
            raise NotLoaded(NOT_FOUND.format(path=path))
        if account is None:
            account = account_name(path)
        elif not _valid(account):
            raise NotLoaded(BAD_ACCOUNT.format(name=account))
        try:
            data = Path(path).read_bytes()
        except OSError:
            raise NotLoaded(NOT_FOUND.format(path=path)) from None
        row = conn.execute("SELECT account FROM imports WHERE sha256 = ?",
                           (hashlib.sha256(data).hexdigest(),)).fetchone()
        if row is not None:
            raise NotLoaded(ALREADY_LOADED.format(account=row["account"]))
        reading, written = _read(data)
        if sign is None:
            sign, sign_from = _ask_sign(Path(path).name, reading, written, ask, say), "asked"
        return load(conn, path=path, reading=reading, account=account, sign=sign, sign_from=sign_from,
                    session_id=session_id)
    except NotLoaded as refused:
        db.record_event(conn, session_id=session_id, kind="data.refused", actor="harness",
                        payload={"file": str(path), "reason": str(refused)})
        raise


def _import(row) -> dict:
    return json.loads(row["report"])


def list_imports(conn) -> list[dict]:
    """The import dict of every `imports` row, by id (SPEC 9.2)."""
    return [_import(row) for row in conn.execute("SELECT * FROM imports ORDER BY id")]


def clear_data(conn, *, session_id: str) -> dict:
    """Delete every transaction and every import, and record `data.cleared` (SPEC 9.2)."""
    transactions = conn.execute("DELETE FROM transactions").rowcount
    imports = conn.execute("DELETE FROM imports").rowcount
    conn.commit()
    removed = {"imports": imports, "transactions": transactions}
    db.record_event(conn, session_id=session_id, kind="data.cleared", actor="person", payload=removed)
    return removed
