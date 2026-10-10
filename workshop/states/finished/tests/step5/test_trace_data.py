"""SPEC 7.1 (step 5): the `data` label of `trace`: figures that a data summary of the conversation backs."""
import pytest

OUTPUT = {"value": "4132.31", "as_of": None}


def trace(text, sources):
    from harness.calc.provenance import trace as function
    return function(text, sources)


def sources_of(text, sources):
    return [(item["source"], item["run_id"]) for item in trace(text, sources)]


def test_the_labels_and_their_order(provenance):
    assert provenance.SOURCE_LABELS == ("run", "data", "input", "note", "brief", "person", "today")


def test_a_figure_only_a_summary_backs_is_data_and_names_the_summary():
    [found] = trace("The files show 4,132.31 a month.", [("data", 4, OUTPUT)])
    assert found == {"text": "4,132.31", "start": 15, "end": 23, "source": "data", "run_id": 4}


def test_the_value_of_a_summary_is_read_as_json_text_when_it_is_not_text():
    assert sources_of("4,132.31", [("data", 2, OUTPUT)]) == [("data", 2)]
    assert sources_of("4,132.31", [("data", 2, "4132.31")]) == [("data", 2)]


def test_a_run_comes_before_data():
    sources = [("data", 4, OUTPUT), ("run", 9, {"inputs": {}, "output": "4132.31"})]
    assert sources_of("4,132.31", sources) == [("run", 9)]


@pytest.mark.parametrize("label", ["input", "note", "brief", "person", "today"])
def test_data_comes_before_the_other_labels(label):
    sources = [(label, None, "4132.31"), ("data", 4, OUTPUT)]
    assert sources_of("4,132.31", sources) == [("data", 4)]


def test_the_last_summary_that_backs_a_figure_is_named():
    sources = [("data", 1, OUTPUT), ("data", 2, {"value": "10.00"}), ("data", 3, OUTPUT)]
    assert sources_of("4,132.31", sources) == [("data", 3)]


def test_a_summary_that_does_not_back_the_figure_is_not_named():
    sources = [("data", 1, OUTPUT), ("data", 2, {"value": "10.00"})]
    assert sources_of("10.00", sources) == [("data", 2)]


def test_a_figure_within_half_its_precision_is_backed_and_one_beyond_it_is_not():
    assert sources_of("4,132.3", [("data", 5, OUTPUT)]) == [("data", 5)]
    assert sources_of("4,132", [("data", 5, OUTPUT)]) == [("data", 5)]
    assert sources_of("4,133", [("data", 5, OUTPUT)]) == [("none", None)]


def test_a_figure_no_summary_backs_is_none():
    assert sources_of("4,200", [("data", 4, OUTPUT)]) == [("none", None)]


def test_a_small_number_is_small_whatever_the_sources():
    assert sources_of("3 months", [("data", 4, {"value": "3"})]) == [("small", None)]


def test_the_items_labelled_none_are_the_unbacked_numbers():
    from harness.calc.provenance import unbacked
    text = "You said 5k; the files show 4,132.31 and 4,200."
    sources = [("data", 4, OUTPUT), ("person", None, "I spend 5k")]
    values = [value for _, _, value in sources]
    assert [i["text"] for i in trace(text, sources) if i["source"] == "none"] == unbacked(text, values)


def test_the_run_id_of_a_data_item_for_every_occurrence():
    found = trace("4,132.31 and 4,132.31 again", [("data", 6, OUTPUT)])
    assert [(i["source"], i["run_id"]) for i in found] == [("data", 6), ("data", 6)]


def test_a_date_whose_parts_are_backed_by_data_and_a_run_is_data_with_the_first_part_of_that_label():
    sources = [("run", 2, "30"), ("data", 7, "2027")]
    [found] = trace("On 2027-06-30 it is due.", sources)
    assert (found["source"], found["run_id"]) == ("data", 7)


def test_a_date_with_a_part_backed_by_the_person_is_person():
    sources = [("data", 4, "30"), ("person", None, "2027")]
    [found] = trace("On 2027-06-30 it is due.", sources)
    assert (found["source"], found["run_id"]) == ("person", None)


def test_a_date_with_a_part_nobody_backs_is_none():
    [found] = trace("On 2027-06-30 it is due.", [("data", 4, "2027")])
    assert found["source"] == "none"
