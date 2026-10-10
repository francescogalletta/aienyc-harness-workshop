"""SPEC 6.4: `validate_scenario`, every rule and every message, in order."""
import pytest

import step3_helpers as s3
from step3_helpers import h

DELETE = object()
NUMBER_MESSAGE = ("expect.{key}: '{item}' must be one number the number check reads, not a date and not a bare "
                  "whole number from 0 to 12")


def validate(replay, value, stem="upfront", brief=None):
    return replay.validate_scenario(value, stem=stem, brief=brief or h.make_brief())


def ask(**changes):
    scenario = s3.ask_scenario("upfront")
    for key, value in changes.items():
        if value is DELETE:
            scenario.pop(key, None)
        else:
            scenario[key] = value
    return scenario


def build(**changes):
    scenario = s3.build_scenario("upfront")
    for key, value in changes.items():
        if value is DELETE:
            scenario.pop(key, None)
        else:
            scenario[key] = value
    return scenario


def with_expect(kind="ask", **expect):
    return (ask if kind == "ask" else build)(expect=expect)


# ---- scenarios that are fine --------------------------------------------------------------------------------

def test_the_example_of_the_spec_is_valid(replay):
    scenario = {"name": "upfront_cost", "kind": "ask", "today": "2026-10-09",
                "lines": ["How much do I need before the move? Deposit 2,000, van 450, two months of overlap at 1,100."],
                "expect": {"runs": [{"module": "upfront_cost", "inputs": {"deposit": "2000"}}],
                           "shown": ["4,650"], "max_withheld": 0}}
    assert validate(replay, scenario, stem="upfront_cost") == []


def test_a_full_ask_scenario_and_a_full_build_scenario_are_valid(replay):
    assert validate(replay, ask()) == []
    assert validate(replay, build()) == []


def test_the_smallest_scenarios_are_valid(replay):
    assert validate(replay, {"name": "upfront", "kind": "ask", "lines": ["Hello"], "expect": {"max_withheld": 0}}) == []
    assert validate(replay, {"name": "upfront", "kind": "build", "lines": ["/quit"],
                             "expect": {"steps": {"s1": "built"}}}) == []


@pytest.mark.parametrize("expect", [
    {"runs": [{"module": "m"}]}, {"runs": [{"module": "m", "inputs": {}}]}, {"runs": [{"module": "m", "inputs": {"a": 1}}]},
    {"runs": []}, {"shown": []}, {"not_shown": []}, {"shown": ["4,650"]}, {"not_shown": ["4.6k", "50%"]},
    {"shown": ["13", "$7", "7.0", "7k", "7%", "1,234,567", "0.5", " 4,650 "]},
    {"max_withheld": 0}, {"max_corrections": 3}, {"max_withheld": 0, "max_corrections": 0},
    {"runs": [{"module": "m"}], "shown": ["2,000"], "not_shown": ["9,999"], "max_withheld": 1, "max_corrections": 2}])
def test_ask_expectations_that_are_fine(replay, expect):
    assert validate(replay, with_expect("ask", **expect)) == []


@pytest.mark.parametrize("steps", [{"s1": "built"}, {"s3": "reused", "s1": "kept"}, {"s1": "not_built"},
                                   {"added_1": "built"}, {"added_9": "not_built", "s3": "kept"}, {}])
def test_build_expectations_that_are_fine(replay, steps):
    assert validate(replay, with_expect("build", steps=steps)) == []


def test_the_scenario_is_not_changed(replay):
    scenario = ask(without=["s1"])
    before = repr(scenario)
    validate(replay, scenario)
    assert repr(scenario) == before


# ---- stage 1 -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [[], "scenario", None, 5, 1.5, True, [{"name": "x"}]])
def test_a_scenario_that_is_not_an_object(replay, value):
    assert validate(replay, value) == ["the scenario must be an object"]


def test_missing_keys_one_per_key_in_the_order_name_kind_lines_expect(replay):
    assert validate(replay, {}) == ["missing: name", "missing: kind", "missing: lines", "missing: expect"]
    assert validate(replay, {"kind": "ask", "expect": {}}) == ["missing: name", "missing: lines"]
    assert validate(replay, {"name": "upfront", "lines": ["x"]}) == ["missing: kind", "missing: expect"]
    for key in ("name", "kind", "lines", "expect"):
        assert validate(replay, ask(**{key: DELETE})) == [f"missing: {key}"]


def test_a_stage_that_finds_errors_returns_them_without_running_the_next(replay):
    errors = validate(replay, {"extra": 1, "kind": "wrong"})
    assert errors == ["missing: name", "missing: lines", "missing: expect"]


# ---- stage 2: the keys -------------------------------------------------------------------------------------------------

def test_unknown_keys_one_per_key_in_the_order_given(replay):
    scenario = ask()
    scenario["zeta"] = 1
    scenario["alpha"] = 2
    assert validate(replay, scenario) == ["unknown key: zeta", "unknown key: alpha"]


def test_the_name_must_be_the_stem(replay):
    message = "name must be the file name without .json, in snake_case: 'upfront'"
    assert validate(replay, ask(name="other")) == [message]
    assert validate(replay, ask(name="Upfront")) == [message]
    assert validate(replay, ask(name=5)) == [message]
    assert validate(replay, ask(name=None)) == [message]


@pytest.mark.parametrize("stem", ["Bad-Stem", "9lives", "has space", "", "_underscore", "Capital"])
def test_a_stem_that_is_not_snake_case_is_refused_even_when_the_name_is_the_same(replay, stem):
    assert validate(replay, ask(name=stem), stem=stem) == [
        f"name must be the file name without .json, in snake_case: '{stem}'"]


@pytest.mark.parametrize("stem", ["a", "upfront", "rent_2", "a1_b2_c3"])
def test_a_stem_in_snake_case_is_fine(replay, stem):
    assert validate(replay, ask(name=stem), stem=stem) == []


@pytest.mark.parametrize("kind", ["Ask", "tell", "", None, 5, ["ask"]])
def test_the_kind_is_ask_or_build(replay, kind):
    # What else is said about a scenario of no kind (the keys of expect) is not in the contract: only the first line is.
    errors = validate(replay, ask(kind=kind, today=DELETE))
    assert errors[0] == "kind must be ask or build"


@pytest.mark.parametrize("description", [5, None, ["x"], {"a": 1}, True])
def test_the_description_must_be_a_string(replay, description):
    assert validate(replay, ask(description=description)) == ["description must be a string"]


def test_the_description_may_be_left_out_or_empty(replay):
    assert validate(replay, ask(description=DELETE)) == []
    assert validate(replay, ask(description="")) == []


def test_today_is_for_ask_scenarios_only(replay):
    assert validate(replay, build(today="2026-03-14")) == ["today is only for ask scenarios"]
    assert validate(replay, ask(today=DELETE)) == []


@pytest.mark.parametrize("today", ["2026-13-01", "2026-02-30", "2026-3-1", "tomorrow", "20260314", "14/03/2026",
                                   "2026-03-14T00:00", "", 20260314, None, ["2026-03-14"], "2026-03-14 "])
def test_today_must_be_a_date_written_yyyy_mm_dd(replay, today):
    assert validate(replay, ask(today=today)) == ["today must be a date written YYYY-MM-DD"]


@pytest.mark.parametrize("today", ["2026-03-14", "2000-02-29", "2031-07-22"])
def test_a_valid_today(replay, today):
    assert validate(replay, ask(today=today)) == []


@pytest.mark.parametrize("without", ["s1", ["s1", 5], [1], {"s1": 1}, None, 5, "s1,s3"])
def test_without_must_be_a_list_of_strings(replay, without):
    assert validate(replay, build(without=without)) == ["without must be a list of step ids"]


def test_each_item_of_without_must_be_a_calculation_step_of_the_brief(replay):
    assert validate(replay, build(without=["s1", "s3"])) == []
    assert validate(replay, build(without=[])) == []
    assert validate(replay, build(without=["ghost"])) == ["without: 'ghost' is not a calculation step of the brief"]
    assert validate(replay, build(without=["s2"])) == ["without: 's2' is not a calculation step of the brief"]
    assert validate(replay, build(without=["s1", "ghost", "s2", "added_1"])) == [
        "without: 'ghost' is not a calculation step of the brief",
        "without: 's2' is not a calculation step of the brief",
        "without: 'added_1' is not a calculation step of the brief"]


def test_without_is_allowed_in_an_ask_scenario_too(replay):
    assert validate(replay, ask(without=["s1"])) == []
    assert validate(replay, ask(without=["ghost"])) == ["without: 'ghost' is not a calculation step of the brief"]


def test_without_is_checked_against_the_brief_given(replay):
    other = h.make_brief(process=[{**h.make_brief()["process"][0], "id": "only_one"}])
    assert validate(replay, build(without=["only_one"], expect={"steps": {"only_one": "built"}}), brief=other) == []
    assert validate(replay, build(without=["s1"]), brief=other) == [
        "without: 's1' is not a calculation step of the brief",
        "expect.steps: 's1' is not a calculation step of the brief", "expect.steps: 's3' is not a calculation step of the brief"]


@pytest.mark.parametrize("lines", [[], "text", None, 5, [""], ["  "], ["ok", ""], ["ok", 5], [None], ["\n"], {"a": "b"}])
def test_lines_must_be_a_non_empty_list_of_non_empty_strings(replay, lines):
    assert validate(replay, ask(lines=lines)) == ["lines must be a non-empty list of non-empty strings"]


def test_lines_with_text_are_fine(replay):
    assert validate(replay, ask(lines=["yes", " /accept ", "A longer line, with 1,000 in it."])) == []


# ---- stage 2: expect ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("expect", [[], "runs", None, 5, [{"runs": []}]])
def test_expect_must_be_an_object_and_nothing_more_is_checked(replay, expect):
    assert validate(replay, ask(expect=expect)) == ["expect must be an object"]


def test_expect_must_not_be_empty(replay):
    assert validate(replay, ask(expect={})) == ["expect must hold at least one expectation"]


def test_unknown_keys_of_expect(replay):
    assert validate(replay, ask(expect={"max_withheld": 0, "wording": "x", "tone": 1})) == [
        "expect: unknown key: wording", "expect: unknown key: tone"]


@pytest.mark.parametrize("key, value", [("runs", [{"module": "m"}]), ("shown", ["4,650"]), ("not_shown", ["4,650"]),
                                        ("max_withheld", 0), ("max_corrections", 0),
                                        ("decisions", [{"kind": "judgment"}]), ("asides", {"opened": 1})])
def test_an_ask_key_in_a_build_scenario(replay, key, value):
    assert validate(replay, build(expect={key: value, "steps": {"s1": "built"}})) == [
        f"expect.{key} is only for ask scenarios"]


def test_the_steps_key_in_an_ask_scenario(replay):
    assert validate(replay, ask(expect={"steps": {"s1": "built"}})) == ["expect.steps is only for build scenarios"]
    assert validate(replay, ask(expect={"max_withheld": 0, "steps": {}})) == ["expect.steps is only for build scenarios"]


def test_runs_must_be_a_list(replay):
    for value in ("m", {"module": "m"}, None, 5):
        assert validate(replay, with_expect(runs=value)) == ["expect.runs must be a list"]


@pytest.mark.parametrize("entry", ["m", 5, None, [], {}, {"inputs": {}}, {"module": ""}, {"module": 5}, {"module": None},
                                   {"module": "m", "inputs": []}, {"module": "m", "inputs": "a"},
                                   {"module": "m", "inputs": None}, {"module": "m", "extra": 1},
                                   {"module": "m", "inputs": {}, "note": "x"}])
def test_a_runs_entry_must_be_an_object_with_a_module_and_optional_inputs(replay, entry):
    assert validate(replay, with_expect(runs=[entry])) == [
        "expect.runs: entry 1 must be an object with module and, optionally, inputs"]


def test_entries_are_numbered_from_1(replay):
    good = {"module": "m", "inputs": {"a": "1"}}
    assert validate(replay, with_expect(runs=[good, "bad", good, {"module": ""}])) == [
        "expect.runs: entry 2 must be an object with module and, optionally, inputs",
        "expect.runs: entry 4 must be an object with module and, optionally, inputs"]


@pytest.mark.parametrize("key", ["shown", "not_shown"])
@pytest.mark.parametrize("value", ["4,650", [4650], [None], {"a": "4,650"}, None, 5, ["4,650", 5]])
def test_shown_and_not_shown_must_be_lists_of_text(replay, key, value):
    errors = validate(replay, with_expect(**{key: value}))
    assert errors and errors[0] == f"expect.{key} must be a list of numbers written as text"


@pytest.mark.parametrize("key", ["shown", "not_shown"])
@pytest.mark.parametrize("item", ["twelve", "4,650 and 100", "4,650 4,651", "2026-03-14", "7", "0", "12", "abc", "",
                                  "  ", "-5", "+5", "1st", "about 4,650", "4,650.", "(4,650)", "5 percent", "1/2"])
def test_an_item_must_be_one_number_not_a_date_and_not_a_small_bare_whole_number(replay, key, item):
    assert validate(replay, with_expect(**{key: [item]})) == [NUMBER_MESSAGE.format(key=key, item=item)]


def test_the_items_are_checked_one_by_one_in_order(replay):
    assert validate(replay, with_expect(shown=["4,650", "twelve", "9", "2,000"], not_shown=["x"])) == [
        NUMBER_MESSAGE.format(key="shown", item="twelve"), NUMBER_MESSAGE.format(key="shown", item="9"),
        NUMBER_MESSAGE.format(key="not_shown", item="x")]


@pytest.mark.parametrize("key", ["max_withheld", "max_corrections"])
@pytest.mark.parametrize("value", [-1, 1.5, "1", True, False, None, [], 1.0, "0", {"n": 1}])
def test_the_limits_are_whole_numbers_of_0_or_more(replay, key, value):
    assert validate(replay, with_expect(**{key: value})) == [f"expect.{key} must be a whole number, 0 or more"]


@pytest.mark.parametrize("key", ["max_withheld", "max_corrections"])
@pytest.mark.parametrize("value", [0, 1, 25])
def test_a_limit_that_is_fine(replay, key, value):
    assert validate(replay, with_expect(**{key: value})) == []


@pytest.mark.parametrize("value", [[], "built", None, 5, [{"s1": "built"}]])
def test_steps_must_be_an_object(replay, value):
    assert validate(replay, with_expect("build", steps=value)) == ["expect.steps must be an object"]


@pytest.mark.parametrize("step", ["s2", "ghost", "added", "S1", "", "xadded_1"])
def test_a_key_of_steps_must_be_a_calculation_step_or_an_added_id(replay, step):
    assert validate(replay, with_expect("build", steps={step: "built"})) == [
        f"expect.steps: '{step}' is not a calculation step of the brief"]


@pytest.mark.parametrize("outcome", ["done", "BUILT", "", None, 5, True, ["built"], "not built", "already built"])
def test_a_value_of_steps_is_one_of_the_four_outcomes(replay, outcome):
    assert validate(replay, with_expect("build", steps={"s1": outcome})) == [
        "expect.steps: 's1' must be built, reused, kept or not_built"]


def test_the_keys_of_steps_are_checked_before_their_values_each_in_order(replay):
    """The two rules come one after the other in the table of 6.4: every bad key, then every bad value."""
    errors = validate(replay, with_expect("build", steps={"s1": "done", "s3": "kept", "ghost": "built", "s2": "built",
                                                          "added_2": "oops"}))
    assert errors == ["expect.steps: 'ghost' is not a calculation step of the brief",
                      "expect.steps: 's2' is not a calculation step of the brief",
                      "expect.steps: 's1' must be built, reused, kept or not_built",
                      "expect.steps: 'added_2' must be built, reused, kept or not_built"]


# ---- the order of the rules ------------------------------------------------------------------------------------------------------

def test_the_rules_of_stage_2_report_in_the_order_of_the_table(replay):
    scenario = {"name": "wrong", "kind": "ask", "description": 5, "today": "soon", "without": "s1", "lines": [],
                "expect": {}, "extra": 1}
    assert validate(replay, scenario) == [
        "unknown key: extra",
        "name must be the file name without .json, in snake_case: 'upfront'",
        "description must be a string",
        "today must be a date written YYYY-MM-DD",
        "without must be a list of step ids",
        "lines must be a non-empty list of non-empty strings",
        "expect must hold at least one expectation"]


def test_a_scenario_full_of_nonsense_gives_errors_and_never_raises(replay):
    errors = validate(replay, {"name": None, "kind": None, "lines": None, "expect": None, "today": None,
                               "without": None, "description": None})
    assert isinstance(errors, list) and errors and all(isinstance(e, str) for e in errors)
