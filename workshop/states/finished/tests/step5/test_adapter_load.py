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





















# ---- load: the sign convention --------------------------------------------------------------------------------------



def test_out_positive_negates_every_amount(adapter, conn, folder):
    read_and_load(adapter, conn, folder, text=simple([("2026-03-25", "a", "3.50"), ("2026-03-26", "b", "-10.00")]),
                  sign="out_positive")
    assert [r["amount"] for r in s5.transactions(conn)] == ["-3.50", "10.00"]








# ---- load: refusals -------------------------------------------------------------------------------------------------











# ---- load: the event ------------------------------------------------------------------------------------------------



# ---- add_file: the checks in order ---------------------------------------------------------------------------------

def refused(conn):
    return s5.payloads(conn, "data.refused")










def test_a_file_name_that_does_not_make_an_account_name_is_refused(adapter, conn, folder):
    path = s5.write(folder, "2026.csv", BANK)
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, path)
    assert str(error.value) == s5.BAD_ACCOUNT.format(name="2026")
    assert refused(conn) == [{"file": str(path), "reason": s5.BAD_ACCOUNT.format(name="2026")}]










def test_a_file_already_loaded_is_refused_under_any_name(adapter, conn, folder):
    s5.add_text(adapter, conn, folder, "first.csv", BANK)
    copy = s5.write(folder / "other", "second.csv", BANK)
    with pytest.raises(adapter.NotLoaded) as error:
        s5.add(adapter, conn, copy)
    assert str(error.value) == s5.ALREADY_LOADED.format(account="first")
    assert refused(conn) == [{"file": str(copy), "reason": s5.ALREADY_LOADED.format(account="first")}]
    assert len(s5.sql_rows(conn, "SELECT * FROM imports")) == 1












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
















@pytest.mark.parametrize("answer", ["/quit"])
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




# ---- list_imports and clear_data ------------------------------------------------------------------------------------





def test_clear_data_removes_the_rows_and_says_how_many(adapter, conn, folder):
    s5.add_text(adapter, conn, folder, "one.csv", BANK)
    s5.add_text(adapter, conn, folder, "two.csv", SPANISH)
    assert adapter.clear_data(conn, session_id="C1") == {"imports": 2, "transactions": 4}
    assert s5.sql_rows(conn, "SELECT * FROM imports") == [] and s5.transactions(conn) == []
    assert adapter.list_imports(conn) == []










