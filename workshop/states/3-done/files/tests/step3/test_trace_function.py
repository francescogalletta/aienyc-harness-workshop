"""SPEC 7.1: `trace` says where each number and date of a text came from."""
import itertools
import json

import pytest

LABELS = ("run", "input", "note", "brief", "person", "today")


def trace(text, sources):
    from harness.calc.provenance import trace as function
    return function(text, sources)


def item(text, source, run_id=None, *, within=None, start=None):
    """The expected item. `start` defaults to the first place `text` is written in `within`."""
    if start is None:
        start = within.index(text)
    return {"text": text, "start": start, "end": start + len(text), "source": source, "run_id": run_id}


def brief_of(*pairs):
    """[(label, ref, value)] from (label, value) or (label, ref, value) tuples."""
    return [pair if len(pair) == 3 else (pair[0], None, pair[1]) for pair in pairs]


# ---- the constants ------------------------------------------------------------------------------------

def test_the_labels_and_their_order(provenance):
    assert provenance.SOURCE_LABELS == LABELS
    assert (provenance.SMALL_LABEL, provenance.NONE_LABEL) == ("small", "none")


def test_the_existing_small_stays(provenance):
    assert provenance.SMALL == 12


# ---- the shape --------------------------------------------------------------------------------------------

def test_no_numbers_gives_nothing():
    assert trace("", []) == []
    assert trace("No numbers here at all.", [("run", 1, "2000")]) == []


def test_one_item_per_number_with_its_place_and_source():
    text = "You will have 4,583.33 left."
    assert trace(text, [("run", 3, {"inputs": {}, "output": "4583.333"})]) == [
        {"text": "4,583.33", "start": 14, "end": 22, "source": "run", "run_id": 3}]
    assert text[14:22] == "4,583.33"


def test_the_keys_of_an_item_and_their_order():
    [found] = trace("Only 2,000.", [("run", 1, "2000")])
    assert list(found) == ["text", "start", "end", "source", "run_id"]


def test_text_start_and_end_are_the_place_in_the_text():
    text = "Pay 3,000 now, 1,250.50 later, 4.6k in all, 50% down, $1,200 and €5.50."
    found = trace(text, [])
    assert [f["text"] for f in found] == ["3,000", "1,250.50", "4.6k", "50%", "$1,200", "€5.50"]
    for f in found:
        assert text[f["start"]:f["end"]] == f["text"]
    assert [f["start"] for f in found] == sorted(f["start"] for f in found)


def test_the_text_of_an_item_keeps_its_sign_its_suffix_and_its_percent():
    found = trace("A 12.5% rate, $9,999, £7.5, 4K.", [])
    assert [f["text"] for f in found] == ["12.5%", "$9,999", "£7.5", "4K"]


def test_a_minus_sign_is_not_part_of_the_item():
    text = "Short by -1,500 or -7.5k."
    found = trace(text, [])
    assert [f["text"] for f in found] == ["1,500", "7.5k"]
    assert text[found[0]["start"] - 1] == "-"


def test_every_occurrence_is_an_item_not_once_per_value():
    text = "2,000 and again 2,000, then 2,000."
    found = trace(text, [("run", 4, "2000")])
    assert len(found) == 3 and len({f["start"] for f in found}) == 3
    assert all(f["source"] == "run" and f["run_id"] == 4 for f in found)


def test_the_sources_are_not_changed():
    sources = [("run", 1, {"output": "2000"}), ("person", None, "I have 500")]
    before = json.dumps(sources)
    trace("2,000 and 500", sources)
    assert json.dumps(sources) == before


def test_offsets_count_code_points():
    text = "😀 café é costs 2,000 😀 and 3,000"
    found = trace(text, [])
    assert [(f["text"], text[f["start"]:f["end"]]) for f in found] == [("2,000", "2,000"), ("3,000", "3,000")]
    assert found[0]["start"] == text.index("2,000")


@pytest.mark.parametrize("text", ["step s1 of the plan", "the 1st payment", "the 3rd of May", "group a99", "x2y"])
def test_a_number_glued_to_a_letter_is_not_read(text):
    assert trace(text, []) == []


# ---- source: each label on its own ----------------------------------------------------------------------------------

@pytest.mark.parametrize("label", LABELS)
def test_each_label_backs_a_number(label):
    ref = 7 if label == "run" else None
    [found] = trace("It is 4,583.33.", [(label, ref, "4583.333")])
    assert (found["source"], found["run_id"]) == (label, ref)


@pytest.mark.parametrize("label", LABELS)
def test_a_number_that_no_source_backs_is_none(label):
    ref = 7 if label == "run" else None
    [found] = trace("It is 4,583.33.", [(label, ref, "9999")])
    assert (found["source"], found["run_id"]) == ("none", None)
    assert trace("It is 4,583.33.", []) == [item("4,583.33", "none", within="It is 4,583.33.")]


def test_a_run_id_is_given_only_for_a_run():
    found = trace("5,000 and 6,000", [("run", 9, "5000"), ("input", None, "6000")])
    assert [(f["source"], f["run_id"]) for f in found] == [("run", 9), ("input", None)]


# ---- the order of the labels ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("earlier, later", list(itertools.combinations(LABELS, 2)))
def test_the_first_label_in_the_order_wins(earlier, later):
    sources = [(later, None, "2000"), (earlier, 5 if earlier == "run" else None, "2000")]       # listed in reverse
    [found] = trace("2,000", sources)
    assert found["source"] == earlier
    assert found["run_id"] == (5 if earlier == "run" else None)


def test_all_six_back_it_and_the_run_wins():
    sources = [(label, 2 if label == "run" else None, "2000") for label in reversed(LABELS)]
    [found] = trace("2,000", sources)
    assert (found["source"], found["run_id"]) == ("run", 2)


def test_each_number_is_labelled_on_its_own():
    text = "run 2,000 input 4,500 note 6,500 brief 7,500 person 8,500 nobody 9,999"
    sources = brief_of(("run", 5, {"inputs": {"a": "2000"}, "output": "2000"}), ("input", "4500"), ("note", "6500"),
                       ("brief", {"goal": "save 7,500"}), ("person", "I have 8,500"))
    found = trace(text, sources)
    assert [(f["text"], f["source"], f["run_id"]) for f in found] == [
        ("2,000", "run", 5), ("4,500", "input", None), ("6,500", "note", None), ("7,500", "brief", None),
        ("8,500", "person", None), ("9,999", "none", None)]


# ---- the run id: the last source in the list that backs it ---------------------------------------------------------------

def test_the_run_id_is_the_ref_of_the_last_backing_source_in_the_list():
    sources = [("run", 1, "2000"), ("run", 2, "2000"), ("run", 3, "7")]
    assert trace("2,000", sources)[0]["run_id"] == 2


def test_last_in_the_list_is_not_the_same_as_the_highest_id():
    sources = [("run", 5, "2000"), ("run", 3, "2000")]
    assert trace("2,000", sources)[0]["run_id"] == 3


def test_a_run_that_does_not_back_it_is_passed_over():
    sources = [("run", 1, "2000"), ("run", 2, "9999"), ("person", None, "2000")]
    [found] = trace("2,000", sources)
    assert (found["source"], found["run_id"]) == ("run", 1)


def test_other_labels_between_the_runs_do_not_matter():
    sources = [("run", 1, "2000"), ("input", None, "2000"), ("run", 2, "2000"), ("today", None, "2000")]
    assert trace("2,000", sources)[0]["run_id"] == 2


# ---- what a source holds ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "rent 2000", {"output": "2000"}, [1, "2000"], 2000, {"inputs": {"a": {"b": ["2000"]}}}, '"2000"', 2000.0])
def test_a_value_is_read_as_text_or_as_json(value):
    assert trace("2,000", [("input", None, value)])[0]["source"] == "input"


def test_a_value_that_is_not_text_is_turned_into_json_without_escaping_non_ascii():
    assert trace("2,000", [("note", None, {"name": "café", "amount": "2000"})])[0]["source"] == "note"
    assert trace("2,001", [("note", None, {"amount": "2000"})])[0]["source"] == "none"


def test_a_source_that_is_text_is_read_as_it_is():
    assert trace("2,000", [("person", None, "I have 2,000 in cash")])[0]["source"] == "person"


# ---- small numbers --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("written", ["0", "1", "7", "12"])
def test_a_bare_whole_number_up_to_12_is_small_with_no_source(written):
    text = f"There are {written} left."
    assert trace(text, []) == [item(written, "small", within=text)]


def test_small_wins_even_when_a_source_has_the_number():
    sources = [("run", 1, "5"), ("person", None, "5")]
    assert trace("5 payments", sources) == [item("5", "small", within="5 payments")]


def test_13_is_not_small():
    assert trace("13 months", [])[0]["source"] == "none"
    assert trace("13 months", [("person", None, "13")])[0]["source"] == "person"


@pytest.mark.parametrize("written", ["$5", "€5", "£12", "5.0", "5.5", "5k", "5K", "5%"])
def test_a_small_number_that_is_not_bare_is_looked_up(written):
    assert trace(f"It is {written}.", [])[0]["source"] == "none"


def test_a_small_number_that_is_not_bare_is_labelled_by_its_source():
    assert trace("It is 5.0.", [("note", None, "about 5")])[0]["source"] == "note"
    assert trace("It is 5%.", [("brief", None, "a rate of 0.05")])[0]["source"] == "brief"
    assert trace("It is $5.", [("person", None, "I have 5")])[0]["source"] == "person"


# ---- precision --------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("written, source", [
    ("4,583", "run"), ("4,584", "none"), ("4,583.3", "run"), ("4,583.4", "none"), ("4,583.33", "run"),
    ("4,583.34", "none"), ("4.6k", "run"), ("4.7k", "none"), ("5k", "run"), ("6k", "none"), ("5K", "run"),
    ("4,600", "none")])
def test_a_number_is_backed_within_half_its_precision(written, source):
    [found] = trace(f"It is {written}.", [("run", 1, {"output": "4583.333"})])
    assert found["source"] == source


@pytest.mark.parametrize("text, value, source", [
    ("50%", "0.5", "input"), ("0.5", "a rate of 50%", "input"), ("50", "a rate of 50%", "input"),
    ("12.5%", "0.125", "input"), ("12.5%", "12.5", "input"), ("12.5%", "0.13", "none"), ("12.5%", "0.12", "none"),
    ("25%", "25", "input"), ("25%", "0.25", "input")])
def test_a_percentage_matches_its_value_or_its_value_over_100(text, value, source):
    [found] = trace(text, [("input", None, value)])
    assert found["source"] == source


# ---- dates ----------------------------------------------------------------------------------------------------------------------------

def test_a_date_is_one_item_with_its_place():
    text = "On 2026-03-14 I paid."
    assert trace(text, [("today", None, "2026-03-14")]) == [
        {"text": "2026-03-14", "start": 3, "end": 13, "source": "today", "run_id": None}]


def test_the_parts_of_a_date_are_not_read_again_as_numbers():
    assert len(trace("2026-03-14 and 2026-03-14", [])) == 2


def test_dates_and_numbers_come_in_order_of_appearance():
    text = "Pay 3,000 on 2026-03-14 or 500, then 2026-04-02 or $40."
    found = trace(text, [])
    assert [f["text"] for f in found] == ["3,000", "2026-03-14", "500", "2026-04-02", "$40"]
    for f in found:
        assert text[f["start"]:f["end"]] == f["text"]


def test_a_date_whose_labelled_parts_are_all_backed_by_the_same_label():
    [found] = trace("2026-03-14", [("today", None, "2026-03-14")])
    assert (found["source"], found["run_id"]) == ("today", None)


def test_a_date_takes_the_label_that_comes_last_in_the_order():
    sources = [("brief", None, "year 2026"), ("person", None, "day 14")]
    assert trace("2026-03-14", sources)[0]["source"] == "person"
    assert trace("2026-03-14", sources[::-1])[0]["source"] == "person"
    sources = [("run", 2, "2026"), ("today", None, "14")]
    assert trace("2026-03-14", sources)[0]["source"] == "today"
    sources = [("person", None, "2026"), ("note", None, "14")]
    assert trace("2026-03-14", sources)[0]["source"] == "person"


def test_a_date_s_run_id_is_that_of_the_first_part_with_that_label():
    [found] = trace("2026-03-14", [("run", 4, "2026"), ("run", 7, "14")])
    assert (found["source"], found["run_id"]) == ("run", 4)
    [found] = trace("2026-03-14", [("run", 7, "2026"), ("run", 4, "14")])
    assert (found["source"], found["run_id"]) == ("run", 7)
    [found] = trace("2026-03-14", [("input", None, "2026"), ("run", 4, "14")])      # the year is input, the day is run
    assert (found["source"], found["run_id"]) == ("input", None)


def test_a_date_with_a_month_and_a_day_above_12():
    [found] = trace("2026-13-14", [("run", 4, "2026 13"), ("run", 8, "14")])
    assert (found["source"], found["run_id"]) == ("run", 4)
    [found] = trace("2026-13-14", [("today", None, "2026-03-14")])               # 13 is nobody's
    assert found["source"] == "none"


def test_parts_of_12_or_less_are_not_looked_at():
    for text in ("2026-03-05", "2026-12-12", "2026-01-09"):
        assert trace(text, [("brief", None, "year 2026")])[0]["source"] == "brief"


def test_a_date_with_a_labelled_part_that_nothing_backs_is_none():
    assert trace("2026-03-14", [("person", None, "day 14")])[0]["source"] == "none"        # the year
    assert trace("2026-03-14", [("person", None, "year 2026")])[0]["source"] == "none"     # the day
    assert trace("2026-03-14", [])[0] == item("2026-03-14", "none", within="2026-03-14")
    [found] = trace("2026-03-14", [("run", 3, "2026")])
    assert (found["source"], found["run_id"]) == ("none", None)


def test_a_date_with_small_parts_only_needs_its_year():
    assert trace("2026-03-05", [])[0]["source"] == "none"
    [found] = trace("2026-03-05", [("run", 6, "2026")])
    assert (found["source"], found["run_id"]) == ("run", 6)


def test_every_part_of_a_date_in_a_source_is_known():
    sources = [("today", None, "the date is 2026-03-14")]
    found = trace("in 2026, 14 payments", sources)
    assert [(f["text"], f["source"]) for f in found] == [("2026", "today"), ("14", "today")]


# ---- what none means --------------------------------------------------------------------------------------------------------------------

TEXTS = [
    ("You keep 2,000 a month, or 3,500.50 after 12 months, $450 and 7.5% of 9,999.", [
        ("run", 1, {"inputs": {"a": "5000"}, "output": "2000"}), ("input", None, "450"), ("person", None, "I have 3,500.5")]),
    ("A 4.6k loan at 12.5% over 24 months, then 1,234,567.", [("note", None, "4583.333"), ("brief", None, "a rate of 0.125")]),
    ("Nothing is known: 99, 13, 14.5, 2k and 3%.", []),
    ("50% of 4,000 is 2,000 and 4,000 again.", [("person", None, "I save 4000"), ("run", 2, "0.5")]),
    ("The 1st and 2nd of 15 and 16 are 17.", [("person", None, "15")]),
]


@pytest.mark.parametrize("text, sources", TEXTS)
def test_the_none_items_are_the_numbers_that_unbacked_returns(text, sources):
    from harness.calc.provenance import unbacked
    values = [value if isinstance(value, str) else json.dumps(value, ensure_ascii=False) for _, _, value in sources]
    unknown = []
    for f in trace(text, sources):
        if f["source"] == "none" and f["text"] not in unknown:
            unknown.append(f["text"])
    assert unknown == unbacked(text, values)


@pytest.mark.parametrize("text, sources", TEXTS)
def test_every_item_has_a_label_a_place_and_a_run_id_only_for_a_run(text, sources):
    for f in trace(text, sources):
        assert f["source"] in (*LABELS, "small", "none")
        assert text[f["start"]:f["end"]] == f["text"]
        assert (f["run_id"] is not None) == (f["source"] == "run")
