"""SPEC 7.1 (step 5): the `data` label of `trace`: figures that a data summary of the conversation backs."""
import pytest

OUTPUT = {"value": "4132.31", "as_of": None}


def trace(text, sources):
    from harness.calc.provenance import trace as function
    return function(text, sources)


def sources_of(text, sources):
    return [(item["source"], item["run_id"]) for item in trace(text, sources)]




def test_a_figure_only_a_summary_backs_is_data_and_names_the_summary():
    [found] = trace("The files show 4,132.31 a month.", [("data", 4, OUTPUT)])
    assert found == {"text": "4,132.31", "start": 15, "end": 23, "source": "data", "run_id": 4}




def test_a_run_comes_before_data():
    sources = [("data", 4, OUTPUT), ("run", 9, {"inputs": {}, "output": "4132.31"})]
    assert sources_of("4,132.31", sources) == [("run", 9)]










def test_a_figure_no_summary_backs_is_none():
    assert sources_of("4,200", [("data", 4, OUTPUT)]) == [("none", None)]












