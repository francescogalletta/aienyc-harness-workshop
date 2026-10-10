"""SPEC 5.8: every number the agent sends out must already be known."""
from harness.calc import provenance


def unbacked(text, sources):
    return provenance.unbacked(text, sources)


def test_a_module_result_backs_the_ways_of_writing_it():
    for written in ["4,583.33", "4,583", "4.6k", "$4,583.33"]:
        assert unbacked(written, ["4583.333"]) == []


def test_but_not_a_rounding_that_is_too_coarse_or_too_far():
    assert unbacked("4,600", ["4583.333"]) == ["4,600"]
    assert unbacked("4,584", ["4583.333"]) == ["4,584"]
    assert unbacked("4.7k", ["4583.333"]) == ["4.7k"]


def test_unbacked_numbers_come_back_as_written_in_order_each_once():
    text = "Pay 1,234 now, 5,678 later and 1,234 again, then 12.5% and 7.7k."
    assert unbacked(text, []) == ["1,234", "5,678", "12.5%", "7.7k"]


def test_any_one_source_is_enough():
    assert unbacked("3,000 and 4,000", ["rent 3000", "bonus 4000"]) == []
    assert unbacked("2,001", [{"output": "2000"}]) == ["2,001"]


def test_a_percentage_in_a_source_backs_its_value_and_its_value_over_100():
    assert unbacked("50%", ["The rate is 50%"]) == []
    assert unbacked("0.5", ["The rate is 50%"]) == []
    assert unbacked("12.5%", ["0.125"]) == []


def test_a_date_is_backed_by_the_same_date_or_by_each_of_its_parts():
    assert unbacked("due on 2026-10-13", ["today is 2026-10-13"]) == []
    assert unbacked("2026-10-13", ["2026", "13"]) == []
    assert unbacked("2026-10-12", ["2026"]) == []          # month and day are 12 or less


def test_a_date_with_a_part_nobody_knows_is_not_backed():
    assert unbacked("2026-10-13", ["2026"]) != []
    assert unbacked("2027-10-09", ["2026-10-09"]) != []


def test_a_bare_whole_number_up_to_12_is_never_checked_but_13_is():
    assert unbacked("3 payments, 12 months, and 0 left", []) == []
    assert unbacked("13 months", []) == ["13"]


def test_small_numbers_are_checked_when_they_are_not_bare():
    for text in ["$5", "5.5", "5k", "5%"]:
        assert len(unbacked(text, [])) == 1


