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


def test_a_full_ask_scenario_and_a_full_build_scenario_are_valid(replay):
    assert validate(replay, ask()) == []
    assert validate(replay, build()) == []


# ---- stage 1 -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [[], "scenario"])
def test_a_scenario_that_is_not_an_object(replay, value):
    assert validate(replay, value) == ["the scenario must be an object"]


def test_missing_keys_one_per_key_in_the_order_name_kind_lines_expect(replay):
    assert validate(replay, {}) == ["missing: name", "missing: kind", "missing: lines", "missing: expect"]
    assert validate(replay, {"kind": "ask", "expect": {}}) == ["missing: name", "missing: lines"]
    assert validate(replay, {"name": "upfront", "lines": ["x"]}) == ["missing: kind", "missing: expect"]
    for key in ("name", "kind", "lines", "expect"):
        assert validate(replay, ask(**{key: DELETE})) == [f"missing: {key}"]


# ---- stage 2: the keys -------------------------------------------------------------------------------------------------


def test_the_name_must_be_the_stem(replay):
    message = "name must be the file name without .json, in snake_case: 'upfront'"
    assert validate(replay, ask(name="other")) == [message]
    assert validate(replay, ask(name="Upfront")) == [message]
    assert validate(replay, ask(name=5)) == [message]
    assert validate(replay, ask(name=None)) == [message]


@pytest.mark.parametrize("kind", ["tell"])
def test_the_kind_is_ask_or_build(replay, kind):
    # What else is said about a scenario of no kind (the keys of expect) is not in the contract: only the first line is.
    errors = validate(replay, ask(kind=kind, today=DELETE))
    assert errors[0] == "kind must be ask or build"


@pytest.mark.parametrize("today", ["tomorrow"])
def test_today_must_be_a_date_written_yyyy_mm_dd(replay, today):
    assert validate(replay, ask(today=today)) == ["today must be a date written YYYY-MM-DD"]


def test_each_item_of_without_must_be_a_calculation_step_of_the_brief(replay):
    assert validate(replay, build(without=["s1", "s3"])) == []
    assert validate(replay, build(without=[])) == []
    assert validate(replay, build(without=["ghost"])) == ["without: 'ghost' is not a calculation step of the brief"]
    assert validate(replay, build(without=["s2"])) == ["without: 's2' is not a calculation step of the brief"]
    assert validate(replay, build(without=["s1", "ghost", "s2", "added_1"])) == [
        "without: 'ghost' is not a calculation step of the brief",
        "without: 's2' is not a calculation step of the brief",
        "without: 'added_1' is not a calculation step of the brief"]


@pytest.mark.parametrize("lines", [[]])
def test_lines_must_be_a_non_empty_list_of_non_empty_strings(replay, lines):
    assert validate(replay, ask(lines=lines)) == ["lines must be a non-empty list of non-empty strings"]


# ---- stage 2: expect ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key, value", [("runs", [{"module": "m"}]), ("shown", ["4,650"])])
def test_an_ask_key_in_a_build_scenario(replay, key, value):
    assert validate(replay, build(expect={key: value, "steps": {"s1": "built"}})) == [
        f"expect.{key} is only for ask scenarios"]


@pytest.mark.parametrize("entry", ["m"])
def test_a_runs_entry_must_be_an_object_with_a_module_and_optional_inputs(replay, entry):
    assert validate(replay, with_expect(runs=[entry])) == [
        "expect.runs: entry 1 must be an object with module and, optionally, inputs"]


@pytest.mark.parametrize("key", ["shown"])
@pytest.mark.parametrize("item", ["twelve"])
def test_an_item_must_be_one_number_not_a_date_and_not_a_small_bare_whole_number(replay, key, item):
    assert validate(replay, with_expect(**{key: [item]})) == [NUMBER_MESSAGE.format(key=key, item=item)]


@pytest.mark.parametrize("outcome", ["done"])
def test_a_value_of_steps_is_one_of_the_four_outcomes(replay, outcome):
    assert validate(replay, with_expect("build", steps={"s1": outcome})) == [
        "expect.steps: 's1' must be built, reused, kept or not_built"]


# ---- the order of the rules ------------------------------------------------------------------------------------------------------
