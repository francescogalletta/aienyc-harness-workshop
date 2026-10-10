"""SPEC 9.2: the names of accounts, the constants of the adapter, and the first rule of `read_table`: the text."""
import pytest

import step5_helpers as s5
from step5_helpers import read_ok, refusal


# ---- the constants ----------------------------------------------------------------------------------------------

def test_the_constants_of_the_adapter(adapter):
    assert adapter.SIGNS == ("out_negative", "out_positive")
    assert adapter.DELIMITERS == (",", ";", "\t", "|")
    assert adapter.HEADER_SEARCH == 20
    assert adapter.COLUMN_NAMES == s5.COLUMN_NAMES
    assert adapter.DATE_FORMATS == s5.DATE_FORMATS


@pytest.mark.parametrize("name", ["BAD_ACCOUNT", "NOT_FOUND", "ALREADY_LOADED", "EMPTY", "NOT_TEXT", "NO_HEADER",
                                  "SHORT_ROW", "NO_ROWS", "BAD_DATES", "AMBIGUOUS_DATES", "BAD_NUMBERS",
                                  "AMBIGUOUS_NUMBERS", "NO_SIGN", "SIGN_ROWS", "SIGN_QUESTION"])
def test_the_messages_of_the_adapter(adapter, name):
    assert getattr(adapter, name) == getattr(s5, name)


def test_not_loaded_is_an_exception_whose_message_is_the_reason(adapter):
    assert issubclass(adapter.NotLoaded, Exception)
    assert str(adapter.NotLoaded("the file is empty")) == "the file is empty"


def test_the_sources_package_holds_only_a_docstring(sources):
    assert (sources.__doc__ or "").strip()
    public = [name for name in vars(sources) if not name.startswith("_")]
    assert all(name in {"adapter", "summaries"} for name in public), public       # only submodules once imported


# ---- account names ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path, expected", [
    ("Checking 2026.csv", "checking_2026"),
    ("checking_2026.csv", "checking_2026"),
    ("/some/folder/Main Account.CSV", "main_account"),
    ("statement.2026.csv", "statement_2026"),
    ("Caja--Ahorro (viejo).csv", "caja_ahorro_viejo"),
    ("  weird   name .txt", "weird_name"),
    ("Cuenta Ñandú.csv", "cuenta_and"),
    ("a.csv", "a"),
    ("A1_b2.csv", "a1_b2"),
    ("_main_.csv", "main"),
    ("all accounts.csv", "all_accounts"),
    ("No Extension", "no_extension"),
])
def test_account_name_from_a_file_name(adapter, path, expected):
    assert adapter.account_name(path) == expected


def test_account_name_takes_a_path_object_and_ignores_the_folders(adapter, tmp_path):
    assert adapter.account_name(tmp_path / "Folder One" / "Card 2026.csv") == "card_2026"


@pytest.mark.parametrize("path, name", [
    ("2026.csv", "2026"),
    ("9 lives.csv", "9_lives"),
    ("all.csv", "all"),
    ("ALL.csv", "all"),
    ("---.csv", ""),
    ("ñ.csv", ""),
])
def test_a_file_name_that_does_not_make_an_account_name(adapter, path, name):
    with pytest.raises(adapter.NotLoaded) as error:
        adapter.account_name(path)
    assert str(error.value) == s5.BAD_ACCOUNT.format(name=name)


# ---- text: EMPTY and NOT_TEXT -----------------------------------------------------------------------------------

@pytest.mark.parametrize("data", [b"", b"   ", b"\n\n", b" \t \r\n \n", "  \n".encode("utf-8"), b"\xef\xbb\xbf",
                                  b"\xef\xbb\xbf \n"])
def test_nothing_but_white_space_is_empty(adapter, data):
    assert refusal(adapter, data) == s5.EMPTY


@pytest.mark.parametrize("data", [
    b"Date,Description,Amount\n2026-03-25,a\x00b,1.00\n",
    b"\x00",
    "Date,Description,Amount\n2026-03-25,x,1.00\n\x00".encode("utf-8"),
    b"Date,Description,Amount\n2026-03-25,\x81,1.00\n",                  # not UTF-8, and 0x81 is not Windows-1252 either
    b"\xff\xfe\x00D\x00a\x00t\x00e\x00",
])
def test_bytes_that_are_not_text(adapter, data):
    assert refusal(adapter, data) == s5.NOT_TEXT


def test_a_byte_order_mark_is_dropped(adapter):
    reading = read_ok(adapter, b"\xef\xbb\xbfDate,Description,Amount\n2026-03-25,Coffee,-3.50\n")
    assert reading["columns"]["date"] == "Date"
    assert reading["rows"][0]["description"] == "Coffee"


def test_windows_1252_is_the_second_choice(adapter):
    reading = read_ok(adapter, b"Date,Description,Amount\n2026-03-25,Caf\xe9 \x80,-3.50\n")
    assert reading["rows"][0]["description"] == "Café €"


def test_utf_8_is_the_first_choice(adapter):
    reading = read_ok(adapter, "Date,Description,Amount\n2026-03-25,Café €,-3.50\n".encode("utf-8"))
    assert reading["rows"][0]["description"] == "Café €"


def test_the_sha256_is_that_of_the_bytes(adapter):
    import hashlib
    data = b"\xef\xbb\xbfDate,Description,Amount\r\n2026-03-25,Coffee,-3.50\r\n"
    assert read_ok(adapter, data)["sha256"] == hashlib.sha256(data).hexdigest()


def test_crlf_line_ends_read_like_any_other(adapter):
    reading = read_ok(adapter, s5.simple(newline="\r\n"))
    assert [r["description"] for r in reading["rows"]] == ["Coffee", "Pay"]


def test_the_reading_has_exactly_the_keys_of_the_spec(adapter):
    reading = read_ok(adapter, s5.simple())
    assert set(reading) == s5.READING_KEYS
    assert reading["dropped"] == [] and reading["same_kept"] == []
    assert reading["rows"] == [
        {"row": 2, "date": "2026-03-25", "amount": "-3.50", "description": "Coffee", "balance": None},
        {"row": 3, "date": "2026-03-26", "amount": "100.00", "description": "Pay", "balance": None}]
    assert reading["columns"] == {"date": "Date", "description": "Description", "amount": "Amount", "balance": None}
