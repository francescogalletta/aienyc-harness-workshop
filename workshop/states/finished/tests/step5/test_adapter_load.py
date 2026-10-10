"""SPEC 9.2: `load`, `add_file`, `list_imports`, `clear_data`, the sign convention and the events they record."""
import json
from datetime import datetime

import pytest

import step5_helpers as s5
from step5_helpers import h, simple

SPANISH = "Fecha;Concepto;Importe;Saldo\n25/03/2026;Shop;-1.234,56;5.000,00\n26/03/2026;Pay;2.000,00;7.000,00\n"
BANK = "Date,Description,Amount,Balance\n2026-03-25,Shop,-5.00,95.00\n2026-03-26,Pay,10.00,105.00\n"


def read_and_load(adapter, conn, files, name="bank.csv", text=SPANISH, *, account="main", sign="out_negative",
                  sign_from="flag", session_id="S1"):
    path = s5.write(files, name, text)
    reading = adapter.read_table(path.read_bytes())
    imported = adapter.load(conn, path=str(path), reading=reading, account=account, sign=sign, sign_from=sign_from,
                            session_id=session_id)
    return path, reading, imported


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "files"


# ---- load: what it writes -------------------------------------------------------------------------------------------

def test_load_returns_the_import_dict(adapter, conn, folder):
    path, reading, imported = read_and_load(adapter, conn, folder)
    assert set(imported) == s5.IMPORT_KEYS
    assert imported["id"] == 1 and imported["session_id"] == "S1"
    assert imported["file"] == str(path) and imported["name"] == "bank.csv"
    assert imported["sha256"] == reading["sha256"]
    assert (imported["account"], imported["sign"], imported["sign_from"]) == ("main", "out_negative", "flag")
    assert imported["delimiter"] == ";" and imported["header_row"] == 1
    assert imported["columns"] == {"date": "Fecha", "description": "Concepto", "amount": "Importe", "balance": "Saldo"}
    assert imported["date_format"] == "DD/MM/YYYY" and imported["number_format"] == "1.234,56"
    assert imported["newest_first"] is False
    assert imported["transactions"] == 2
    assert (imported["first"], imported["last"]) == ("2026-03-25", "2026-03-26")
    assert imported["dropped"] == [] and imported["same_kept"] == []


def test_the_time_is_utc_iso_8601(adapter, conn, folder):
    _, _, imported = read_and_load(adapter, conn, folder)
    moment = datetime.fromisoformat(imported["ts"])
    assert moment.utcoffset().total_seconds() == 0


def test_first_and_last_are_the_earliest_and_latest_dates_written(adapter, conn, folder):
    text = "Date,Description,Amount\n2026-03-27,a,1.00\n2026-03-20,b,1.00\n2026-03-25,c,1.00\n"
    _, _, imported = read_and_load(adapter, conn, folder, text=text)
    assert (imported["first"], imported["last"]) == ("2026-03-20", "2026-03-27")


def test_the_dropped_and_same_kept_lists_of_the_reading_are_in_the_import(adapter, conn, folder):
    text = ("Date,Description,Amount\n2026-03-25,a,1.00\n2026-03-25,a,1.00\nDate,Description,Amount\n"
            "2026-03-26,b,2.00\n")
    _, reading, imported = read_and_load(adapter, conn, folder, text=text)
    assert imported["dropped"] == reading["dropped"] == [{"row": 4, "reason": "repeated header"}]
    assert imported["same_kept"] == reading["same_kept"] == [3]
    assert imported["transactions"] == 3


def test_the_imports_row(adapter, conn, folder):
    path, reading, imported = read_and_load(adapter, conn, folder)
    [row] = s5.sql_rows(conn, "SELECT * FROM imports")
    assert row["id"] == 1 and row["session_id"] == "S1" and row["file"] == str(path)
    assert row["sha256"] == reading["sha256"] and row["account"] == "main" and row["sign"] == "out_negative"
    assert json.loads(row["report"]) == imported
    assert row["ts"] == imported["ts"]


def test_the_transactions_rows(adapter, conn, folder):
    read_and_load(adapter, conn, folder)
    rows = s5.transactions(conn)
    assert [(r["import_id"], r["account"], r["date"], r["amount"], r["description"], r["balance"], r["row"])
            for r in rows] == [
        (1, "main", "2026-03-25", "-1234.56", "Shop", "5000.00", 2),
        (1, "main", "2026-03-26", "2000.00", "Pay", "7000.00", 3)]
    assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)


def test_a_transaction_without_a_balance_has_a_null_balance(adapter, conn, folder):
    read_and_load(adapter, conn, folder, text=simple())
    assert [r["balance"] for r in s5.transactions(conn)] == [None, None]


def test_an_empty_balance_cell_is_a_null_balance(adapter, conn, folder):
    text = "Date,Description,Amount,Balance\n2026-03-25,a,1.00,\n2026-03-26,b,2.00,5.00\n"
    read_and_load(adapter, conn, folder, text=text)
    assert [r["balance"] for r in s5.transactions(conn)] == [None, "5.00"]


def test_rows_are_stored_in_file_order_with_their_row_numbers(adapter, conn, folder):
    text = "Statement\nDate,Description,Amount\n2026-03-27,c,3.00\n2026-03-25,a,1.00\n"
    read_and_load(adapter, conn, folder, text=text)
    assert [(r["row"], r["description"]) for r in s5.transactions(conn)] == [(3, "c"), (4, "a")]


def test_a_second_import_continues_the_ids(adapter, conn, folder):
    read_and_load(adapter, conn, folder, "one.csv", BANK, account="one")
    read_and_load(adapter, conn, folder, "two.csv", simple(), account="two")
    assert [r["id"] for r in s5.sql_rows(conn, "SELECT id FROM imports")] == [1, 2]
    assert [(r["import_id"], r["account"]) for r in s5.transactions(conn)] == [(1, "one")] * 2 + [(2, "two")] * 2
    assert [r["id"] for r in s5.transactions(conn)] == [1, 2, 3, 4]


# ---- load: the sign convention --------------------------------------------------------------------------------------

def test_out_negative_keeps_the_amounts_as_read(adapter, conn, folder):
    read_and_load(adapter, conn, folder, text=simple([("2026-03-25", "a", "-3.50"), ("2026-03-26", "b", "10.00")]),
                  sign="out_negative")
    assert [r["amount"] for r in s5.transactions(conn)] == ["-3.50", "10.00"]


def test_out_positive_negates_every_amount(adapter, conn, folder):
    read_and_load(adapter, conn, folder, text=simple([("2026-03-25", "a", "3.50"), ("2026-03-26", "b", "-10.00")]),
                  sign="out_positive")
    assert [r["amount"] for r in s5.transactions(conn)] == ["-3.50", "10.00"]


def test_balances_are_stored_as_read_with_either_convention(adapter, conn, folder):
    read_and_load(adapter, conn, folder, text=BANK, sign="out_positive")
    assert [r["balance"] for r in s5.transactions(conn)] == ["95.00", "105.00"]
    assert [r["amount"] for r in s5.transactions(conn)] == ["5.00", "-10.00"]


@pytest.mark.parametrize("sign, written, stored", [
    ("out_negative", "0.00", "0.00"), ("out_negative", "-0.00", "0.00"), ("out_positive", "0.00", "0.00"),
    ("out_positive", "-0.00", "0.00"), ("out_positive", "0", "0"), ("out_negative", "-0", "0"),
    ("out_positive", "+0.0000", "0.0000"),
])
def test_a_zero_amount_is_stored_with_its_decimals_and_no_minus(adapter, conn, folder, sign, written, stored):
    read_and_load(adapter, conn, folder, text=simple([("2026-03-25", "a", written), ("2026-03-26", "b", "1.00")]),
                  sign=sign)
    assert s5.transactions(conn)[0]["amount"] == stored


def test_the_decimals_of_an_amount_are_kept_when_negated(adapter, conn, folder):
    read_and_load(adapter, conn, folder, text=simple([("2026-03-25", "a", "3.50"), ("2026-03-26", "b", "7")]),
                  sign="out_positive")
    assert [r["amount"] for r in s5.transactions(conn)] == ["-3.50", "-7"]


# ---- load: refusals -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("sign", ["negative", "out", "", None, "OUT_NEGATIVE"])
def test_a_sign_that_is_not_one_of_signs_is_a_value_error(adapter, conn, folder, sign):
    with pytest.raises(ValueError):
        read_and_load(adapter, conn, folder, sign=sign)
    assert s5.sql_rows(conn, "SELECT * FROM imports") == [] and s5.transactions(conn) == []


@pytest.mark.parametrize("sign_from", ["person", "", None, "Flag", "default"])
def test_a_sign_from_that_is_not_flag_asked_or_scenario_is_a_value_error(adapter, conn, folder, sign_from):
    with pytest.raises(ValueError):
        read_and_load(adapter, conn, folder, sign_from=sign_from)
    assert s5.sql_rows(conn, "SELECT * FROM imports") == []


@pytest.mark.parametrize("sign_from", ["flag", "asked", "scenario"])
def test_each_sign_from_is_recorded(adapter, conn, folder, sign_from):
    assert read_and_load(adapter, conn, folder, sign_from=sign_from)[2]["sign_from"] == sign_from


def test_the_same_bytes_are_loaded_once(adapter, conn, folder):
    path, reading, _ = read_and_load(adapter, conn, folder, account="first_one")
    with pytest.raises(adapter.NotLoaded) as error:
        adapter.load(conn, path="elsewhere.csv", reading=reading, account="second", sign="out_negative",
                     sign_from="flag", session_id="S2")
    assert str(error.value) == s5.ALREADY_LOADED.format(account="first_one")
    assert len(s5.sql_rows(conn, "SELECT * FROM imports")) == 1 and len(s5.transactions(conn)) == 2


def test_a_refused_load_records_no_import_event(adapter, conn, folder):
    path, reading, _ = read_and_load(adapter, conn, folder)
    with pytest.raises(adapter.NotLoaded):
        adapter.load(conn, path=str(path), reading=reading, account="again", sign="out_negative",
                     sign_from="flag", session_id="S2")
    assert len(s5.events(conn, "data.imported")) == 1


# ---- load: the event ------------------------------------------------------------------------------------------------

def test_data_imported_is_recorded_with_the_import_dict(adapter, conn, folder):
    _, _, imported = read_and_load(adapter, conn, folder)
    [(kind, actor, payload)] = s5.events(conn, "data.imported")
    assert (kind, actor) == ("data.imported", "harness")
    assert payload == imported
    [row] = s5.sql_rows(conn, "SELECT session_id FROM events WHERE kind = 'data.imported'")
    assert row["session_id"] == "S1"


# ---- add_file: the checks in order ---------------------------------------------------------------------------------

def refused(conn):
    return s5.payloads(conn, "data.refused")


def test_a_path_that_is_not_a_file_is_not_found(adapter, conn, folder):
    given = str(folder / "missing.csv")
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, given)
    assert str(error.value) == s5.NOT_FOUND.format(path=given)
    assert refused(conn) == [{"file": given, "reason": s5.NOT_FOUND.format(path=given)}]
    assert s5.actors(conn, "data.refused") == ["harness"]


def test_a_folder_is_not_a_file(adapter, conn, folder):
    folder.mkdir(parents=True)
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, folder)
    assert str(error.value) == s5.NOT_FOUND.format(path=str(folder))


def test_the_path_is_shown_as_given(adapter, conn):
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, "no/such/2026.csv")
    assert str(error.value) == s5.NOT_FOUND.format(path="no/such/2026.csv")
    assert refused(conn)[0]["file"] == "no/such/2026.csv"


def test_the_account_is_named_from_the_file_name(adapter, conn, folder):
    imported = s5.add_text(adapter, conn, folder, "Main Account 2026.csv", BANK)
    assert imported["account"] == "main_account_2026" and imported["name"] == "Main Account 2026.csv"


def test_a_file_name_that_does_not_make_an_account_name_is_refused(adapter, conn, folder):
    path = s5.write(folder, "2026.csv", BANK)
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, path)
    assert str(error.value) == s5.BAD_ACCOUNT.format(name="2026")
    assert refused(conn) == [{"file": str(path), "reason": s5.BAD_ACCOUNT.format(name="2026")}]


def test_an_account_given_is_used_as_given(adapter, conn, folder):
    imported = s5.add_text(adapter, conn, folder, "2026.csv", BANK, account="my_bank_9")
    assert imported["account"] == "my_bank_9"
    assert {r["account"] for r in s5.transactions(conn)} == {"my_bank_9"}


@pytest.mark.parametrize("account", ["Main", "all", "9lives", "my bank", "_x", "a-b", "ñ"])
def test_an_account_given_is_checked_by_the_same_rule(adapter, conn, folder, account):
    path = s5.write(folder, "statement.csv", BANK)
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, path, account=account)
    assert str(error.value) == s5.BAD_ACCOUNT.format(name=account)
    assert s5.sql_rows(conn, "SELECT * FROM imports") == []


def test_not_found_comes_before_the_account_check(adapter, conn, folder):
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, folder / "2026.csv")
    assert "there is no file" in str(error.value)


def test_the_account_check_comes_before_the_file_is_read(adapter, conn, folder):
    path = s5.write(folder, "2026.csv", "")
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, path)
    assert str(error.value) == s5.BAD_ACCOUNT.format(name="2026")


def test_a_file_already_loaded_is_refused_under_any_name(adapter, conn, folder):
    s5.add_text(adapter, conn, folder, "first.csv", BANK)
    copy = s5.write(folder / "other", "second.csv", BANK)
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, copy)
    assert str(error.value) == s5.ALREADY_LOADED.format(account="first")
    assert refused(conn) == [{"file": str(copy), "reason": s5.ALREADY_LOADED.format(account="first")}]
    assert len(s5.sql_rows(conn, "SELECT * FROM imports")) == 1


def test_a_file_already_loaded_is_refused_before_it_is_read_or_asked_about(adapter, conn, folder):
    s5.add_text(adapter, conn, folder, "first.csv", BANK)
    person = h.Person()
    with pytest.raises(adapter.NotLoaded):
        s5.add(adapter, conn, folder / "first.csv", sign=None, ask=person.ask, say=person.say)
    assert person.log == []


@pytest.mark.parametrize("content, reason", [
    (b"", s5.EMPTY), (b"\x00\x01", s5.NOT_TEXT), ("nothing useful here\n", s5.NO_HEADER),
    ("Date,Description,Amount\n", s5.NO_ROWS), ("Date,Description,Amount\n2026-03-25,a\n", s5.SHORT_ROW.format(row=2)),
])
def test_the_reason_of_read_table_is_the_reason_of_add_file(adapter, conn, folder, content, reason):
    path = s5.write(folder, "statement.csv", content)
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, path)
    assert str(error.value) == reason
    assert refused(conn) == [{"file": str(path), "reason": reason}]
    assert s5.sql_rows(conn, "SELECT * FROM imports") == []


def test_a_refusal_is_recorded_with_the_session_of_the_call(adapter, conn, folder):
    with pytest.raises(adapter.NotLoaded):
        s5.add(adapter, conn, folder / "missing.csv", session_id="the-command")
    [row] = s5.sql_rows(conn, "SELECT session_id FROM events WHERE kind = 'data.refused'")
    assert row["session_id"] == "the-command"


def test_add_file_loads_the_file_and_returns_the_import_dict(adapter, conn, folder):
    imported = s5.add_text(adapter, conn, folder, "bank.csv", SPANISH, sign="out_positive", sign_from="scenario",
                           session_id="S9")
    assert set(imported) == s5.IMPORT_KEYS
    assert (imported["sign"], imported["sign_from"], imported["session_id"]) == ("out_positive", "scenario", "S9")
    assert imported["file"] == str(folder / "bank.csv")
    assert [r["amount"] for r in s5.transactions(conn)] == ["1234.56", "-2000.00"]


def test_add_file_accepts_a_path_object_and_records_the_file_as_given(adapter, conn, folder):
    path = s5.write(folder, "bank.csv", BANK)
    imported = s5.add(adapter, conn, path)
    assert imported["file"] == str(path)


# ---- add_file: asking for the sign -----------------------------------------------------------------------------------

def ask_for_sign(adapter, conn, folder, answers, text=BANK, name="bank.csv", **options):
    person = h.Person(*answers)
    path = s5.write(folder, name, text)
    imported = s5.add(adapter, conn, path, sign=None, sign_from="flag", ask=person.ask, say=person.say, **options)
    return imported, person


def test_the_person_sees_the_first_rows_as_read_and_is_asked(adapter, conn, folder):
    text = simple([("2026-03-25", "Coffee", "-3.50"), ("2026-03-26", "Pay", "100.00")])
    imported, person = ask_for_sign(adapter, conn, folder, ["negative"], text, "bank.csv")
    assert person.log == [("say", s5.SIGN_ROWS.format(name="bank.csv")), ("say", "  2026-03-25  -3.50  Coffee"),
                          ("say", "  2026-03-26  100.00  Pay"), ("ask", s5.SIGN_QUESTION)]
    assert imported["sign"] == "out_negative" and imported["sign_from"] == "asked"


def test_only_the_first_three_rows_are_shown(adapter, conn, folder):
    text = simple([(f"2026-03-{day:02d}", f"row {day}", f"-{day}.00") for day in range(20, 26)])
    _, person = ask_for_sign(adapter, conn, folder, ["neg"], text)
    assert person.told == [s5.SIGN_ROWS.format(name="bank.csv"), "  2026-03-20  -20.00  row 20",
                           "  2026-03-21  -21.00  row 21", "  2026-03-22  -22.00  row 22"]


def test_the_rows_shown_are_the_kept_rows(adapter, conn, folder):
    rows = [("2026-03-25", "A", "-1.00", "10.00"), ("2026-03-25", "A", "-1.00", "10.00"),
            ("2026-03-24", "B", "-2.00", "8.00"), ("2026-03-23", "C", "-3.00", "5.00"),
            ("2026-03-22", "D", "-4.00", "1.00")]
    text = s5.csv_text(rows, header=("Date", "Description", "Amount", "Balance"))
    _, person = ask_for_sign(adapter, conn, folder, ["neg"], text)
    assert person.told[1:] == ["  2026-03-25  -1.00  A", "  2026-03-24  -2.00  B", "  2026-03-23  -3.00  C"]


def test_the_amount_is_shown_as_written(adapter, conn, folder):
    _, person = ask_for_sign(adapter, conn, folder, ["neg"], SPANISH)
    assert person.told[0] == s5.SIGN_ROWS.format(name="bank.csv")
    assert person.told[1].endswith("  -1.234,56  Shop") and person.told[2].endswith("  2.000,00  Pay")


def test_fewer_than_three_rows_are_all_shown(adapter, conn, folder):
    _, person = ask_for_sign(adapter, conn, folder, ["neg"], simple([("2026-03-25", "Only", "-1.00")]))
    assert person.told == [s5.SIGN_ROWS.format(name="bank.csv"), "  2026-03-25  -1.00  Only"]


def test_the_description_is_shown_on_one_line(adapter, conn, folder):
    text = 'Date,Description,Amount\n2026-03-25,"Shop \n   two",-1.00\n'
    _, person = ask_for_sign(adapter, conn, folder, ["neg"], text)
    assert person.told[1] == "  2026-03-25  -1.00  Shop two"


@pytest.mark.parametrize("answer, sign", [
    ("negative", "out_negative"), ("neg", "out_negative"), ("-", "out_negative"), ("positive", "out_positive"),
    ("pos", "out_positive"), ("+", "out_positive"), ("  NEGATIVE ", "out_negative"), ("Pos", "out_positive"),
    ("\tNeg\n", "out_negative"),
])
def test_the_answers_that_give_a_sign(adapter, conn, folder, answer, sign):
    imported, person = ask_for_sign(adapter, conn, folder, [answer])
    assert imported["sign"] == sign and imported["sign_from"] == "asked"
    assert [r["sign"] for r in s5.sql_rows(conn, "SELECT sign FROM imports")] == [sign]
    assert person.asked == [s5.SIGN_QUESTION]


def test_any_other_answer_asks_again_with_the_same_text(adapter, conn, folder):
    imported, person = ask_for_sign(adapter, conn, folder, ["maybe", "", "   ", "negatives", "out", "positive"])
    assert imported["sign"] == "out_positive"
    assert person.asked == [s5.SIGN_QUESTION] * 6
    assert person.told.count(s5.SIGN_ROWS.format(name="bank.csv")) == 1


@pytest.mark.parametrize("answer", ["/quit", "/QUIT", "  /Quit  "])
def test_quit_gives_no_sign_and_nothing_is_loaded(adapter, conn, folder, answer):
    path = s5.write(folder, "bank.csv", BANK)
    person = h.Person(answer)
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, path, sign=None, ask=person.ask, say=person.say)
    assert str(error.value) == s5.NO_SIGN
    assert refused(conn) == [{"file": str(path), "reason": s5.NO_SIGN}]
    assert s5.sql_rows(conn, "SELECT * FROM imports") == [] and s5.events(conn, "data.imported") == []


def test_a_sign_given_is_never_asked_about(adapter, conn, folder):
    person = h.Person()
    path = s5.write(folder, "bank.csv", BANK)
    imported = s5.add(adapter, conn, path, sign="out_positive", sign_from="flag", ask=person.ask, say=person.say)
    assert person.log == [] and imported["sign_from"] == "flag"


def test_a_file_that_cannot_be_read_is_not_asked_about(adapter, conn, folder):
    path = s5.write(folder, "bank.csv", "nothing useful\n")
    person = h.Person()
    with pytest.raises(adapter.NotLoaded):
        s5.add(adapter, conn, path, sign=None, ask=person.ask, say=person.say)
    assert person.log == []


# ---- list_imports and clear_data ------------------------------------------------------------------------------------

def test_list_imports_gives_the_import_dicts_by_id(adapter, conn, folder):
    first = s5.add_text(adapter, conn, folder, "one.csv", BANK)
    second = s5.add_text(adapter, conn, folder, "two.csv", SPANISH, sign="out_positive")
    assert adapter.list_imports(conn) == [first, second]
    assert [d["id"] for d in adapter.list_imports(conn)] == [1, 2]


def test_list_imports_is_empty_with_nothing_loaded(adapter, conn):
    assert adapter.list_imports(conn) == []


def test_clear_data_removes_the_rows_and_says_how_many(adapter, conn, folder):
    s5.add_text(adapter, conn, folder, "one.csv", BANK)
    s5.add_text(adapter, conn, folder, "two.csv", SPANISH)
    assert adapter.clear_data(conn, session_id="C1") == {"imports": 2, "transactions": 4}
    assert s5.sql_rows(conn, "SELECT * FROM imports") == [] and s5.transactions(conn) == []
    assert adapter.list_imports(conn) == []


def test_clear_data_records_data_cleared_for_the_person(adapter, conn, folder):
    s5.add_text(adapter, conn, folder, "one.csv", BANK)
    adapter.clear_data(conn, session_id="C1")
    assert s5.events(conn, "data.cleared") == [("data.cleared", "person", {"imports": 1, "transactions": 2})]
    [row] = s5.sql_rows(conn, "SELECT session_id FROM events WHERE kind = 'data.cleared'")
    assert row["session_id"] == "C1"


def test_clear_data_leaves_the_import_events_alone(adapter, conn, folder):
    s5.add_text(adapter, conn, folder, "one.csv", BANK)
    adapter.clear_data(conn, session_id="C1")
    assert len(s5.events(conn, "data.imported")) == 1


def test_clear_data_keeps_summaries_and_findings(adapter, conn, folder):
    s5.add_text(adapter, conn, folder, "one.csv", BANK)
    conn.execute("INSERT INTO data_summaries (ts, session_id, inputs, output, imports) VALUES (?, ?, ?, ?, ?)",
                 ("2026-03-14T10:00:00+00:00", "S", "{}", "{}", "[1]"))
    conn.execute("INSERT INTO findings (ts, session_id, kind, claim, claim_figure, reference, reference_figure, "
                 "difference, block, options, status) VALUES (?, ?, 'brief', 'c', '1', 'r', '2', '', 'b', '[]', 'open')",
                 ("2026-03-14T10:00:00+00:00", "S"))
    conn.commit()
    adapter.clear_data(conn, session_id="C1")
    assert len(s5.sql_rows(conn, "SELECT * FROM data_summaries")) == 1
    assert len(s5.sql_rows(conn, "SELECT * FROM findings")) == 1


def test_clear_data_with_nothing_loaded_removes_nothing(adapter, conn):
    assert adapter.clear_data(conn, session_id="C1") == {"imports": 0, "transactions": 0}


def test_after_clear_the_same_file_can_be_loaded_again_with_a_new_id(adapter, conn, folder):
    path = s5.write(folder, "bank.csv", BANK)
    first = s5.add(adapter, conn, path)
    adapter.clear_data(conn, session_id="C1")
    second = s5.add(adapter, conn, path)
    assert second["id"] > first["id"]
    assert len(s5.events(conn, "data.imported")) == 2
