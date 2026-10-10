"""SPEC 9.6: handling a report: the finding it opens, and the eleven rules that drop an entry, in their order."""
import pytest

import step5_helpers as s5
from step5_helpers import (CLAIM, DIFFERENCE, MESSAGE, RENT_CLAIM, RENT_DIFFERENCE, RENT_MESSAGE, RENT_QUOTE, SESSION,
                           SPENDING, SPENDING_WORDS, brief_entry, entry, h, put_months, report, s4, summary_call)

DROP = s4.DROP


def go(check_verifier, entries, *, calls=(summary_call(),), message=MESSAGE, **options):
    return check_verifier([*calls, report(*entries)], message, **options)


def go_brief(check_verifier, entries, **options):
    options.setdefault("message", RENT_MESSAGE)
    return go(check_verifier, entries, calls=(), **options)


def dropped(conn):
    return [(p["index"], p["reason"]) for p in s5.payloads(conn, "verify.dropped")]


def opened(conn):
    return s5.payloads(conn, "finding.opened")


@pytest.fixture
def flat(conn):
    """Three full months of 5080.00 going out: the average is 5080.00."""
    put_months(conn, "flat", {"2026-06": ([], ["5080"]), "2026-07": ([], ["5080"]), "2026-08": ([], ["5080"])})


# ---- a finding that passes every rule ------------------------------------------------------------------------------------------

def test_a_data_finding_is_opened(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry()])
    [finding] = found
    assert finding["kind"] == "data" and finding["status"] == "open" and finding["session_id"] == SESSION
    assert finding["claim"] == CLAIM and finding["claim_figure"] == "5k"
    assert finding["reference"] == SPENDING_WORDS and finding["reference_figure"] == SPENDING
    assert finding["summary"] == 1 and finding["input"] is None and finding["earlier"] is None
    assert finding["pending_note"] is None and finding["difference"] == DIFFERENCE
    assert finding["block"] == s5.DATA_BLOCK and finding["options"] == s5.OPTIONS_DATA


def test_a_brief_finding_is_opened(check_verifier, conn):
    found, _, _ = go_brief(check_verifier, [brief_entry()])
    [finding] = found
    assert finding["kind"] == "brief" and finding["claim"] == RENT_CLAIM and finding["claim_figure"] == "1,400"
    assert finding["reference"] == RENT_QUOTE and finding["reference_figure"] == "1,150"
    assert finding["summary"] is None and finding["difference"] == RENT_DIFFERENCE
    assert finding["block"] == s5.BRIEF_BLOCK and finding["options"] == s5.OPTIONS_BRIEF






















# ---- rule 1: the shape --------------------------------------------------------------------------------------------------------------

SHAPE = [
    entry(claim=DROP), entry(claim=""), entry(claim="   "), entry(claim=5), entry(claim=None), entry(claim=["a"]),
    entry(difference=DROP), entry(difference=""), entry(difference=" \n "), entry(difference=5), entry(difference=None),
    entry(kind=DROP), entry(kind="other"), entry(kind="DATA"), entry(kind="earlier"), entry(kind=None), entry(kind=1),
    entry(summary=DROP), entry(summary=True), entry(summary=False), entry(summary="1"), entry(summary=1.0),
    entry(summary=None), entry(summary=[1]),
    entry(kind="brief", quote=DROP), entry(kind="brief", quote=""), entry(kind="brief", quote="  "),
    entry(kind="brief", quote=5), {**entry(kind="brief"), "quote": None},
    "a string", 5, None, ["claim"], True,
]








# ---- rule 2: quoted from the message -------------------------------------------------------------------------------------------------









# ---- rule 3: one figure in the claim ---------------------------------------------------------------------------------------------------





# ---- rule 4: the quote is in the brief, the summary is of this session ---------------------------------------------------------------------

@pytest.mark.parametrize("quote", ["Rent is fixed at 1,500 a month"])
def test_a_quote_that_is_not_in_the_brief_is_dropped(check_verifier, conn, quote):
    found, _, _ = go_brief(check_verifier, [brief_entry(quote=quote)])
    assert found == [] and dropped(conn) == [(1, s5.DROP_NOT_IN_BRIEF)]








def test_a_summary_of_another_conversation_is_dropped(check_verifier, summaries, conn, example_loaded):
    summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 3}, session_id="another")
    found, _, _ = go(check_verifier, [entry(summary=1)], calls=())
    assert found == [] and dropped(conn) == [(1, s5.DROP_NO_SUMMARY.format(summary=1))]




# ---- rule 5: one figure in the quote ----------------------------------------------------------------------------------------------------







# ---- rule 6: comparable --------------------------------------------------------------------------------------------------------------------







# ---- rule 7: they differ ------------------------------------------------------------------------------------------------------------------------





@pytest.mark.parametrize("amount, opens", [("1,207.50", False), ("1,092.50", False)])
def test_the_edge_of_the_tolerance(check_verifier, conn, amount, opens):
    claim = f"My rent is {amount} a month"
    found, _, _ = go_brief(check_verifier, [brief_entry(claim)], message=claim)
    assert (len(found) == 1) is opens
    if not opens:
        assert dropped(conn) == [(1, s5.DROP_WITHIN_TOLERANCE)]






# ---- rule 8: numbers in the difference -----------------------------------------------------------------------------------------------------------

def test_a_number_from_nowhere_in_the_difference_is_dropped(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(difference="The loaded files show 6,000 going out a month.")])
    assert found == [] and dropped(conn) == [(1, s5.DROP_DIFFERENCE_NUMBERS.format(numbers="6,000"))]
















# ---- rule 9: no judgment words ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("word", list(s5.JUDGMENT_WORDS)[:1])
def test_each_judgment_word_drops_the_entry(check_verifier, conn, example_loaded, word):
    text = f"The loaded files show 4,132.31 a month, and that is {word} the figure."
    found, _, _ = go(check_verifier, [entry(difference=text)])
    assert found == [] and dropped(conn) == [(1, s5.DROP_TONE.format(word=word))]










# ---- rule 10: raised once ----------------------------------------------------------------------------------------------------------------------------

def test_the_same_difference_in_the_same_conversation_is_dropped(check_verifier, conn, example_loaded):
    first, _, _ = go(check_verifier, [entry()])
    second, _, _ = go(check_verifier, [entry()], calls=(), message=MESSAGE)
    assert len(first) == 1 and second == []
    assert dropped(conn) == [(1, s5.DROP_ALREADY.format(id=first[0]["id"]))]


















# ---- rule 11: two findings a message ---------------------------------------------------------------------------------------------------------------------

WIDE_BRIEF = h.make_brief(particulars=[
    {"what": "Rent is 1,150 a month", "handling": "Count it"}, {"what": "The gym is 40 a month", "handling": "Count it"},
    {"what": "The phone is 20 a month", "handling": "Count it"}, {"what": "The car is 300 a month", "handling": "Count it"}])
WIDE_MESSAGE = "My rent is 1,400 a month, my gym is 90 a month, my phone is 60 a month and my car is 700 a month."


def wide(what, claim, quote, text):
    return brief_entry(claim, quote, f"The brief gives the {what} as {text}.")


RENT = wide("rent", "My rent is 1,400 a month", "Rent is 1,150 a month", "1,150 a month")
GYM = wide("gym", "my gym is 90 a month", "The gym is 40 a month", "40 a month")
PHONE = wide("phone", "my phone is 60 a month", "The phone is 20 a month", "20 a month")
CAR = wide("car", "my car is 700 a month", "The car is 300 a month", "300 a month")


def wide_check(check_verifier, entries, **options):
    return check_verifier([report(*entries)], WIDE_MESSAGE, brief=WIDE_BRIEF, **options)


def test_only_two_findings_are_opened_for_one_message(check_verifier, conn):
    found, _, _ = wide_check(check_verifier, [RENT, GYM, PHONE, CAR])
    assert [f["claim"] for f in found] == ["My rent is 1,400 a month", "my gym is 90 a month"]
    assert dropped(conn) == [(3, s5.DROP_LIMIT), (4, s5.DROP_LIMIT)]








