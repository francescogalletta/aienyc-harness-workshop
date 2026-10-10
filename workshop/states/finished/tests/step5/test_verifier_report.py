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


def test_verify_returns_the_findings_it_opened_and_they_are_in_the_table(check_verifier, findings, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry()])
    assert found == findings.list_findings(conn, session_id=SESSION) == findings.open_findings(conn, session_id=SESSION)
    assert opened(conn) == found


def test_the_events_of_a_check_in_order(check_verifier, conn, example_loaded):
    go(check_verifier, [entry()])
    assert [k for k in h.kinds(conn) if k != "data.imported"] == ["data.summary", "verify.report", "finding.opened"]
    assert s5.actors(conn, "verify.report") == ["agent"] and s5.actors(conn, "finding.opened") == ["harness"]


def test_verify_report_holds_the_findings_as_sent(check_verifier, conn, example_loaded):
    sent = [entry(), "not even an object", entry(claim="nothing like the message")]
    go(check_verifier, sent)
    assert s5.payloads(conn, "verify.report") == [{"findings": sent}]


def test_an_empty_report_records_the_report_and_opens_nothing(check_verifier, conn):
    found, _, _ = go(check_verifier, [], calls=())
    assert found == [] and s5.payloads(conn, "verify.report") == [{"findings": []}]
    assert s5.events(conn, "verify.dropped") == [] and s5.events(conn, "finding.opened") == []


def test_the_claim_and_the_difference_are_made_one_line(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(claim="I spend  about\n5k a   month", difference=" The loaded files show\n"
                                                                                           "4,132.31 a  month. ")])
    assert found[0]["claim"] == "I spend about 5k a month" and found[0]["difference"] == "The loaded files show 4,132.31 a month."


def test_the_quote_is_a_part_of_one_text_of_the_brief(check_verifier, conn):
    found, _, _ = go_brief(check_verifier, [brief_entry(quote="fixed at 1,150")])
    assert len(found) == 1 and found[0]["reference_figure"] == "1,150" and found[0]["reference"] == "fixed at 1,150"


def test_a_quote_from_an_input_of_the_brief(check_verifier, conn):
    brief = h.make_brief(inputs=[{"name": "Savings target", "description": "The fund should hold 20,000"}])
    found, _, _ = check_verifier([report(brief_entry("My target is 30,000", "The fund should hold 20,000",
                                                     "The brief gives the target as 20,000."))],
                                 "My target is 30,000", brief=brief)
    assert len(found) == 1 and found[0]["reference_figure"] == "20,000" and found[0]["claim_figure"] == "30,000"


def test_a_date_finding(check_verifier, conn):
    brief = h.make_brief(particulars=[{"what": "The wedding is on 2027-06-12", "handling": "Plan for it"}])
    found, _, _ = check_verifier([report(brief_entry(
        "The wedding is on 2027-06-13", "The wedding is on 2027-06-12", "The brief gives the wedding as 2027-06-12."))],
        "The wedding is on 2027-06-13", brief=brief)
    assert found[0]["claim_figure"] == "2027-06-13" and found[0]["reference_figure"] == "2027-06-12"


def test_a_data_summary_of_an_earlier_check_of_the_session_can_be_cited(check_verifier, summaries, conn, example_loaded):
    summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 3}, session_id=SESSION)
    found, _, _ = go(check_verifier, [entry(summary=1)], calls=())
    assert len(found) == 1 and found[0]["summary"] == 1


def test_a_figure_backed_by_the_summary_is_allowed_in_the_difference(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(difference="The loaded files show 4,132 going out a month, 3,613.17 in June.")])
    assert len(found) == 1


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


@pytest.mark.parametrize("bad", SHAPE, ids=[str(k) for k in range(len(SHAPE))])
def test_an_entry_of_the_wrong_shape_is_dropped(check_verifier, conn, example_loaded, bad):
    found, _, _ = go(check_verifier, [bad])
    assert found == [] and dropped(conn) == [(1, s5.DROP_SHAPE)]
    assert s5.payloads(conn, "verify.dropped")[0]["finding"] == bad


def test_a_data_entry_does_not_need_a_quote_and_a_brief_entry_does_not_need_a_summary(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(), brief_entry(RENT_CLAIM, RENT_QUOTE, RENT_DIFFERENCE, summary=DROP)],
                     message=MESSAGE + " " + RENT_CLAIM + ".")
    assert [f["kind"] for f in found] == ["data", "brief"]


def test_the_shape_is_checked_before_anything_else(check_verifier, conn, example_loaded):
    go(check_verifier, [entry(claim="not in the message at all 99", difference=DROP)])
    assert dropped(conn) == [(1, s5.DROP_SHAPE)]


# ---- rule 2: quoted from the message -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("claim", ["I spend about 6k a month", "i spend about 5k a month", "I spend about 5k a MONTH",
                                   "I spend 5k a month", "I earn about 5k a month"])
def test_a_claim_that_is_not_part_of_the_message_is_dropped(check_verifier, conn, example_loaded, claim):
    found, _, _ = go(check_verifier, [entry(claim=claim)])
    assert found == [] and dropped(conn) == [(1, s5.DROP_NOT_QUOTED)]


def test_a_claim_is_compared_with_white_space_made_one_line_on_both_sides(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(claim="I spend about 5k a month")],
                     message="I spend  about\n5k   a month. How long until I reach my target?")
    assert len(found) == 1 and found[0]["claim"] == "I spend about 5k a month"


def test_the_whole_message_may_be_the_claim(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(claim=MESSAGE)])
    assert len(found) == 1 and found[0]["claim"] == MESSAGE


def test_the_claim_is_checked_against_the_message_not_the_brief(check_verifier, conn, example_loaded):
    go(check_verifier, [entry(claim=RENT_QUOTE)])
    assert dropped(conn) == [(1, s5.DROP_NOT_QUOTED)]


# ---- rule 3: one figure in the claim ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("message, claim", [
    ("I spend a lot of money. How long until I reach my target of 20,000?", "I spend a lot of money"),
    ("I have 3 accounts and spend 5k. Is that fine?", "I have 3 accounts"),
    ("I earn 3,000 or 3,200 a month. Is that fine?", "I earn 3,000 or 3,200 a month"),
    ("I earn 3,000 and spend 2,500 a month.", "I earn 3,000 and spend 2,500 a month"),
    ("On 2026-03-14 I paid 500 for the flat.", "On 2026-03-14 I paid 500 for the flat"),
])
def test_a_claim_without_exactly_one_figure_is_dropped(check_verifier, conn, example_loaded, message, claim):
    found, _, _ = go(check_verifier, [entry(claim=claim)], message=message)
    assert found == [] and dropped(conn) == [(1, s5.DROP_CLAIM_FIGURE)]


def test_the_figure_of_the_claim_is_checked_before_the_summary(check_verifier, conn, example_loaded):
    go(check_verifier, [entry(claim="I spend a lot of money", summary=99)], message="I spend a lot of money. 5k?")
    assert dropped(conn) == [(1, s5.DROP_CLAIM_FIGURE)]


# ---- rule 4: the quote is in the brief, the summary is of this session ---------------------------------------------------------------------

@pytest.mark.parametrize("quote", ["Rent is fixed at 1,500 a month", "rent is fixed at 1,150 a month",
                                   "Rent is fixed at 1,150 a month Count it as spending", "Rent is 1,150 a month",
                                   "Rent is fixed at 1,150 a month. "])
def test_a_quote_that_is_not_in_the_brief_is_dropped(check_verifier, conn, quote):
    found, _, _ = go_brief(check_verifier, [brief_entry(quote=quote)])
    assert found == [] and dropped(conn) == [(1, s5.DROP_NOT_IN_BRIEF)]


def test_the_goal_is_not_a_place_to_quote_from(check_verifier, conn):
    brief = h.make_brief(goal="Keep spending under 4,000 a month")
    go_brief(check_verifier, [brief_entry(quote="Keep spending under 4,000 a month")], brief=brief)
    assert dropped(conn) == [(1, s5.DROP_NOT_IN_BRIEF)]


def test_the_quote_is_compared_with_white_space_made_one_line(check_verifier, conn):
    found, _, _ = go_brief(check_verifier, [brief_entry(quote="Rent is  fixed\nat 1,150 a month")])
    assert len(found) == 1


@pytest.mark.parametrize("summary", [99, 0, -1, 2])
def test_a_summary_that_does_not_exist_is_dropped(check_verifier, conn, example_loaded, summary):
    found, _, _ = go(check_verifier, [entry(summary=summary)])
    assert found == [] and dropped(conn) == [(1, s5.DROP_NO_SUMMARY.format(summary=summary))]


def test_a_summary_of_another_conversation_is_dropped(check_verifier, summaries, conn, example_loaded):
    summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 3}, session_id="another")
    found, _, _ = go(check_verifier, [entry(summary=1)], calls=())
    assert found == [] and dropped(conn) == [(1, s5.DROP_NO_SUMMARY.format(summary=1))]


def test_the_quote_of_a_brief_entry_is_checked_before_its_figure(check_verifier, conn):
    go_brief(check_verifier, [brief_entry(quote="Count it as spending, not in the brief 5")])
    assert dropped(conn) == [(1, s5.DROP_NOT_IN_BRIEF)]


# ---- rule 5: one figure in the quote ----------------------------------------------------------------------------------------------------

def test_a_quote_without_a_figure_is_dropped(check_verifier, conn):
    found, _, _ = go_brief(check_verifier, [brief_entry(quote="Count it as spending")])
    assert found == [] and dropped(conn) == [(1, s5.DROP_REFERENCE_FIGURE)]


def test_a_quote_with_two_figures_is_dropped(check_verifier, conn):
    brief = h.make_brief(particulars=[{"what": "Rent is 1,150 and bills are 300 a month", "handling": "Count them"}])
    found, _, _ = go_brief(check_verifier, [brief_entry(quote="Rent is 1,150 and bills are 300 a month")], brief=brief)
    assert found == [] and dropped(conn) == [(1, s5.DROP_REFERENCE_FIGURE)]


def test_a_shorter_quote_with_one_figure_of_a_text_with_two_is_allowed(check_verifier, conn):
    brief = h.make_brief(particulars=[{"what": "Rent is 1,150 and bills are 300 a month", "handling": "Count them"}])
    found, _, _ = go_brief(check_verifier, [brief_entry(quote="Rent is 1,150")], brief=brief)
    assert len(found) == 1 and found[0]["reference_figure"] == "1,150"


# ---- rule 6: comparable --------------------------------------------------------------------------------------------------------------------

def test_a_date_against_a_figure_of_the_brief_that_is_not_a_date_is_dropped(check_verifier, conn):
    found, _, _ = go_brief(check_verifier, [brief_entry("My wedding is on 2027-06-12", RENT_QUOTE, RENT_DIFFERENCE)],
                           message="My wedding is on 2027-06-12")
    assert found == [] and dropped(conn) == [(1, s5.DROP_NOT_COMPARABLE)]


def test_a_number_against_a_date_of_the_brief_is_dropped(check_verifier, conn):
    brief = h.make_brief(particulars=[{"what": "The wedding is on 2027-06-12", "handling": "Plan for it"}])
    found, _, _ = go_brief(check_verifier, [brief_entry(RENT_CLAIM, "The wedding is on 2027-06-12",
                                                        "The brief gives 2027-06-12.")], brief=brief)
    assert found == [] and dropped(conn) == [(1, s5.DROP_NOT_COMPARABLE)]


def test_a_date_against_a_summary_is_dropped(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry("My wedding is on 2027-06-12")], message="My wedding is on 2027-06-12")
    assert found == [] and dropped(conn) == [(1, s5.DROP_NOT_COMPARABLE)]


# ---- rule 7: they differ ------------------------------------------------------------------------------------------------------------------------

def test_a_claim_within_five_percent_of_a_summary_is_dropped(check_verifier, conn, flat):
    found, _, _ = go(check_verifier, [entry(difference="The loaded files show 5,080.00 going out a month.")])
    assert found == [] and dropped(conn) == [(1, s5.DROP_WITHIN_TOLERANCE)]


def test_a_claim_within_five_percent_of_the_brief_is_dropped(check_verifier, conn):
    found, _, _ = go_brief(check_verifier, [brief_entry("My rent is 1,200 a month")], message="My rent is 1,200 a month")
    assert found == [] and dropped(conn) == [(1, s5.DROP_WITHIN_TOLERANCE)]


@pytest.mark.parametrize("amount, opens", [("1,207.50", False), ("1,207.51", True), ("1,092.50", False),
                                           ("1,092.49", True), ("1,150", False), ("1,151", False)])
def test_the_edge_of_the_tolerance(check_verifier, conn, amount, opens):
    claim = f"My rent is {amount} a month"
    found, _, _ = go_brief(check_verifier, [brief_entry(claim)], message=claim)
    assert (len(found) == 1) is opens
    if not opens:
        assert dropped(conn) == [(1, s5.DROP_WITHIN_TOLERANCE)]


def test_equal_dates_are_dropped_as_within_tolerance(check_verifier, conn):
    brief = h.make_brief(particulars=[{"what": "The wedding is on 2027-06-12", "handling": "Plan for it"}])
    found, _, _ = check_verifier([report(brief_entry("The wedding is on 2027-06-12", "The wedding is on 2027-06-12",
                                                     "The brief gives 2027-06-12."))],
                                 "The wedding is on 2027-06-12", brief=brief)
    assert found == [] and dropped(conn) == [(1, s5.DROP_WITHIN_TOLERANCE)]


def test_a_difference_of_one_day_in_a_date_is_a_finding(check_verifier, conn):
    brief = h.make_brief(particulars=[{"what": "The wedding is on 2027-06-12", "handling": "Plan for it"}])
    found, _, _ = check_verifier([report(brief_entry("The wedding is on 2027-06-11", "The wedding is on 2027-06-12",
                                                     "The brief gives 2027-06-12."))],
                                 "The wedding is on 2027-06-11", brief=brief)
    assert len(found) == 1


# ---- rule 8: numbers in the difference -----------------------------------------------------------------------------------------------------------

def test_a_number_from_nowhere_in_the_difference_is_dropped(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(difference="The loaded files show 6,000 going out a month.")])
    assert found == [] and dropped(conn) == [(1, s5.DROP_DIFFERENCE_NUMBERS.format(numbers="6,000"))]


def test_the_numbers_are_listed_as_written_in_order_and_joined(check_verifier, conn, example_loaded):
    text = "The files show 4,200 or 7,300 going out, and 4,132.31 on average, 4,200 again."
    go(check_verifier, [entry(difference=text)])
    assert dropped(conn) == [(1, s5.DROP_DIFFERENCE_NUMBERS.format(numbers="4,200, 7,300"))]


def test_numbers_of_the_message_the_brief_and_the_summary_are_backed(check_verifier, conn, example_loaded):
    text = "You said 5k, the brief has 1,150 and the files show 4,132.31 or 3,613.17 in June."
    found, _, _ = go(check_verifier, [entry(difference=text)])
    assert len(found) == 1


def test_a_small_bare_number_is_exempt(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(difference="The loaded files show 4,132.31 a month over the last 3 months.")])
    assert len(found) == 1


def test_a_number_of_a_summary_does_not_back_a_brief_finding(check_verifier, conn, example_loaded):
    found, _, _ = check_verifier([summary_call(), report(brief_entry(difference="The brief gives 1,150 and the files 4,132.31."))],
                                 RENT_MESSAGE)
    assert found == [] and dropped(conn) == [(1, s5.DROP_DIFFERENCE_NUMBERS.format(numbers="4,132.31"))]


def test_a_number_of_a_saved_input_does_not_back_the_difference(check_verifier, conn, example_loaded):
    s5.put_input(conn, "monthly_income", "7,777")
    go(check_verifier, [entry(difference="The loaded files show 4,132.31 and you once saved 7,777.")])
    assert dropped(conn) == [(1, s5.DROP_DIFFERENCE_NUMBERS.format(numbers="7,777"))]


def test_the_summary_is_the_one_the_finding_cites(check_verifier, conn, example_loaded):
    """Summary 2 is a balance; its figure does not back a difference that cites summary 1."""
    calls = (summary_call(), h.tool("data_summary", {"measure": "balance", "account": "checking_2026"}))
    go(check_verifier, [entry(summary=1, difference="The files show 4,132.31 and a balance of 6,318.60.")], calls=calls)
    assert dropped(conn) == [(1, s5.DROP_DIFFERENCE_NUMBERS.format(numbers="6,318.60"))]


def test_a_difference_with_no_numbers_is_allowed(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(difference="The loaded files show less going out than that.")])
    assert len(found) == 1


# ---- rule 9: no judgment words ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("word", list(s5.JUDGMENT_WORDS))
def test_each_judgment_word_drops_the_entry(check_verifier, conn, example_loaded, word):
    text = f"The loaded files show 4,132.31 a month, and that is {word} the figure."
    found, _, _ = go(check_verifier, [entry(difference=text)])
    assert found == [] and dropped(conn) == [(1, s5.DROP_TONE.format(word=word))]


@pytest.mark.parametrize("written, word", [("BUT", "but"), ("However", "however"), ("Unfortunately", "unfortunately"),
                                           ("ReAlLy", "really")])
def test_the_case_is_ignored_and_the_word_is_shown_in_lower_case(check_verifier, conn, example_loaded, written, word):
    go(check_verifier, [entry(difference=f"The loaded files show 4,132.31 a month. {written} it is so.")])
    assert dropped(conn) == [(1, s5.DROP_TONE.format(word=word))]


def test_the_first_word_in_the_text_is_the_one_named(check_verifier, conn, example_loaded):
    go(check_verifier, [entry(difference="The loaded files show 4,132.31 a month; it must be so, but that is wrong.")])
    assert dropped(conn) == [(1, s5.DROP_TONE.format(word="must"))]


@pytest.mark.parametrize("text", ["The files show 4,132.31 and butter is not a judgment.",
                                  "The files show 4,132.31 and the shoulders are fine.",
                                  "The files show 4,132.31 and mustard is a condiment.",
                                  "The files show 4,132.31 with some errors elsewhere.",
                                  "The files show 4,132.31, which is the actuality.",
                                  "The files show 4,132.31 and the butterfly flew."])
def test_a_word_that_only_contains_a_judgment_word_is_allowed(check_verifier, conn, example_loaded, text):
    found, _, _ = go(check_verifier, [entry(difference=text)])
    assert len(found) == 1


def test_numbers_are_checked_before_tone(check_verifier, conn, example_loaded):
    go(check_verifier, [entry(difference="It is wrong: the files show 9,999.")])
    assert dropped(conn) == [(1, s5.DROP_DIFFERENCE_NUMBERS.format(numbers="9,999"))]


# ---- rule 10: raised once ----------------------------------------------------------------------------------------------------------------------------

def test_the_same_difference_in_the_same_conversation_is_dropped(check_verifier, conn, example_loaded):
    first, _, _ = go(check_verifier, [entry()])
    second, _, _ = go(check_verifier, [entry()], calls=(), message=MESSAGE)
    assert len(first) == 1 and second == []
    assert dropped(conn) == [(1, s5.DROP_ALREADY.format(id=first[0]["id"]))]


def test_the_figures_are_compared_by_value_not_by_the_words(check_verifier, conn, example_loaded):
    first, _, _ = go(check_verifier, [entry()])
    go(check_verifier, [entry("I spend roughly 5,000.00 a month")], calls=(), message="I spend roughly 5,000.00 a month")
    assert dropped(conn) == [(1, s5.DROP_ALREADY.format(id=first[0]["id"]))]


def test_a_new_summary_with_the_same_value_is_the_same_reference_figure(check_verifier, conn, example_loaded):
    first, _, _ = go(check_verifier, [entry()])
    go(check_verifier, [entry(summary=2)])
    assert dropped(conn) == [(1, s5.DROP_ALREADY.format(id=first[0]["id"]))]


def test_another_claim_figure_is_a_new_difference(check_verifier, conn, example_loaded):
    go(check_verifier, [entry()])
    found, _, _ = go(check_verifier, [entry("I spend about 6k a month", summary=2)], message="I spend about 6k a month")
    assert len(found) == 1 and found[0]["id"] == 2


def test_the_same_entry_twice_in_one_report_opens_one_finding(check_verifier, conn, example_loaded):
    found, _, _ = go(check_verifier, [entry(), entry()])
    assert [f["id"] for f in found] == [1] and dropped(conn) == [(2, s5.DROP_ALREADY.format(id=1))]


def test_a_decided_finding_is_still_raised_once(check_verifier, findings, conn, example_loaded):
    from harness.calc import decisions
    first, _, _ = go(check_verifier, [entry()])
    decision = decisions.record_decision(conn, session_id=SESSION, kind="finding", step_id=None, question=first[0]["block"],
                                         options=first[0]["options"], choice="2", words="2", runs=[])
    findings.close_finding(conn, first[0]["id"], decision_id=decision["id"], choice="2", saved=False, session_id=SESSION)
    found, _, _ = go(check_verifier, [entry()], calls=())
    assert found == [] and dropped(conn) == [(1, s5.DROP_ALREADY.format(id=1))]


def test_a_finding_of_another_conversation_does_not_count(check_verifier, findings, summaries, conn, example_loaded):
    summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 3}, session_id="another")
    findings.open_finding(conn, session_id="another", kind="data", claim=CLAIM, claim_figure="5k", reference="x",
                          reference_figure=SPENDING, summary_id=1, difference=DIFFERENCE)
    found, _, _ = go(check_verifier, [entry(summary=2)])
    assert len(found) == 1 and found[0]["id"] == 2 and s5.events(conn, "verify.dropped") == []


def test_the_same_figures_of_another_kind_are_not_the_same_difference(check_verifier, findings, conn):
    findings.open_finding(conn, session_id=SESSION, kind="data", claim="x 1,400", claim_figure="1,400", reference="y",
                          reference_figure="1,150", summary_id=None, difference="d")
    found, _, _ = go_brief(check_verifier, [brief_entry()])
    assert len(found) == 1 and s5.events(conn, "verify.dropped") == []


def test_a_finding_of_kind_earlier_with_the_same_figures_counts_only_as_its_own_kind(check_verifier, findings, conn):
    findings.open_finding(conn, session_id=SESSION, kind="earlier", claim="1,400", claim_figure="1,400", reference="1,150",
                          reference_figure="1,150", input_name="rent", earlier={"value": "1,150", "note": "n", "ts": "t",
                                                                               "session_id": "s"}, pending_note="n")
    found, _, _ = go_brief(check_verifier, [brief_entry()])
    assert len(found) == 1


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


def test_the_entries_that_were_dropped_do_not_count_towards_the_limit(check_verifier, conn):
    found, _, _ = wide_check(check_verifier, ["junk", RENT, entry(), GYM, PHONE])
    assert len(found) == 2
    assert dropped(conn) == [(1, s5.DROP_SHAPE), (3, s5.DROP_NOT_QUOTED), (5, s5.DROP_LIMIT)]


def test_two_findings_are_allowed_and_the_events_are_in_the_order_of_the_entries(check_verifier, conn):
    result = wide_check(check_verifier, ["junk", RENT, GYM, PHONE])
    names = [k for k in h.kinds(conn) if k.startswith(("verify.", "finding."))]
    assert names == ["verify.report", "verify.dropped", "finding.opened", "finding.opened", "verify.dropped"]
    assert [p["index"] for p in s5.payloads(conn, "verify.dropped")] == [1, 4]
    assert len(result[0]) == 2


def test_an_entry_already_raised_is_dropped_for_that_before_the_limit(check_verifier, conn):
    found, _, _ = wide_check(check_verifier, [RENT, GYM, RENT])
    assert len(found) == 2 and dropped(conn) == [(3, s5.DROP_ALREADY.format(id=1))]


def test_findings_of_earlier_messages_do_not_use_up_the_two(check_verifier, conn):
    wide_check(check_verifier, [RENT, GYM])
    found, _, _ = wide_check(check_verifier, [PHONE, CAR])
    assert [f["id"] for f in found] == [3, 4] and s5.events(conn, "verify.dropped") == []
