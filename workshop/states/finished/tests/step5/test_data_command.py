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


def test_the_other_two_example_files(conn):
    result = cli("data", "add", SAVINGS, "--sign", "negative")
    assert lines(result.stdout) == [
        loaded_line("savings_2026.csv", 12, "savings_2026", "2026-01-29", "2026-09-30"),
        read_line("semicolons", "DD/MM/YYYY", "1.234,56", "negative"), "1 of 1 files loaded."]
    result = cli("data", "add", CARD, "--sign", "positive")
    assert lines(result.stdout) == [
        loaded_line("card_2026.csv", 248, "card_2026", "2026-01-02", "2026-09-29"),
        read_line("commas", "YYYY-MM-DD", "1,234.56", "positive"), "1 of 1 files loaded."]
    assert result.returncode == 0


@pytest.mark.parametrize("delimiter, word", [(",", "commas"), (";", "semicolons"), ("\t", "tabs"), ("|", "bars")])
def test_the_delimiter_is_named(folder, delimiter, word):
    path = s5.write(folder, "bank.csv", s5.simple(delimiter=delimiter))
    result = cli("data", "add", str(path), "--sign", "negative")
    assert lines(result.stdout)[1] == read_line(word, "YYYY-MM-DD", "1,234.56", "negative")


def test_the_row_of_the_headings_is_shown(folder):
    path = s5.write(folder, "bank.csv", "Statement\nIssued today\n" + s5.simple())
    result = cli("data", "add", str(path), "--sign", "positive")
    assert lines(result.stdout)[1] == read_line("commas", "YYYY-MM-DD", "1,234.56", "positive", row=3)


def test_the_name_is_the_file_name_and_not_the_path(folder):
    path = s5.write(folder / "deep" / "er", "My Bank.csv", BANK)
    result = cli("data", "add", str(path), "--sign", "negative")
    assert lines(result.stdout)[0] == loaded_line("My Bank.csv", 2, "my_bank", "2026-03-25", "2026-03-26")


def test_the_sign_is_named_as_it_was_given(folder):
    path = s5.write(folder, "bank.csv", BANK)
    assert "money out written positive." in cli("data", "add", str(path), "--sign", "positive").stdout


def test_a_repeated_row_and_a_repeated_heading_are_listed_apart(folder):
    row = "2026-03-25,Shop,-5.00,95.00\n"
    text = "Date,Description,Amount,Balance\n" + row + row + "Date,Description,Amount,Balance\n" + row
    result = cli("data", "add", str(s5.write(folder, "bank.csv", text)), "--sign", "negative")
    assert lines(result.stdout)[2:-1] == [
        "  left out, a repeated heading row: rows 4.",
        "  left out, the same date, amount, description and balance as an earlier row: rows 3, 5."]


def test_only_the_lists_that_are_not_empty_are_printed(folder):
    row = "2026-03-25,Shop,-5.00,95.00\n"
    result = cli("data", "add", str(s5.write(folder, "bank.csv", "Date,Description,Amount,Balance\n" + row + row)),
                 "--sign", "negative")
    assert lines(result.stdout)[2:-1] == [s5.DATA_REPEATS_LEFT.format(rows="3")]
    result = cli("data", "add", str(s5.write(folder, "two.csv", BANK + "Date,Description,Amount,Balance\n")),
                 "--sign", "negative")
    assert lines(result.stdout)[2:-1] == [s5.DATA_HEADERS_LEFT.format(rows="4")]
    assert len(lines(cli("data", "add", str(s5.write(folder, "three.csv", s5.simple())), "--sign", "negative").stdout)) == 3


def test_equal_rows_kept_without_a_balance_column_are_listed(folder):
    row = "2026-03-25,Shop,-5.00\n"
    result = cli("data", "add", str(s5.write(folder, "card.csv", "Date,Description,Amount\n" + row * 3)),
                 "--sign", "positive")
    assert lines(result.stdout) == [
        loaded_line("card.csv", 3, "card", "2026-03-25", "2026-03-25"),
        read_line("commas", "YYYY-MM-DD", "1,234.56", "positive"),
        s5.DATA_SAME_KEPT.format(rows="3, 4"), "1 of 1 files loaded."]


def test_the_lines_come_in_the_order_of_the_contract(folder):
    row = "2026-03-25,Shop,-5.00,95.00\n"
    head = "Date,Description,Amount,Balance\n"
    result = cli("data", "add", str(s5.write(folder, "bank.csv", head + row + row + head + row)), "--sign", "negative")
    printed = lines(result.stdout)
    assert printed[0].startswith("bank.csv: loaded") and printed[1].startswith("  read:")
    assert printed[2].startswith("  left out, a repeated heading row") and printed[3].startswith("  left out, the same date")


# ---- data add: several files, and refusals ------------------------------------------------------------------------------

def test_files_are_loaded_in_the_order_given(folder):
    b = s5.write(folder, "b.csv", BANK)
    a = s5.write(folder, "a.csv", s5.simple())
    result = cli("data", "add", str(b), str(a), "--sign", "negative")
    printed = lines(result.stdout)
    assert printed[0].startswith("b.csv: loaded") and printed[2].startswith("a.csv: loaded")
    assert printed[-1] == "2 of 2 files loaded." and result.returncode == 0


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


def test_the_other_files_are_loaded_when_one_is_refused(folder, conn):
    cli("data", "add", str(s5.write(folder, "bad.csv", "")), str(s5.write(folder, "good.csv", BANK)), "--sign", "negative")
    assert [r["account"] for r in s5.sql_rows(conn, "SELECT account FROM imports")] == ["good"]


def test_the_reason_is_the_message_of_the_adapter(folder):
    expectations = {"nothing.csv": ("just words\n", s5.NO_HEADER), "norows.csv": ("Date,Description,Amount\n", s5.NO_ROWS),
                    "2026.csv": (BANK, s5.BAD_ACCOUNT.format(name="2026")),
                    "dates.csv": (s5.simple([("03/04/2026", "x", "1.00")]), s5.AMBIGUOUS_DATES.format(
                        first="DD/MM/YYYY", second="MM/DD/YYYY"))}
    for name, (text, reason) in expectations.items():
        result = cli("data", "add", str(s5.write(folder, name, text)), "--sign", "negative")
        assert lines(result.stdout) == [f"{name}: not loaded: {reason}", "0 of 1 files loaded."], name
        assert result.returncode == 1


def test_the_same_file_twice_is_loaded_once(folder):
    path = str(s5.write(folder, "bank.csv", BANK))
    result = cli("data", "add", path, path, "--sign", "negative")
    printed = lines(result.stdout)
    assert printed[-2:] == ["bank.csv: not loaded: " + s5.ALREADY_LOADED.format(account="bank"), "1 of 2 files loaded."]
    assert result.returncode == 1


def test_a_file_loaded_by_an_earlier_command_is_refused(folder):
    path = str(s5.write(folder, "bank.csv", BANK))
    cli("data", "add", path, "--sign", "negative")
    again = cli("data", "add", path, "--sign", "negative")
    assert lines(again.stdout) == ["bank.csv: not loaded: " + s5.ALREADY_LOADED.format(account="bank"),
                                   "0 of 1 files loaded."]
    assert again.returncode == 1


def test_account_names_one_file(folder, conn):
    path = s5.write(folder, "2026.csv", BANK)
    result = cli("data", "add", str(path), "--sign", "negative", "--account", "my_bank")
    assert lines(result.stdout)[0] == loaded_line("2026.csv", 2, "my_bank", "2026-03-25", "2026-03-26")
    assert result.returncode == 0


def test_an_account_name_that_is_not_valid_is_refused_as_a_file(folder):
    path = s5.write(folder, "bank.csv", BANK)
    result = cli("data", "add", str(path), "--sign", "negative", "--account", "All")
    assert lines(result.stdout) == ["bank.csv: not loaded: " + s5.BAD_ACCOUNT.format(name="All"), "0 of 1 files loaded."]
    assert result.returncode == 1


# ---- data add: nothing loaded, nothing recorded ---------------------------------------------------------------------------

def test_no_files_is_an_error(conn):
    result = cli("data", "add")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.strip() == s5.NO_FILES


def test_no_files_with_a_sign_is_the_same_error(conn):
    result = cli("data", "add", "--sign", "negative")
    assert result.returncode == 1 and result.stderr.strip() == s5.NO_FILES


def test_account_with_more_than_one_file_is_an_error_and_loads_nothing(folder, conn):
    one, two = s5.write(folder, "one.csv", BANK), s5.write(folder, "two.csv", s5.simple())
    result = cli("data", "add", str(one), str(two), "--sign", "negative", "--account", "mine")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.strip() == s5.ONE_ACCOUNT
    assert s5.sql_rows(conn, "SELECT * FROM imports") == []


def test_the_errors_record_nothing(folder, conn):
    cli("data", "add")
    one, two = s5.write(folder, "one.csv", BANK), s5.write(folder, "two.csv", s5.simple())
    cli("data", "add", str(one), str(two), "--account", "mine", "--sign", "negative")
    assert data_events(conn) == []


# ---- data add: the sign is asked when it is not given -------------------------------------------------------------------

def test_without_sign_each_file_is_asked_about(folder, conn):
    one, two = s5.write(folder, "one.csv", BANK), s5.write(folder, "two.csv", s5.simple())
    result = cli("data", "add", str(one), str(two), typed="negative\npositive\n")
    assert result.returncode == 0 and "2 of 2 files loaded." in result.stdout
    assert s5.SIGN_ROWS.format(name="one.csv") in result.stdout and s5.SIGN_ROWS.format(name="two.csv") in result.stdout
    assert result.stdout.count(s5.SIGN_QUESTION) == 2
    rows = s5.sql_rows(conn, "SELECT account, sign FROM imports ORDER BY id")
    assert [(r["account"], r["sign"]) for r in rows] == [("one", "out_negative"), ("two", "out_positive")]
    assert [p["sign_from"] for p in s5.payloads(conn, "data.imported")] == ["asked", "asked"]
    assert "money out written negative." in result.stdout and "money out written positive." in result.stdout


def test_the_rows_are_shown_before_the_question(folder):
    path = s5.write(folder, "bank.csv", s5.simple([("2026-03-25", "Coffee", "-3.50")]))
    result = cli("data", "add", str(path), typed="negative\n")
    shown = result.stdout
    assert shown.index(s5.SIGN_ROWS.format(name="bank.csv")) < shown.index("  2026-03-25  -3.50  Coffee") < shown.index(
        s5.SIGN_QUESTION)


def test_the_end_of_input_leaves_the_file_unloaded(folder, conn):
    path = s5.write(folder, "bank.csv", BANK)
    result = cli("data", "add", str(path))
    assert "bank.csv: not loaded: " + s5.NO_SIGN in result.stdout
    assert lines(result.stdout)[-1] == "0 of 1 files loaded." and result.returncode == 1
    assert s5.sql_rows(conn, "SELECT * FROM imports") == []


def test_quit_leaves_that_file_unloaded_and_the_next_is_still_asked(folder):
    one, two = s5.write(folder, "one.csv", BANK), s5.write(folder, "two.csv", s5.simple())
    result = cli("data", "add", str(one), str(two), typed="/quit\nnegative\n")
    assert "one.csv: not loaded: " + s5.NO_SIGN in result.stdout
    assert "two.csv: loaded 2 transactions" in result.stdout
    assert lines(result.stdout)[-1] == "1 of 2 files loaded." and result.returncode == 1


def test_a_sign_flag_means_nobody_is_asked(folder, conn):
    path = s5.write(folder, "bank.csv", BANK)
    result = cli("data", "add", str(path), "--sign", "positive")
    assert s5.SIGN_QUESTION not in result.stdout
    assert [p["sign_from"] for p in s5.payloads(conn, "data.imported")] == ["flag"]


# ---- events and sessions -----------------------------------------------------------------------------------------------

def test_the_events_of_a_command_carry_its_own_session_id(folder, conn):
    one, two = s5.write(folder, "one.csv", BANK), s5.write(folder, "two.csv", s5.simple())
    cli("data", "add", str(one), str(two), str(folder / "missing.csv"), "--sign", "negative")
    first = sessions(conn, "data.imported") + sessions(conn, "data.refused")
    assert len(first) == 3 and len(set(first)) == 1 and first[0]
    cli("data", "add", str(s5.write(folder, "three.csv", "Date,Description,Amount\n2026-03-25,x,1\n")), "--sign", "negative")
    later = sessions(conn, "data.imported")
    assert len(set(later)) == 2


def test_a_refused_file_is_recorded_with_the_path_as_given(folder, conn):
    given = str(folder / "missing.csv")
    cli("data", "add", given, "--sign", "negative")
    assert s5.payloads(conn, "data.refused") == [{"file": given, "reason": s5.NOT_FOUND.format(path=given)}]


# ---- data list ------------------------------------------------------------------------------------------------------

def test_list_with_nothing_loaded(conn):
    result = cli("data", "list")
    assert result.returncode == 0 and lines(result.stdout) == [s5.NO_DATA] and result.stderr == ""


def test_list_makes_the_database_and_records_nothing(conn):
    cli("data", "list")
    assert data_events(conn) == []


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


def test_list_says_when_an_account_has_no_full_month(folder):
    cli("data", "add", str(s5.write(folder, "bank.csv", BANK)), "--sign", "negative")
    assert cli("data", "list").stdout.rstrip("\n").split("\n") == [
        list_line(1, "bank", "bank.csv", 2, "2026-03-25", "2026-03-26", "negative", "yes"), "",
        s5.DATA_NO_MONTHS.format(scope="account 'bank'"), s5.DATA_NO_MONTHS.format(scope="all accounts")]


def test_list_gives_one_account_line_per_account_not_per_file(folder):
    one = s5.write(folder, "one.csv", s5.simple([("2026-03-01", "a", "1.00"), ("2026-03-31", "b", "1.00")]))
    two = s5.write(folder, "two.csv", s5.simple([("2026-04-01", "a", "1.00"), ("2026-04-30", "b", "1.00")]))
    cli("data", "add", str(one), "--sign", "negative", "--account", "joint")
    cli("data", "add", str(two), "--sign", "negative", "--account", "joint")
    printed = cli("data", "list").stdout.rstrip("\n").split("\n")
    assert printed[2] == ""
    assert printed[3:] == [s5.DATA_MONTHS.format(scope="account 'joint'", first="2026-03", last="2026-04"),
                           s5.DATA_MONTHS.format(scope="all accounts", first="2026-03", last="2026-04")]


def test_list_shows_a_single_full_month_as_the_first_and_the_last(folder):
    one = s5.write(folder, "one.csv", s5.simple([("2026-03-01", "a", "1.00"), ("2026-03-31", "b", "1.00")]))
    cli("data", "add", str(one), "--sign", "negative")
    printed = cli("data", "list").stdout.rstrip("\n").split("\n")
    assert printed[-2:] == [s5.DATA_MONTHS.format(scope="account 'one'", first="2026-03", last="2026-03"),
                            s5.DATA_MONTHS.format(scope="all accounts", first="2026-03", last="2026-03")]


# ---- data clear -----------------------------------------------------------------------------------------------------

def test_clear_with_nothing_loaded_prints_no_data_and_records_nothing(conn):
    result = cli("data", "clear")
    assert result.returncode == 0 and lines(result.stdout) == [s5.NO_DATA]
    assert s5.events(conn, "data.cleared") == []


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


def test_clear_asks_nothing(folder):
    cli("data", "add", str(s5.write(folder, "one.csv", BANK)), "--sign", "negative")
    result = cli("data", "clear", typed="")
    assert result.returncode == 0 and "Removed 1 files and 2 transactions" in result.stdout
    assert "> " not in result.stdout


def test_a_second_clear_finds_nothing_to_clear(folder):
    cli("data", "add", str(s5.write(folder, "one.csv", BANK)), "--sign", "negative")
    cli("data", "clear")
    assert lines(cli("data", "clear").stdout) == [s5.NO_DATA]


def test_the_event_log_keeps_the_record_after_a_clear(folder, conn):
    path = s5.write(folder, "one.csv", BANK)
    cli("data", "add", str(path), "--sign", "negative")
    cli("data", "clear")
    again = cli("data", "add", str(path), "--sign", "negative")
    assert again.returncode == 0
    assert len(s5.events(conn, "data.imported")) == 2


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
    """What the command said on standard error, without the line that tells the example was copied (SPEC 6.2)."""
    return "".join(line for line in result.stderr.splitlines(keepends=True) if not line.startswith("Copied the example"))


def example_events(workdir):
    return s3.stored_events(workdir / "my" / "var" / "examples" / "demo" / "harness.db")


def test_in_example_mode_with_no_file_every_data_file_is_loaded_in_name_order(tmp_path):
    work = example_with_data(tmp_path, {"b_other.csv": s5.simple(), "a_bank.csv": BANK})
    result = run_in_example(work, "data", "add", "--sign", "negative")
    assert result.returncode == 0, result.stderr
    printed = lines(result.stdout)
    assert printed[0].startswith("a_bank.csv: loaded") and printed[2].startswith("b_other.csv: loaded")
    assert printed[-1] == "2 of 2 files loaded."


def test_the_example_data_goes_into_the_database_of_the_example(tmp_path):
    work = example_with_data(tmp_path)
    run_in_example(work, "data", "add", "--sign", "negative")
    rows = s3.sql(work / "my" / "var" / "examples" / "demo" / "harness.db", "SELECT account FROM imports ORDER BY id")
    assert [r["account"] for r in rows] == ["a_bank", "b_other"]
    assert [e["payload"]["name"] for e in example_events(work) if e["kind"] == "data.imported"] == [
        "a_bank.csv", "b_other.csv"]


def test_files_that_start_with_a_dot_and_folders_are_not_loaded(tmp_path):
    work = example_with_data(tmp_path, {"a_bank.csv": BANK, ".hidden.csv": s5.simple(), "sub/c.csv": s5.simple()})
    result = run_in_example(work, "data", "add", "--sign", "negative")
    assert result.returncode == 0
    printed = lines(result.stdout)
    assert printed[0].startswith("a_bank.csv: loaded") and printed[-1] == "1 of 1 files loaded."


@pytest.mark.parametrize("files", [{}, {".gitkeep": ""}, {"sub/c.csv": "x"}])
def test_an_example_without_account_files_says_so(tmp_path, files):
    work = example_with_data(tmp_path, files)
    result = run_in_example(work, "data", "add", "--sign", "negative")
    assert result.returncode == 1 and result.stdout == ""
    assert stderr_of(result).strip() == s5.NO_EXAMPLE_DATA.format(name="demo", folder="examples/demo/data")


def test_an_example_with_no_data_folder_says_so(tmp_path):
    work = tmp_path / "work"
    s3.make_example(work / "examples", "demo")
    result = run_in_example(work, "data", "add", "--sign", "negative")
    assert result.returncode == 1 and stderr_of(result).strip() == s5.NO_EXAMPLE_DATA.format(
        name="demo", folder="examples/demo/data")


def test_in_example_mode_a_file_named_on_the_command_is_loaded_instead(tmp_path):
    work = example_with_data(tmp_path)
    other = s5.write(tmp_path / "elsewhere", "mine.csv", BANK)
    result = run_in_example(work, "data", "add", str(other), "--sign", "negative")
    assert result.returncode == 0 and lines(result.stdout)[0].startswith("mine.csv: loaded")
    assert lines(result.stdout)[-1] == "1 of 1 files loaded."


def test_account_with_the_example_data_of_more_than_one_file_is_an_error(tmp_path):
    work = example_with_data(tmp_path)
    result = run_in_example(work, "data", "add", "--sign", "negative", "--account", "mine")
    assert result.returncode == 1 and result.stdout == "" and stderr_of(result).strip() == s5.ONE_ACCOUNT
    if (work / "my" / "var" / "examples" / "demo" / "harness.db").exists():
        assert not any(e["kind"].startswith("data.") for e in example_events(work))


def test_account_with_the_example_data_of_one_file_names_it(tmp_path):
    work = example_with_data(tmp_path, {"a_bank.csv": BANK})
    result = run_in_example(work, "data", "add", "--sign", "negative", "--account", "mine")
    assert result.returncode == 0 and "into account 'mine'" in lines(result.stdout)[0]


def test_no_brief_is_needed(tmp_path):
    work = tmp_path / "work"
    s5.write(work / "examples" / "demo" / "data", "a_bank.csv", BANK)
    result = run_in_example(work, "data", "add", "--sign", "negative")
    assert result.returncode == 0 and lines(result.stdout)[-1] == "1 of 1 files loaded."


def test_list_and_clear_work_on_the_database_of_the_example(tmp_path):
    work = example_with_data(tmp_path)
    run_in_example(work, "data", "add", "--sign", "negative")
    listed = lines(run_in_example(work, "data", "list").stdout)
    assert listed[0].startswith("1  a_bank  a_bank.csv  2 transactions") and listed[1].startswith("2  b_other")
    cleared = run_in_example(work, "data", "clear")
    assert lines(cleared.stdout) == [s5.DATA_CLEARED.format(imports=2, transactions=4)]
    assert lines(run_in_example(work, "data", "list").stdout) == [s5.NO_DATA]
