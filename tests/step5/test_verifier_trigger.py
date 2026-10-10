"""SPEC 9.6: when the verifier runs: `needs_check`."""
import pytest

import step5_helpers as s5
from step5_helpers import h, put_import

NO_FIGURES_IN_THE_BRIEF = {"particulars": [{"what": "I rent a flat", "handling": "Count it as spending"}],
                           "inputs": [{"name": "Monthly income", "description": "What comes in each month"}]}


def bare_brief(**changes):
    return h.make_brief(**{**NO_FIGURES_IN_THE_BRIEF, **changes})


@pytest.mark.parametrize("message", [
    "I spend about 5k a month", "My rent is 1,150", "I earn 4000", "I saved 12.5 last year", "It is 15%",
    "My wedding is on 2027-06-12", "I owe $300", "Between 150 and 200", "I have 13 cards",
])
def test_a_message_with_a_figure_is_checked_when_the_brief_has_a_figure(verifier, conn, brief, message):
    assert verifier.needs_check(conn, brief, message) is True


@pytest.mark.parametrize("message", [
    "", "I spend a lot", "I have 3 accounts", "Could you help me with 12 things?", "step s1 of the 1st plan",
    "Between 0 and 12", "Yes", "/quit",
])
def test_a_message_without_a_figure_is_not_checked(verifier, conn, brief, message):
    put_import(conn, "main", [("2026-03-01", "1.00", "a")])
    s5.put_input(conn, "monthly_income", "5000")
    assert verifier.needs_check(conn, brief, message) is False


def test_a_figure_with_nothing_to_check_it_against_is_not_checked(verifier, conn):
    assert verifier.needs_check(conn, bare_brief(), s5.MESSAGE) is False


def test_the_brief_is_something_to_check_against_when_it_holds_a_figure_in_a_particular(verifier, conn):
    brief = bare_brief(particulars=[{"what": "Rent is fixed at 1,150 a month", "handling": "Count it"}])
    assert verifier.needs_check(conn, brief, s5.MESSAGE) is True


def test_the_handling_of_a_particular_counts(verifier, conn):
    brief = bare_brief(particulars=[{"what": "Rent", "handling": "Count 1,150 as spending"}])
    assert verifier.needs_check(conn, brief, s5.MESSAGE) is True


def test_the_description_and_the_name_of_an_input_count(verifier, conn):
    assert verifier.needs_check(conn, bare_brief(inputs=[{"name": "Target", "description": "Aim for 20,000"}]),
                                s5.MESSAGE) is True
    assert verifier.needs_check(conn, bare_brief(inputs=[{"name": "Fund of 20,000", "description": "A fund"}]),
                                s5.MESSAGE) is True


def test_a_date_in_the_brief_counts(verifier, conn):
    brief = bare_brief(particulars=[{"what": "The wedding is on 2027-06-12", "handling": "Plan for it"}])
    assert verifier.needs_check(conn, brief, s5.MESSAGE) is True


def test_a_bare_small_number_in_the_brief_is_not_a_figure(verifier, conn):
    brief = bare_brief(particulars=[{"what": "I pay rent 12 times a year", "handling": "Count 3 months ahead"}])
    assert verifier.needs_check(conn, brief, s5.MESSAGE) is False


def test_the_goal_and_the_process_are_not_references(verifier, conn):
    brief = bare_brief(goal="Save 20,000 by 2027-06-12")
    assert verifier.needs_check(conn, brief, s5.MESSAGE) is False


def test_loaded_transactions_are_something_to_check_against(verifier, conn):
    put_import(conn, "main", [("2026-03-01", "1.00", "a")])
    assert verifier.needs_check(conn, bare_brief(), s5.MESSAGE) is True


def test_a_saved_input_is_something_to_check_against(verifier, conn):
    s5.put_input(conn, "monthly_income", "5000")
    assert verifier.needs_check(conn, bare_brief(), s5.MESSAGE) is True


def test_the_files_cleared_leave_nothing_to_check_against(adapter, verifier, conn, tmp_path):
    s5.add_text(adapter, conn, tmp_path, "bank.csv", s5.simple())
    assert verifier.needs_check(conn, bare_brief(), s5.MESSAGE) is True
    adapter.clear_data(conn, session_id="C")
    assert verifier.needs_check(conn, bare_brief(), s5.MESSAGE) is False


def test_needs_check_calls_no_model(verifier, conn, brief):
    assert verifier.needs_check(conn, brief, s5.MESSAGE) is True
    assert s5.events(conn) == []
