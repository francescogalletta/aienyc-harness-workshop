"""SPEC 9.3: `python -m harness data add`, `data list` and `data clear`: the lines printed and the exit codes."""
import pytest

import step5_helpers as s5
from step5_helpers import EXAMPLE_DATA, ROOT, h, s3

SPANISH = "Fecha;Concepto;Importe;Saldo\n25/03/2026;Shop;-1.234,56;5.000,00\n26/03/2026;Pay;2.000,00;7.000,00\n"
BANK = "Date,Description,Amount,Balance\n2026-03-25,Shop,-5.00,95.00\n2026-03-26,Pay,10.00,105.00\n"
CHECKING = "tests/fixtures/accounts/example/checking_2026.csv"
SAVINGS = "tests/fixtures/accounts/example/savings_2026.csv"
CARD = "tests/fixtures/accounts/example/card_2026.csv"


def cli(*args, typed=""):
    return h.run_cli(list(args), typed)


def lines(text):
    return text.rstrip("\n").split("\n") if text.strip() else []


def sessions(conn, kind):
    return [r["session_id"] for r in s5.sql_rows(conn, "SELECT session_id FROM events WHERE kind = ? ORDER BY id", (kind,))]


def data_events(conn):
    return [kind for kind in h.kinds(conn) if kind.startswith("data.")]


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "files"


def loaded_line(name, count, account, first, last):
    return s5.DATA_LOADED.format(name=name, count=count, account=account, first=first, last=last)


def read_line(delimiter, dates, numbers, sign, row=1):
    return s5.DATA_READ.format(delimiter=delimiter, row=row, dates=dates, numbers=numbers, sign=sign)


# ---- data add: what is printed -----------------------------------------------------------------------------------------

def test_the_spec_example_for_the_current_account(conn):
    result = cli("data", "add", CHECKING, "--sign", "negative")
    assert result.returncode == 0 and result.stderr == ""
    assert lines(result.stdout) == [
        "checking_2026.csv: loaded 112 transactions into account 'checking_2026', 2026-01-01 to 2026-09-29.",
        "  read: semicolons between columns, headings on row 1, dates written DD/MM/YYYY, amounts written like "
        "1.234,56, money out written negative.",
        "  left out, a repeated heading row: rows 38.",
        "  left out, the same date, amount, description and balance as an earlier row: rows 39, 40.",
        "1 of 1 files loaded."]












def test_a_repeated_row_and_a_repeated_heading_are_listed_apart(folder):
    row = "2026-03-25,Shop,-5.00,95.00\n"
    text = "Date,Description,Amount,Balance\n" + row + row + "Date,Description,Amount,Balance\n" + row
    result = cli("data", "add", str(s5.write(folder, "bank.csv", text)), "--sign", "negative")
    assert lines(result.stdout)[2:-1] == [
        "  left out, a repeated heading row: rows 4.",
        "  left out, the same date, amount, description and balance as an earlier row: rows 3, 5."]








# ---- data add: several files, and refusals ------------------------------------------------------------------------------



def test_a_file_that_is_not_loaded_is_printed_and_the_exit_code_is_1(folder, conn):
    good = s5.write(folder, "bank.csv", BANK)
    empty = s5.write(folder, "empty.csv", "")
    result = cli("data", "add", str(good), str(empty), str(folder / "missing.csv"), "--sign", "negative")
    printed = lines(result.stdout)
    assert printed[0].startswith("bank.csv: loaded")
    assert printed[2:] == ["empty.csv: not loaded: " + s5.EMPTY,
                           "missing.csv: not loaded: " + s5.NOT_FOUND.format(path=str(folder / "missing.csv")),
                           "1 of 3 files loaded."]
    assert result.returncode == 1 and result.stderr == ""














# ---- data add: nothing loaded, nothing recorded ---------------------------------------------------------------------------

def test_no_files_is_an_error(conn):
    result = cli("data", "add")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.strip() == s5.NO_FILES




def test_account_with_more_than_one_file_is_an_error_and_loads_nothing(folder, conn):
    one, two = s5.write(folder, "one.csv", BANK), s5.write(folder, "two.csv", s5.simple())
    result = cli("data", "add", str(one), str(two), "--sign", "negative", "--account", "mine")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.strip() == s5.ONE_ACCOUNT
    assert s5.sql_rows(conn, "SELECT * FROM imports") == []




# ---- data add: the sign is asked when it is not given -------------------------------------------------------------------









def test_a_sign_flag_means_nobody_is_asked(folder, conn):
    path = s5.write(folder, "bank.csv", BANK)
    result = cli("data", "add", str(path), "--sign", "positive")
    assert s5.SIGN_QUESTION not in result.stdout
    assert [p["sign_from"] for p in s5.payloads(conn, "data.imported")] == ["flag"]


# ---- events and sessions -----------------------------------------------------------------------------------------------





# ---- data list ------------------------------------------------------------------------------------------------------





def load_the_example_files():
    assert cli("data", "add", CHECKING, SAVINGS, "--sign", "negative").returncode == 0
    assert cli("data", "add", CARD, "--sign", "positive").returncode == 0


def list_line(number, account, name, count, first, last, sign, balance):
    return s5.DATA_LIST_LINE.format(id=number, account=account, name=name, count=count, first=first, last=last,
                                    sign=sign, balance=balance)


def test_list_prints_each_import_and_then_the_full_months(conn):
    load_the_example_files()
    result = cli("data", "list")
    assert result.returncode == 0 and result.stderr == ""
    assert result.stdout.rstrip("\n").split("\n") == [
        list_line(1, "checking_2026", "checking_2026.csv", 112, "2026-01-01", "2026-09-29", "negative", "yes"),
        list_line(2, "savings_2026", "savings_2026.csv", 12, "2026-01-29", "2026-09-30", "negative", "yes"),
        list_line(3, "card_2026", "card_2026.csv", 248, "2026-01-02", "2026-09-29", "positive", "no"),
        "",
        s5.DATA_MONTHS.format(scope="account 'card_2026'", first="2026-02", last="2026-08"),
        s5.DATA_MONTHS.format(scope="account 'checking_2026'", first="2026-01", last="2026-08"),
        s5.DATA_MONTHS.format(scope="account 'savings_2026'", first="2026-02", last="2026-09"),
        s5.DATA_MONTHS.format(scope="all accounts", first="2026-02", last="2026-08")]








# ---- data clear -----------------------------------------------------------------------------------------------------



def test_clear_removes_the_files_and_the_transactions(folder, conn):
    cli("data", "add", str(s5.write(folder, "one.csv", BANK)), str(s5.write(folder, "two.csv", s5.simple())),
        "--sign", "negative")
    result = cli("data", "clear")
    assert result.returncode == 0 and result.stderr == ""
    assert lines(result.stdout) == [s5.DATA_CLEARED.format(imports=2, transactions=4)]
    assert s5.sql_rows(conn, "SELECT * FROM imports") == [] and s5.transactions(conn) == []
    assert s5.events(conn, "data.cleared") == [("data.cleared", "person", {"imports": 2, "transactions": 4})]
    assert len(s5.events(conn, "data.imported")) == 2
    assert lines(cli("data", "list").stdout) == [s5.NO_DATA]








# ---- example mode ---------------------------------------------------------------------------------------------------

EXAMPLE_ENV = {"HARNESS_EXAMPLE": "demo", "HARNESS_DB": None, "HARNESS_BRIEF_DIR": None, "HARNESS_MODULES_DIR": None}


def run_in_example(workdir, *args, typed=""):
    return s3.run_in(workdir, list(args), typed, **EXAMPLE_ENV)


def example_with_data(tmp_path, files=None):
    parent = tmp_path / "work" / "examples"
    s3.make_example(parent, "demo")
    (parent / "demo" / "data").mkdir(parents=True, exist_ok=True)
    for name, content in (files if files is not None else {"a_bank.csv": BANK, "b_other.csv": s5.simple()}).items():
        target = parent / "demo" / "data" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return tmp_path / "work"


def stderr_of(result):
    """What the command said on standard error, without the line that tells the example was copied (SPEC 4.8)."""
    return "".join(line for line in result.stderr.splitlines(keepends=True) if not line.startswith("Copied the example"))


def example_events(workdir):
    return s3.stored_events(workdir / "my" / "var" / "examples" / "demo" / "harness.db")




















