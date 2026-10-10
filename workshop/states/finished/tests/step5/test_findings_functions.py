"""SPEC 9.5: `figure`, `disagree`, `plain`, `same_value`, `brief_texts` and the constants."""
from decimal import Decimal

import pytest

import step5_helpers as s5
from step5_helpers import h


def number(value, *, written=None, percent=False):
    return {"written": written or str(value), "date": False, "value": Decimal(str(value)), "percent": percent}


def date(text):
    return {"written": text, "date": True, "value": text, "percent": False}


# ---- the constants ------------------------------------------------------------------------------------------------------

def test_the_constants(findings):
    assert findings.FINDING_KINDS == ("earlier", "data", "brief")
    assert findings.TOLERANCE == Decimal("0.05")
    assert findings.MAX_FINDINGS == 2
    assert findings.JUDGMENT_WORDS == s5.JUDGMENT_WORDS


@pytest.mark.parametrize("name", ["FINDING_INTRO", "FINDING_SAID", "FINDING_DATA", "FINDING_BRIEF", "FINDING_NOW",
                                  "FINDING_EARLIER", "EARLIER_HERE", "EARLIER_BEFORE", "FINDING_KEEP",
                                  "FINDING_USE_DATA", "FINDING_USE_BRIEF", "FINDING_USE_NEW", "FINDING_KEEP_EARLIER"])
def test_the_text_of_the_block(findings, name):
    assert getattr(findings, name) == getattr(s5, name)


# ---- figure -------------------------------------------------------------------------------------------------------------

def test_the_figure_of_a_sentence(findings):
    found = findings.figure("I spend about 5k a month")
    assert found == {"written": "5k", "date": False, "value": Decimal("5000"), "percent": False}
    assert list(found) == ["written", "date", "value", "percent"]
    assert isinstance(found["value"], Decimal)


def test_two_figures_are_none(findings):
    assert findings.figure("between 150 and 200") is None
    assert findings.figure("I earn 3,000 and spend 2,500") is None


def test_no_figure_is_none(findings):
    assert findings.figure("I spend a lot") is None
    assert findings.figure("") is None


@pytest.mark.parametrize("text, written, value", [
    ("rent is 1,150 a month", "1,150", "1150"), ("it is 1150.50 now", "1150.50", "1150.50"),
    ("about 5K", "5K", "5000"), ("a 5 in 10 chance of 250", "250", "250"), ("nearly 13 of them", "13", "13"),
    ("a rate of 12.5 per day", "12.5", "12.5"), ("only 0.75 left", "0.75", "0.75"),
])
def test_numbers_are_read_with_their_value(findings, text, written, value):
    found = findings.figure(text)
    assert found["written"] == written and found["value"] == Decimal(value) and found["date"] is False
    assert found["percent"] is False


def test_a_k_multiplies_by_a_thousand(findings):
    assert findings.figure("4.6k")["value"] == Decimal("4600")


def test_a_percentage(findings):
    found = findings.figure("a raise of 12% next year")
    assert found["written"] == "12%" and found["percent"] is True and found["value"] == Decimal("12")
    assert findings.figure("0.5%")["value"] == Decimal("0.5")


def test_a_date(findings):
    found = findings.figure("payday is 2026-03-25")
    assert found == {"written": "2026-03-25", "date": True, "value": "2026-03-25", "percent": False}


def test_a_date_and_a_number_are_two_figures(findings):
    assert findings.figure("on 2026-03-14 I paid 500") is None


@pytest.mark.parametrize("text", ["3 payments", "the 12 months", "0 left", "6", "I have 1 account"])
def test_a_bare_whole_number_from_0_to_12_is_left_out(findings, text):
    assert findings.figure(text) is None


@pytest.mark.parametrize("text", ["$12", "12.0", "12k", "12%", "13"])
def test_what_is_not_a_bare_whole_number_up_to_12_is_kept(findings, text):
    assert findings.figure(text) is not None


def test_small_numbers_do_not_count_among_the_figures(findings):
    found = findings.figure("I pay 3 times a year, 1,200 each")
    assert found is not None and found["written"] == "1,200"


def test_a_number_glued_to_a_letter_is_not_read(findings):
    assert findings.figure("the 1st of the month, step s1") is None


def test_a_currency_sign_is_read_as_a_number(findings):
    found = findings.figure("it costs $1,234.50")
    assert found["value"] == Decimal("1234.50") and found["date"] is False


def test_signs_are_ignored(findings):
    assert findings.figure("I lost -5,000")["value"] == Decimal("5000")


# ---- disagree -----------------------------------------------------------------------------------------------------------

def test_about_5k_against_5080_does_not_disagree_and_against_4132_does(findings):
    claim = findings.figure("I spend about 5k a month")
    assert findings.disagree(claim, findings.figure("5080")) is False
    assert findings.disagree(claim, findings.figure("4132.31")) is True


@pytest.mark.parametrize("claim, reference, result", [
    ("105", "100", False), ("95", "100", False), ("105.01", "100", True), ("94.99", "100", True),
    ("100", "100", False), ("1,050", "1,000", False), ("1,051", "1,000", True), ("5k", "5000", False),
    ("1,400", "1,150", True), ("1,150", "1,400", True), ("1,200", "1,150", False),
])
def test_the_tolerance_is_five_percent_of_the_reference(findings, claim, reference, result):
    assert findings.disagree(findings.figure(claim), findings.figure(reference)) is result


def test_the_tolerance_is_taken_from_the_reference_not_the_claim(findings):
    """100 against 105.2 is within 5% of 105.2 (a difference of 5.2, at most 5.26); 105.3 against 100 is not (5.3 is
    more than 5% of 100)."""
    assert findings.disagree(findings.figure("100"), findings.figure("105.2")) is False
    assert findings.disagree(findings.figure("100"), findings.figure("105.3")) is True
    assert findings.disagree(findings.figure("105.3"), findings.figure("100")) is True
    assert findings.disagree(findings.figure("105.0"), findings.figure("100")) is False


def test_a_zero_reference_disagrees_with_any_difference(findings):
    zero = number(0)
    assert findings.disagree(number(Decimal("0.01")), zero) is True
    assert findings.disagree(number(100), zero) is True
    assert findings.disagree(number(0), zero) is False


def test_two_equal_dates_agree_and_two_other_dates_disagree(findings):
    assert findings.disagree(findings.figure("2026-03-25"), findings.figure("2026-03-25")) is False
    assert findings.disagree(findings.figure("2026-03-25"), findings.figure("2026-03-26")) is True
    assert findings.disagree(findings.figure("2026-03-25"), findings.figure("2026-04-25")) is True


def test_dates_have_no_tolerance(findings):
    assert findings.disagree(findings.figure("2026-03-25"), findings.figure("2026-03-24")) is True


def test_a_date_and_a_number_are_not_comparable(findings):
    assert findings.disagree(findings.figure("2026-03-25"), findings.figure("5000")) is None
    assert findings.disagree(findings.figure("5000"), findings.figure("2026-03-25")) is None


def test_with_one_percentage_its_value_is_divided_by_100(findings):
    assert findings.disagree(number(50, written="50%", percent=True), number("0.5")) is False
    assert findings.disagree(number("0.5"), number(50, written="50%", percent=True)) is False
    assert findings.disagree(number(10, written="10%", percent=True), number("0.2")) is True
    assert findings.disagree(number(10, written="10%", percent=True), number("0.1")) is False


def test_with_two_percentages_nothing_is_divided(findings):
    ten = number(10, written="10%", percent=True)
    assert findings.disagree(ten, number("10.2", written="10.2%", percent=True)) is False
    assert findings.disagree(ten, number(11, written="11%", percent=True)) is True


def test_disagree_reads_percentages_as_the_number_check_does(findings):
    assert findings.disagree(findings.figure("a raise of 12%"), findings.figure("0.12")) is False
    assert findings.disagree(findings.figure("a raise of 12%"), findings.figure("0.2")) is True


def test_signs_are_ignored_in_the_comparison(findings):
    assert findings.disagree(findings.figure("-5,000"), findings.figure("5,000")) is False


# ---- plain --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("I spend about 5k a month", "5000"), ("rent is 1,150", "1150"), ("2026-03-14 it was", "2026-03-14"),
    ("a raise of 12%", "12%"), ("it costs $1,234.50", "1234.50"), ("only 0.75", "0.75"), ("about 4132.31", "4132.31"),
])
def test_plain(findings, text, expected):
    assert findings.plain(findings.figure(text)) == expected


def test_plain_of_a_number_is_the_decimal_as_text(findings):
    assert findings.plain(number("1150.50")) == "1150.50"
    assert findings.plain(number(5000)) == "5000"
    assert findings.plain(number(7, written="7%", percent=True)) == "7%"


def test_plain_of_a_date_is_its_text(findings):
    assert findings.plain(date("2026-03-25")) == "2026-03-25"


# ---- same_value ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("a, b", [
    ("5000", "5000"), ("5000", "  5000  "), ("deposit  500", "deposit 500"), ("deposit\n500", "deposit 500"),
    ("10000", "10,000"), ("10,000", "10000"), ("500", "500.00"), ("5k", "5000"), ("5", "5.0"), ("12", "12.00"),
    ("50%", "50.0%"), ("hello", "hello"), ("  1,150 ", "1150"), ("2026-03-14", "2026-03-14"),
])
def test_values_that_are_the_same(findings, a, b):
    assert findings.same_value(a, b) is True


@pytest.mark.parametrize("a, b", [
    ("deposit 500", "deposit 500.00"), ("5000", "5001"), ("50%", "50"), ("50", "50%"), ("1,150", "1.150"),
    ("abc", "abd"), ("1 and 2", "1 and 2.0"), ("5k", "5100"), ("500", "five hundred"), ("2026-03-14", "2026-03-15"),
    ("12%", "0.12"),
])
def test_values_that_are_not_the_same(findings, a, b):
    assert findings.same_value(a, b) is False


def test_same_value_is_symmetric(findings):
    for a, b in (("10000", "10,000"), ("deposit 500", "deposit 500.00"), ("50%", "50")):
        assert findings.same_value(a, b) == findings.same_value(b, a)


# ---- brief_texts --------------------------------------------------------------------------------------------------------

def test_brief_texts_of_the_test_brief(findings):
    assert findings.brief_texts(h.make_brief()) == [
        h.PARTICULAR, "Count it as spending", "Monthly income", "What comes in each month", "Monthly spending",
        "What goes out each month", "Savings target", "How much the fund should hold"]


def test_brief_texts_take_the_particulars_before_the_inputs_in_order(findings):
    brief = h.make_brief(particulars=[{"what": "A", "handling": "B"}, {"what": "C", "handling": "D"}],
                         inputs=[{"name": "E", "description": "F"}, {"name": "G", "description": "H"}])
    assert findings.brief_texts(brief) == ["A", "B", "C", "D", "E", "F", "G", "H"]


def test_brief_texts_take_the_strings_only(findings):
    brief = h.make_brief(particulars=[{"what": 12, "handling": "keep it"}, {"what": "rent", "handling": None}],
                         inputs=[{"name": "x", "description": 5}])
    assert findings.brief_texts(brief) == ["keep it", "rent", "x"]


def test_brief_texts_of_an_empty_brief(findings):
    assert findings.brief_texts(h.make_brief(particulars=[], inputs=[])) == []


def test_brief_texts_leave_out_the_rest_of_the_brief(findings):
    brief = h.make_brief(particulars=[], inputs=[], goal="A goal with 7,000 in it")
    assert findings.brief_texts(brief) == []
