"""SPEC 7.1: `trace` says where each number and date of a text came from."""
import itertools

import pytest

LABELS = ("run", "input", "note", "brief", "person", "today")      # the labels of step 3, in their order (later steps add more)


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


# ---- the shape --------------------------------------------------------------------------------------------


def test_one_item_per_number_with_its_place_and_source():
    text = "You will have 4,583.33 left."
    assert trace(text, [("run", 3, {"inputs": {}, "output": "4583.333"})]) == [
        {"text": "4,583.33", "start": 14, "end": 22, "source": "run", "run_id": 3}]
    assert text[14:22] == "4,583.33"


# ---- source: each label on its own ----------------------------------------------------------------------------------

def test_each_label_backs_a_number():
    for label in LABELS:
        ref = 7 if label == "run" else None
        [found] = trace("It is 4,583.33.", [(label, ref, "4583.333")])
        assert (found["source"], found["run_id"]) == (label, ref)


# ---- the order of the labels ------------------------------------------------------------------------------------------

def test_the_first_label_in_the_order_wins():
    for earlier, later in itertools.combinations(LABELS, 2):
        sources = [(later, None, "2000"), (earlier, 5 if earlier == "run" else None, "2000")]       # listed in reverse
        [found] = trace("2,000", sources)
        assert found["source"] == earlier
        assert found["run_id"] == (5 if earlier == "run" else None)


# ---- the run id: the last source in the list that backs it ---------------------------------------------------------------


# ---- what a source holds ----------------------------------------------------------------------------------------------------


# ---- small numbers --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("written", ["12"])
def test_a_bare_whole_number_up_to_12_is_small_with_no_source(written):
    text = f"There are {written} left."
    assert trace(text, []) == [item(written, "small", within=text)]


# ---- precision --------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("written, source", [("4,583", "run"), ("4,584", "none"), ("4.6k", "run"), ("4,600", "none")])
def test_a_number_is_backed_within_half_its_precision(written, source):
    [found] = trace(f"It is {written}.", [("run", 1, {"output": "4583.333"})])
    assert found["source"] == source


# ---- dates ----------------------------------------------------------------------------------------------------------------------------

def test_a_date_is_one_item_with_its_place():
    text = "On 2026-03-14 I paid."
    assert trace(text, [("today", None, "2026-03-14")]) == [
        {"text": "2026-03-14", "start": 3, "end": 13, "source": "today", "run_id": None}]


# ---- what none means --------------------------------------------------------------------------------------------------------------------

TEXTS = [
    ("You keep 2,000 a month, or 3,500.50 after 12 months, $450 and 7.5% of 9,999.", [
        ("run", 1, {"inputs": {"a": "5000"}, "output": "2000"}), ("input", None, "450"), ("person", None, "I have 3,500.5")]),
    ("A 4.6k loan at 12.5% over 24 months, then 1,234,567.", [("note", None, "4583.333"), ("brief", None, "a rate of 0.125")]),
    ("Nothing is known: 99, 13, 14.5, 2k and 3%.", []),
    ("50% of 4,000 is 2,000 and 4,000 again.", [("person", None, "I save 4000"), ("run", 2, "0.5")]),
    ("The 1st and 2nd of 15 and 16 are 17.", [("person", None, "15")]),
]
