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




# --- trace (SPEC 5.2): which source a figure is traced to ---

def traced(text, sources):
    return [(each["text"], each["source"], each["run_id"]) for each in provenance.trace(text, sources)]


def test_a_number_leads_to_a_run_only_when_the_run_produced_it():
    sources = [("person", None, "I have 10,000 saved, 18 months"), ("run", 4, {"balance": "10000", "gap": "5600"},
                                                                    {"savings": "10000", "months": "18"})]
    assert traced("10,000 then 5,600 after 18 months", sources) == [
        ("10,000", "person", None), ("5,600", "run", 4), ("18", "person", None)]


def test_a_single_output_is_produced_even_when_an_input_has_the_same_value():
    sources = [("person", None, "I take home 10,000 and spend 5,000"),
               ("run", 3, "5000", {"income": "10000", "spending": "5000"})]
    assert traced("5,000", sources) == [("5,000", "run", 3)]


def test_a_value_inside_an_object_or_a_list_output_counts():
    rows = [{"month": 1, "balance": "1300"}, {"month": 2, "balance": "2600.5"}]
    assert traced("2,600.50", [("run", 2, rows, {"monthly": "1300"})]) == [("2,600.50", "run", 2)]


def test_a_year_or_a_part_of_a_date_never_leads_to_a_run_but_a_whole_date_does():
    sources = [("person", None, "the wedding is in 2027"), ("run", 3, {"due": "2027-05-13", "rows": 2028},
                                                            {"wedding": "2027-06-12"})]
    found = traced("Due 2027-05-13, in 2027, wedding 2027-06-12", sources)
    assert found == [("2027-05-13", "run", 3), ("2027", "person", None), ("2027-06-12", "person", None)]
    assert traced("2028", [("run", 3, {"x": "2028-01-31"}, {})]) == [("2028", "none", None)]


def test_of_several_runs_the_first_given_wins():
    sources = [("run", 9, "350", {"total": "175"}), ("run", 4, "350", {"a": "100"})]
    assert traced("350", sources) == [("350", "run", 9)]
    assert traced("350", list(reversed(sources))) == [("350", "run", 4)]


def test_a_run_given_without_inputs_counts_its_whole_output():
    assert traced("4,583.33", [("run", 1, "4583.333")]) == [("4,583.33", "run", 1)]
