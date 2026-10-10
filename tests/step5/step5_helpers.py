"""Shared by the step 5 tests (SPEC section 9: verification).

The fixed strings and the blocks below are copied from the SPEC on purpose: the tests check the harness against the
contract, not against its own constants. The helpers of steps 2 to 4 (a small brief, two example modules, script
builders, a recording person, a running server) are reused: this file puts those folders on the import path.

The brief of `h.make_brief()` has one figure in its particulars, "Rent is fixed at 1,150 a month", so a message with a
figure always has something to be checked against. The account files are small, written by the tests into
`tmp_path`, except where a test says it reads the real files of `tests/fixtures/accounts/example/`.
"""
import json
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "step4"))

import step4_helpers as s4                                   # noqa: E402  (after the path is set)
from step4_helpers import h, s3                              # noqa: E402,F401
from harness.model import ScriptedModel                      # noqa: E402

SESSION = h.SESSION
DAY = h.DAY
TODAY = DAY.isoformat()
EXAMPLE_DATA = ROOT / "tests" / "fixtures" / "accounts" / "example"
EXAMPLES = ROOT / "examples"

# ---- 9.2: the adapter -------------------------------------------------------------------------------------------

SIGNS = ("out_negative", "out_positive")
DELIMITERS = (",", ";", "\t", "|")
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

BAD_ACCOUNT = ("'{name}' cannot be an account name: use letters, digits and _, start with a letter, and do not use "
               "all. Name it with --account")
NOT_FOUND = "there is no file {path}"
ALREADY_LOADED = "this file is already loaded, into account '{account}'"
EMPTY = "the file is empty"
NOT_TEXT = "the file is not text"
NO_HEADER = ("no heading row was found in the first 20 rows. It needs a date, a description and an amount column, "
             "with headings such as Date, Description and Amount")
SHORT_ROW = "row {row} has fewer columns than the heading row"
NO_ROWS = "there are no rows under the heading row"
BAD_DATES = "the dates cannot all be read in one format: row {row} has '{cell}'"
AMBIGUOUS_DATES = "the dates could be {first} or {second}, and they give different dates"
BAD_NUMBERS = "the amounts cannot all be read in one format: row {row} has '{cell}'"
AMBIGUOUS_NUMBERS = ("the amounts could be written like 1,234.56 or like 1.234,56, and they give different values")
NO_SIGN = "no answer was given on how it writes money going out"
SIGN_ROWS = "{name}: the first rows, as read:"
SIGN_QUESTION = ("In this file, is money going out written as a negative number (as on most bank statements) or as a "
                 "positive number (as on most card statements)? Type negative or positive.")

# ---- 9.3: the command line --------------------------------------------------------------------------------------

DATA_LOADED = "{name}: loaded {count} transactions into account '{account}', {first} to {last}."
DATA_READ = ("  read: {delimiter} between columns, headings on row {row}, dates written {dates}, amounts written "
             "like {numbers}, money out written {sign}.")
DATA_HEADERS_LEFT = "  left out, a repeated heading row: rows {rows}."
DATA_REPEATS_LEFT = "  left out, the same date, amount, description and balance as an earlier row: rows {rows}."
DATA_SAME_KEPT = ("  kept, the same date, amount and description as an earlier row; with no balance column they "
                  "cannot be told apart from real repeats: rows {rows}.")
DATA_REFUSED = "{name}: not loaded: {reason}"
DATA_ADDED = "{loaded} of {total} files loaded."
DATA_LIST_LINE = ("{id}  {account}  {name}  {count} transactions  {first} to {last}  money out written {sign}  "
                  "balance column: {balance}")
DATA_MONTHS = "{scope}: full months {first} to {last}"
DATA_NO_MONTHS = "{scope}: no full month"
DATA_CLEARED = "Removed {imports} files and {transactions} transactions. What was loaded stays in the event log."
NO_DATA = "No account files are loaded. Add them with: python -m harness data add FILE ..."
NO_FILES = "Name the account files to add, for example: python -m harness data add statement.csv"
ONE_ACCOUNT = "--account names the account of one file. Add the files one at a time to name each account."
NO_EXAMPLE_DATA = "The example '{name}' has no account files in {folder}."

# ---- 9.4: the summaries -----------------------------------------------------------------------------------------

MAX_MONTHS = 12
MEASURES = {
    "money_in": "Money that came in, in each full calendar month. value is the average a month over the months asked for.",
    "money_out": "Money that went out, as a positive figure, in each full calendar month. value is the average a month over the months asked for.",
    "net": "Money in less money out, in each full calendar month. value is the average a month over the months asked for.",
    "balance": "The balance on the latest row of one account whose files have a balance column. value is that balance, as_of its date.",
}
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

# ---- 9.5: findings ----------------------------------------------------------------------------------------------

FINDING_KINDS = ("earlier", "data", "brief")
MAX_FINDINGS = 2
JUDGMENT_WORDS = ("actually", "but", "however", "wrong", "incorrect", "mistake", "mistaken", "error",
                  "should", "must", "clearly", "obviously", "really", "unfortunately")
FINDING_INTRO = "Two figures for the same thing differ. Only you can decide which one to use:"
FINDING_SAID = "You said: \"{claim}\""
FINDING_DATA = "Your loaded files show {figure}: {what}."
FINDING_BRIEF = "The brief says: \"{quote}\""
FINDING_NOW = "To save now as {name}: {value}"
FINDING_EARLIER = "Saved earlier ({when}) as {name}: {value}"
EARLIER_HERE = "in this conversation"
EARLIER_BEFORE = "in an earlier conversation"
FINDING_KEEP = "Keep what I said: {figure}"
FINDING_USE_DATA = "Use the figure from my files: {figure}"
FINDING_USE_BRIEF = "Use the figure in the brief: {figure}"
FINDING_USE_NEW = "Use the new value: {value}"
FINDING_KEEP_EARLIER = "Keep the earlier value: {value}"

FINDING_KEYS = ["id", "ts", "session_id", "kind", "claim", "claim_figure", "reference", "reference_figure",
                "summary", "input", "earlier", "pending_note", "difference", "block", "options", "status",
                "decision", "choice", "chosen"]

# ---- 9.6: the verifier ------------------------------------------------------------------------------------------

MAX_VERIFY_CALLS = 4
MAX_VERIFY_SUMMARIES = 6
VERIFY_PROGRESS = "  (checking your figures)"
VERIFY_FAILED = "  (the check of your figures did not finish: {reason})"
VERIFY_NO_REPORT = "[harness] Call report now, with an empty list of findings when nothing differs."
NO_REPORT_REASON = "the verifier gave no report"
SUMMARY_LIMIT = "No more summaries in this check. Call report."
REPORT_SHAPE = "report needs findings: a list, empty when nothing differs."
DROP_SHAPE = "it needs a claim, a kind (data or brief), a difference, and a quote (brief) or a summary (data)"
DROP_NOT_QUOTED = "the claim is not quoted from the person's message"
DROP_CLAIM_FIGURE = "the claim does not hold exactly one figure"
DROP_NOT_IN_BRIEF = "the quote is not in the brief's particulars or inputs"
DROP_NO_SUMMARY = "there is no data summary {summary} in this conversation"
DROP_REFERENCE_FIGURE = "the quote does not hold exactly one figure"
DROP_NOT_COMPARABLE = "one figure is a date and the other is not"
DROP_WITHIN_TOLERANCE = "the two figures are within 5% of each other"
DROP_DIFFERENCE_NUMBERS = "the difference has numbers that are not in the message, the brief or the summary: {numbers}"
DROP_TONE = "the difference uses the word '{word}'"
DROP_ALREADY = "finding {id} already raised this"
DROP_LIMIT = "only 2 findings are raised per message"

DATA_SUMMARY_SCHEMA = {"type": "object", "properties": {
    "measure": {"type": "string", "enum": ["money_in", "money_out", "net", "balance"]},
    "account": {"type": "string"},
    "months": {"type": "integer"}, "month": {"type": "string"}},
    "required": ["measure", "account"]}
REPORT_SCHEMA = {"type": "object", "properties": {
    "findings": {"type": "array", "items": {"type": "object", "properties": {
        "claim": {"type": "string"}, "kind": {"type": "string", "enum": ["data", "brief"]},
        "quote": {"type": "string"}, "summary": {"type": "integer"}, "difference": {"type": "string"}},
        "required": ["claim", "kind", "difference"]}}},
    "required": ["findings"]}

# ---- 9.7: the agent ---------------------------------------------------------------------------------------------

FINDING_NOTE = ("[harness] The harness checked the person's figures and opened finding {id}. Raise it now: call "
                "ask_decision with finding {id} and runs [], and nothing else. The person will see this block, word "
                "for word:\n{block}\nUntil they decide, run_module and save_input are refused and your replies are "
                "held back.")
FINDING_OPEN = ("Refused while finding {id} is open. Call ask_decision with finding {id} and runs [] first: the "
                "person decides which figure to use.")
FINDING_FIRST = ("[harness] Your reply was not shown, because finding {id} is open. Call ask_decision with finding "
                 "{id} and runs [] now.")
FINDING_RAISED = ("Not saved: '{name}' already holds a different value. The harness opened finding {id}. Call "
                  "ask_decision with finding {id} and runs [] next: the person decides which value to keep.")
FINDING_DECIDED = ("Not saved: the person already decided about this value of '{name}' (finding {id}). Carry on with "
                   "what they chose.")
FINDING_NOT_OPEN = "There is no open finding {finding} in this conversation."

ASK_DECISION_SCHEMA = h.ASK_DECISION_SCHEMA

# ---- the words the tests say ------------------------------------------------------------------------------------

CLAIM = "I spend about 5k a month"
MESSAGE = "I spend about 5k a month. How long until I reach my target?"
FIGURE_5K = "5k"
DIFFERENCE = "The loaded files show 4,132.31 going out a month on average over the last three full months."
SPENDING = "4132.31"
RENT_CLAIM = "My rent is 1,400 a month"
RENT_MESSAGE = "My rent is 1,400 a month. How long until I reach my target?"
RENT_QUOTE = h.PARTICULAR                                    # "Rent is fixed at 1,150 a month"
RENT_DIFFERENCE = "The brief gives the rent as 1,150 a month."
THINKING = ("say", "  (thinking)")
PROGRESS = ("say", VERIFY_PROGRESS)


def one_line(text):
    return " ".join(text.split())


# ---- text of account files --------------------------------------------------------------------------------------

def csv_text(rows, *, header=("Date", "Description", "Amount"), delimiter=",", newline="\n", final_newline=True):
    """A delimited text: the heading row and then each row, cells joined by the delimiter (no quoting)."""
    lines = [delimiter.join(line) for line in ([header] if header is not None else []) + [list(r) for r in rows]]
    return newline.join(lines) + (newline if final_newline else "")


def simple(rows=None, **options):
    """A small file in the default layout: Date, Description, Amount with ISO dates and point numbers."""
    rows = rows if rows is not None else [("2026-03-25", "Coffee", "-3.50"), ("2026-03-26", "Pay", "100.00")]
    return csv_text(rows, **options)


def read_ok(adapter, text, **options):
    """`read_table` of a text (encoded as UTF-8 unless bytes are given)."""
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    return adapter.read_table(data)


def refusal(adapter, data):
    """The message `read_table` raises `NotLoaded` with for the bytes (or text) given."""
    data = data if isinstance(data, bytes) else data.encode("utf-8")
    try:
        adapter.read_table(data)
    except adapter.NotLoaded as error:
        return str(error)
    raise AssertionError("read_table accepted the file")


def rows_of(reading):
    return [(r["row"], r["date"], r["amount"], r["description"], r["balance"]) for r in reading["rows"]]


READING_KEYS = {"sha256", "delimiter", "header_row", "columns", "date_format", "number_format", "newest_first", "rows",
                "dropped", "same_kept"}
IMPORT_KEYS = {"id", "ts", "session_id", "file", "name", "sha256", "account", "sign", "sign_from", "delimiter",
               "header_row", "columns", "date_format", "number_format", "newest_first", "transactions", "first",
               "last", "dropped", "same_kept"}


# ---- loading files into the database ----------------------------------------------------------------------------

def write(folder, name, content):
    """Write a file (text, UTF-8, or bytes) into a folder. Returns its path."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_bytes(content.encode("utf-8"))
    return path


def add(adapter, conn, path, *, sign="out_negative", sign_from="flag", account=None, session_id=SESSION, **options):
    return adapter.add_file(conn, path, account=account, sign=sign, sign_from=sign_from, session_id=session_id, **options)


def add_text(adapter, conn, folder, name, text, **options):
    return add(adapter, conn, write(folder, name, text), **options)


def load_example(adapter, conn, which=("checking_2026.csv", "savings_2026.csv", "card_2026.csv"), session_id="loading"):
    """The real files of tests/fixtures/accounts/example/: the bank files with money out negative, the card file positive."""
    imports = []
    for name in which:
        sign = "out_positive" if name.startswith("card") else "out_negative"
        imports.append(add(adapter, conn, EXAMPLE_DATA / name, sign=sign, session_id=session_id))
    return imports


def sql_rows(conn, query, params=()):
    return [dict(r) for r in conn.execute(query, params)]


def transactions(conn, account=None):
    query = "SELECT * FROM transactions" + (" WHERE account = ?" if account else "") + " ORDER BY id"
    return sql_rows(conn, query, (account,) if account else ())


# Rows put straight into the tables of 9.1, so that the summaries are tested alone (the schema is in the SPEC).

def put_import(conn, account, rows, *, name=None, newest_first=False, sign="out_negative", session_id="loading",
               file=None):
    """Insert one `imports` row and its `transactions` rows. `rows` are tuples (date, amount, description[, balance
    [, row]]); `row` defaults to 2, 3, ... Returns (import id, [transaction ids])."""
    name = name or f"{account}.csv"
    cells = []
    for index, row in enumerate(rows, 2):
        day, amount, description, *rest = row
        balance = rest[0] if rest else None
        number = rest[1] if len(rest) > 1 else index
        cells.append((day, amount, description, balance, number))
    dates = sorted(c[0] for c in cells)
    report = {"name": name, "file": file or name, "account": account, "sign": sign, "sign_from": "flag",
              "newest_first": newest_first, "delimiter": ",", "header_row": 1, "columns": {}, "date_format": "YYYY-MM-DD",
              "number_format": "1,234.56", "transactions": len(cells), "first": dates[0] if dates else None,
              "last": dates[-1] if dates else None, "dropped": [], "same_kept": []}
    cursor = conn.execute(
        "INSERT INTO imports (ts, session_id, file, sha256, account, sign, report) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("2026-03-14T10:00:00+00:00", session_id, file or name, f"{account}-{name}-{len(cells)}-{cells[:1]}", account,
         sign, json.dumps({**report})))
    import_id = cursor.lastrowid
    report["id"] = import_id
    report["ts"] = "2026-03-14T10:00:00+00:00"
    report["session_id"] = session_id
    report["sha256"] = f"{account}-{name}-{len(cells)}-{cells[:1]}"
    conn.execute("UPDATE imports SET report = ? WHERE id = ?", (json.dumps(report), import_id))
    ids = []
    for day, amount, description, balance, number in cells:
        cursor = conn.execute(
            "INSERT INTO transactions (import_id, account, date, amount, description, balance, row) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", (import_id, account, day, amount, description, balance, number))
        ids.append(cursor.lastrowid)
    conn.commit()
    return import_id, ids


def month_days(month):
    """First and last day of 'YYYY-MM' as text."""
    year, number = map(int, month.split("-"))
    following = date(year + (number == 12), number % 12 + 1, 1)
    last = date.fromordinal(following.toordinal() - 1)
    return f"{month}-01", last.isoformat()


def month_rows(month, ins=(), outs=()):
    """The rows of one full month: a zero row on its first and on its last day (so the rows reach both ends), the
    money in as positive amounts and the money out as negative amounts on the 15th."""
    first, last = month_days(month)
    rows = [(first, "0.00", "start of month")]
    rows += [(f"{month}-15", str(Decimal(a)), "in") for a in ins]
    rows += [(f"{month}-15", str(-Decimal(a)), "out") for a in outs]
    rows += [(last, "0.00", "end of month")]
    return rows


def put_months(conn, account, months, **options):
    """`months` maps 'YYYY-MM' to (ins, outs). Returns (import id, ids)."""
    rows = []
    for month, (ins, outs) in months.items():
        rows += month_rows(month, ins, outs)
    return put_import(conn, account, rows, **options)


def cents(value):
    """Round half up to cents, as text with two decimals and no '-0.00' (SPEC 9.4)."""
    value = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if value == 0:
        value = Decimal("0.00")
    return f"{value:.2f}"


# ---- the scripted model: the verifier and the agent are answered in the order they are called -------------------

def verifier_first_line():
    return h.prompt_text("verifier.md").strip().splitlines()[0]


def role_of(system):
    """verifier, aside, spec_writer, ... or analyst."""
    if system.strip().startswith(verifier_first_line()):
        return "verifier"
    return s4.role_of(system)


class Model(ScriptedModel):
    """A scripted model that notes each call, by role, in the person's log."""

    def __init__(self, script, person=None):
        super().__init__(script)
        self.person = person

    def complete(self, *, system, messages, tools=()):
        if self.person is not None:
            self.person.log.append(("call", role_of(system)))
        return super().complete(system=system, messages=messages, tools=tools)

    def roles(self):
        return [role_of(call["system"]) for call in self.calls]

    def of(self, role):
        return [call for call in self.calls if role_of(call["system"]) == role]


def summary_call(measure="money_out", account="all", **period):
    """The verifier's tool call `data_summary` (months 3 unless a period is given)."""
    arguments = {"measure": measure, "account": account}
    if measure != "balance":
        arguments.update(period or {"months": 3})
    return h.tool("data_summary", arguments)


def entry(claim=CLAIM, kind="data", *, summary=1, quote=None, difference=DIFFERENCE, **changes):
    """One finding as the verifier sends it to `report`. A change of DROP removes that key."""
    item = {"claim": claim, "kind": kind, "difference": difference}
    if kind == "data":
        item["summary"] = summary
    else:
        item["quote"] = RENT_QUOTE if quote is None else quote
    item.update(changes)
    return {key: value for key, value in item.items() if value is not s4.DROP}


def brief_entry(claim=RENT_CLAIM, quote=RENT_QUOTE, difference=RENT_DIFFERENCE, **changes):
    return entry(claim, "brief", quote=quote, difference=difference, **changes)


def report(*entries):
    return h.tool("report", {"findings": list(entries)})


def ask_finding(finding=1, **extra):
    """The agent's call that raises a finding (SPEC 9.7): only the finding and `runs`."""
    return h.tool("ask_decision", {"finding": finding, "runs": [], **extra})


def finding_ask(finding, **extra):
    return ask_finding(finding, **extra)


# ---- the blocks of 9.5, worked out here -------------------------------------------------------------------------

def finding_block(kind="data", *, claim=CLAIM, claim_figure="5k", reference=None, reference_figure=SPENDING,
                  difference=DIFFERENCE, name="monthly_spending", when=EARLIER_BEFORE, value=None):
    """The block of a finding, joined by newlines. For `earlier`: `claim` is the new value and `reference` the saved one."""
    if kind == "earlier":
        new, saved = one_line(claim), one_line(reference)
        lines = [FINDING_INTRO, "  " + FINDING_NOW.format(name=name, value=new),
                 "  " + FINDING_EARLIER.format(when=when, name=name, value=saved),
                 "    1. " + FINDING_USE_NEW.format(value=new), "    2. " + FINDING_KEEP_EARLIER.format(value=saved)]
        return "\n".join(lines)
    third = FINDING_DATA.format(figure=one_line(reference_figure), what=one_line(reference or ""))
    if kind == "brief":
        third = FINDING_BRIEF.format(quote=one_line(reference))
    use = FINDING_USE_DATA if kind == "data" else FINDING_USE_BRIEF
    lines = [FINDING_INTRO, "  " + FINDING_SAID.format(claim=one_line(claim)), "  " + third,
             "  " + one_line(difference),
             "    1. " + FINDING_KEEP.format(figure=one_line(claim_figure)),
             "    2. " + use.format(figure=one_line(reference_figure))]
    return "\n".join(lines)


SPENDING_WORDS = ("money out a month, on average over the 3 full months 2026-06 to 2026-08, all accounts")
DATA_BLOCK = finding_block("data", reference=SPENDING_WORDS)
BRIEF_BLOCK = finding_block("brief", claim=RENT_CLAIM, claim_figure="1,400", reference=RENT_QUOTE,
                            reference_figure="1,150", difference=RENT_DIFFERENCE)
OPTIONS_DATA = [FINDING_KEEP.format(figure="5k"), FINDING_USE_DATA.format(figure=SPENDING)]
OPTIONS_BRIEF = [FINDING_KEEP.format(figure="1,400"), FINDING_USE_BRIEF.format(figure="1,150")]


# ---- reading what was recorded ----------------------------------------------------------------------------------

def events(conn, kind=None):
    return h.events(conn, kind)


def payloads(conn, kind):
    return h.payloads(conn, kind)


def actors(conn, kind):
    return [actor for k, actor, _ in h.events(conn, kind)]


def kinds_after_start(conn):
    """The event kinds of the conversation, after its ask.started."""
    names = h.kinds(conn)
    return names[names.index("ask.started") + 1:]


def finding_rows(conn):
    return sql_rows(conn, "SELECT * FROM findings ORDER BY id")


def summary_rows(conn):
    return sql_rows(conn, "SELECT * FROM data_summaries ORDER BY id")


def tool_results(model, call_index):
    """The tool messages among the messages of one model call, in order."""
    return [m for m in model.calls[call_index]["messages"] if m["role"] == "tool"]


def result_content(model, call_index, position=-1):
    return h.tool_message(model, call_index, position)["content"]


def saved_input(conn, name):
    row = conn.execute("SELECT * FROM inputs WHERE name = ?", (name,)).fetchone()
    return None if row is None else dict(row)


def put_input(conn, name, value, note="said earlier", session_id="an-earlier-session"):
    """A saved input as `save_input` stores it (SPEC 5.9: the value as `json.dumps(value)`)."""
    conn.execute("INSERT OR REPLACE INTO inputs (name, value, note, ts, session_id) VALUES (?, ?, ?, ?, ?)",
                 (name, json.dumps(value), note, "2026-03-01T09:00:00+00:00", session_id))
    conn.commit()


# ---- a message with four brief findings (SPEC 9.6: two a message) -------------------------------------------------

WIDE_BRIEF = h.make_brief(particulars=[
    {"what": "Rent is 1,150 a month", "handling": "Count it"}, {"what": "The gym is 40 a month", "handling": "Count it"},
    {"what": "The phone is 20 a month", "handling": "Count it"}, {"what": "The car is 300 a month", "handling": "Count it"}])
WIDE_MESSAGE = "My rent is 1,400 a month, my gym is 90 a month, my phone is 60 a month and my car is 700 a month."
_WIDE = {"rent": ("My rent is 1,400 a month", "1,400", "Rent is 1,150 a month", "1,150"),
         "gym": ("my gym is 90 a month", "90", "The gym is 40 a month", "40"),
         "phone": ("my phone is 60 a month", "60", "The phone is 20 a month", "20"),
         "car": ("my car is 700 a month", "700", "The car is 300 a month", "300")}


def wide_entry(name):
    claim, _, quote, shown = _WIDE[name]
    return brief_entry(claim, quote, f"The brief gives the {name} as {shown} a month.")


def wide_block(name):
    claim, claim_figure, quote, shown = _WIDE[name]
    return finding_block("brief", claim=claim, claim_figure=claim_figure, reference=quote, reference_figure=shown,
                         difference=f"The brief gives the {name} as {shown} a month.")
