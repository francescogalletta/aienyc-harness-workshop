"""SPEC 5.8: every number the agent sends out must already be known."""
import pytest


def unbacked(text, sources):
    from harness.calc.provenance import unbacked as check
    return check(text, sources)


def test_the_smallest_number_that_is_checked():
    from harness.calc import provenance
    assert provenance.SMALL == 12


# ---- the examples of the contract --------------------------------------------------------------

@pytest.mark.parametrize("written", ["4,583.33", "4,583", "4.6k"])
def test_a_module_result_backs_the_ways_of_writing_it(written):
    assert unbacked(written, ["4583.333"]) == []


def test_but_not_a_rounding_that_is_too_coarse_or_too_far():
    assert unbacked("4,600", ["4583.333"]) == ["4,600"]


def test_a_result_of_one_half_backs_fifty_percent():
    assert unbacked("50%", ["0.5"]) == []


# ---- what is returned --------------------------------------------------------------------------

def test_nothing_to_check():
    assert unbacked("", []) == []
    assert unbacked("No numbers here at all.", []) == []


def test_unbacked_numbers_come_back_as_written_in_order_each_once():
    text = "Pay 1,234 now, 5,678 later and 1,234 again, then 90.5 and 7.7k."
    assert unbacked(text, []) == ["1,234", "5,678", "90.5", "7.7k"]


def test_a_percentage_is_returned_with_its_sign():
    assert unbacked("A rate of 12.5% applies.", []) == ["12.5%"]


def test_a_currency_sign_is_ignored_when_reading():
    assert unbacked("$4,583.33", ["4583.333"]) == []
    assert unbacked("€5,000 and £5,000", ["5000"]) == []
    [found] = unbacked("It costs $9,999.", ["5000"])
    assert "9,999" in found


def test_a_minus_sign_is_not_part_of_the_number():
    assert unbacked("-4,000", []) == ["4,000"]
    assert unbacked("-1,500", ["1500"]) == []
    assert unbacked("1,500", ["-1500"]) == []


def test_any_one_source_is_enough():
    assert unbacked("3,000 and 4,000", ["rent 3000", "bonus 4000"]) == []
    assert unbacked("3,000 and 4,000", ["rent 3000"]) == ["4,000"]


# ---- reading numbers ---------------------------------------------------------------------------

def test_commas_are_thousands_separators_in_text_and_in_sources():
    assert unbacked("1,234,567", ["1234567"]) == []
    assert unbacked("1234567", ["1,234,567"]) == []


def test_a_source_that_is_not_a_string_is_turned_into_json_text():
    assert unbacked("2,000", [2000]) == []
    assert unbacked("2,000", [{"output": "2000", "run_id": 4}]) == []
    assert unbacked("2,000.5", [[1, 2000.5]]) == []
    assert unbacked("2,001", [{"output": "2000"}]) == ["2,001"]


@pytest.mark.parametrize("text", ["step s99 of the plan", "the 99th payment", "on the 33rd", "group a99"])
def test_a_number_glued_to_a_letter_is_not_read(text):
    assert unbacked(text, []) == []


# ---- precision and backing ---------------------------------------------------------------------

@pytest.mark.parametrize("written, backed", [
    ("4,583", True), ("4,584", False),                 # whole numbers: within half of 1
    ("4,583.3", True), ("4,583.4", False),             # one decimal: within 0.05
    ("4,583.33", True), ("4,583.34", False),           # two decimals: within 0.005
    ("4.6k", True), ("4.7k", False),                   # 4.6k is 4600 to the nearest 100
    ("5k", True), ("6k", False),                       # 5k is 5000 to the nearest 1000
    ("5K", True),
])
def test_a_number_is_backed_within_half_its_precision(written, backed):
    assert (unbacked(written, ["4583.333"]) == []) is backed


@pytest.mark.parametrize("written, backed", [
    ("50%", True), ("12.5%", False), ("0.5", True), ("50", True),
])
def test_a_percentage_in_a_source_gives_both_its_value_and_its_value_over_100(written, backed):
    assert (unbacked(written, ["The rate is 50%"]) == []) is backed


@pytest.mark.parametrize("source, backed", [
    ("0.125", True),                 # 12.5% is also 0.125
    ("12.5", True),
    ("0.13", False),
])
def test_a_percentage_in_text_matches_its_value_or_its_value_over_100(source, backed):
    assert (unbacked("12.5%", [source]) == []) is backed


# ---- dates -------------------------------------------------------------------------------------

def test_a_date_is_backed_by_the_same_date():
    assert unbacked("due on 2026-10-13", ["today is 2026-10-13"]) == []


def test_a_date_is_backed_when_each_part_is_backed_or_exempt():
    assert unbacked("2026-10-13", ["2026", "13"]) == []
    assert unbacked("2026-10-12", ["2026"]) == []          # month and day are 12 or less


def test_a_date_with_a_part_nobody_knows_is_not_backed():
    for text, sources in [("2026-10-13", ["2026"]), ("2027-10-09", ["2026-10-09"]), ("2026-10-13", [])]:
        found = unbacked(text, sources)
        assert found and any(part in found[0] for part in ("2026", "2027", "13"))


def test_every_part_of_a_date_in_a_source_is_a_known_value():
    assert unbacked("13 payments", ["the due date is 2026-10-13"]) == []
    assert unbacked("in 2026", ["the due date is 2026-10-13"]) == []


# ---- exempt ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["3 payments", "0 left", "12 months", "1. First, 2. second, 12. last"])
def test_a_bare_whole_number_up_to_12_is_never_checked(text):
    assert unbacked(text, []) == []


def test_13_is_checked():
    assert unbacked("13 months", []) == ["13"]


@pytest.mark.parametrize("text", ["$5", "€5", "5.0", "5.5", "5k", "5%", "£12"])
def test_small_numbers_are_checked_when_they_are_not_bare(text):
    assert len(unbacked(text, [])) == 1


# ---- what it deliberately does not catch ------------------------------------------------------

def test_a_small_whole_number_worked_out_in_the_head_gets_through():
    assert unbacked("That is 7 months of saving.", ["5 months", "2 months"]) == []


def test_numbers_in_words_get_through():
    assert unbacked("About three thousand, or twenty percent.", []) == []


def test_m_and_bn_suffixes_get_through():
    assert unbacked("A fund of 250m, or 3bn.", []) == []


def test_decimal_commas_get_through():
    assert unbacked("About 12,5 euros.", []) == []


def test_a_right_number_with_the_wrong_meaning_gets_through():
    assert unbacked("The deposit is 1,500.", ["The rent is 1500."]) == []


def test_a_day_of_12_or_less_worked_out_in_the_head_gets_through_when_the_year_is_known():
    assert unbacked("The payment falls on 2026-04-11.", ["2026"]) == []


def test_signs_are_not_checked():
    assert unbacked("You are short by 1,500.", ["You have a surplus of 1500."]) == []
