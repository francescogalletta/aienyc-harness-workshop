"""SPEC 6.1 (step 4) and 8.8: what the data author changes in the seeded examples.

The scenarios of `examples/` were updated after step 4 was implemented; these checks keep them that way.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
NAMES = sorted(p.name for p in EXAMPLES.iterdir() if p.is_dir()) if EXAMPLES.is_dir() else []

DECIDE = "Once you have the results, help me decide what to update first."
KEEP_OR_MOVE = "Then help me decide whether to keep the move date or move it."
YES6 = ["yes"] * 6
FOUR_ASK = [("wedding", "cover_each_payment"), ("wedding", "no_family_contribution"),
            ("moving", "months_at_current_saving"), ("moving", "upfront_and_monthly")]
TWO_BUILD = [("wedding", "build_monthly_surplus"), ("moving", "build_months_to_save")]


def scenario(example, name):
    return json.loads((EXAMPLES / example / "scenarios" / f"{name}.json").read_text(encoding="utf-8"))


def brief_of(example):
    from harness.calc.builder import load_brief
    return load_brief(EXAMPLES / example / "brief")


def scenarios_of(example):
    folder = EXAMPLES / example / "scenarios"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]


# ---- true already --------------------------------------------------------------------------------------------------------------------------

def test_there_are_two_examples():
    assert NAMES == ["moving", "wedding"]


@pytest.mark.parametrize("example", NAMES)
def test_every_scenario_still_loads_and_validates(replay, example):
    scenarios = replay.load_scenarios(EXAMPLES / example, brief_of(example))
    assert scenarios and {s["name"] for s in scenarios} == {p.stem for p in (EXAMPLES / example / "scenarios").glob("*.json")}


@pytest.mark.parametrize("example, name", TWO_BUILD)
def test_the_build_scenarios_have_no_side_conversation_and_no_gate_lines(example, name):
    wanted = scenario(example, name)
    assert wanted["kind"] == "build" and not any(line.startswith("/aside") for line in wanted["lines"])
    assert set(wanted["expect"]) == {"steps"}


# ---- 6.1: what each example ships ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("example", NAMES)
def test_an_example_ships_a_judgment_scenario(example):
    steps = {step["id"]: step["kind"] for step in brief_of(example)["process"]}
    found = [s["name"] for s in scenarios_of(example) if s["kind"] == "ask"
             for entry in s["expect"].get("decisions", [])
             if entry["kind"] == "judgment" and steps.get(entry.get("step")) == "judgment"]
    assert found


@pytest.mark.parametrize("example", NAMES)
def test_an_example_ships_an_aside_scenario(example):
    assert [s["name"] for s in scenarios_of(example) if s["kind"] == "ask" and "asides" in s["expect"]]


# ---- 8.8 rule 1: six yes lines after the first --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("example, name", FOUR_ASK)
def test_the_four_ask_scenarios_have_six_yes_lines_after_the_first(example, name):
    wanted = scenario(example, name)
    assert wanted["kind"] == "ask" and wanted["lines"][1:] == YES6


@pytest.mark.parametrize("example, name", FOUR_ASK)
def test_the_four_ask_scenarios_start_with_a_question_and_have_no_new_expectation(example, name):
    wanted = scenario(example, name)
    assert wanted["lines"][0] and not set(wanted["expect"]) & {"decisions", "asides"}


# ---- 8.8 rule 3: four new scenarios ----------------------------------------------------------------------------------------------------------------------

NEW = [
    ("wedding", "decide_what_to_update", "2027-01-15", ("cover_each_payment", " " + DECIDE),
     {"decisions": [{"kind": "judgment", "step": "s7"}], "max_withheld": 0}),
    ("wedding", "aside_before_asking", "2027-01-15", None,
     {"asides": {"opened": 1, "turns": 1}, "runs": [{"module": "wedding_total_cost"}], "max_withheld": 0}),
    ("moving", "keep_or_move_date", None, ("months_at_current_saving", " " + KEEP_OR_MOVE),
     {"decisions": [{"kind": "judgment", "step": "m4"}], "max_withheld": 0}),
    ("moving", "aside_before_asking", None, None,
     {"asides": {"opened": 1, "turns": 1}, "runs": [{"module": "move_upfront_cost"}], "max_withheld": 0}),
]
ASIDE_OPENING = {"wedding": "/aside What does a running balance mean in my plan?", "moving": "/aside What is a sinking fund?"}
ASIDE_FIRST_LINE = {"wedding": "cover_each_payment", "moving": "upfront_and_monthly"}


@pytest.mark.parametrize("example, name, today, first, expect", NEW)
def test_a_new_scenario_is_as_the_spec_says(example, name, today, first, expect):
    wanted = scenario(example, name)
    assert wanted["name"] == name and wanted["kind"] == "ask"
    assert isinstance(wanted.get("description"), str) and wanted["description"].strip()
    assert wanted.get("today") == today and ("today" in wanted) == (today is not None)
    if first is not None:
        source, addition = first
        assert wanted["lines"] == [scenario(example, source)["lines"][0] + addition, *YES6]
    else:
        assert wanted["lines"] == [ASIDE_OPENING[example], "/back", "no",
                                   scenario(example, ASIDE_FIRST_LINE[example])["lines"][0], *YES6]
    assert wanted["expect"] == expect


@pytest.mark.parametrize("example, name, today, first, expect", NEW)
def test_a_new_scenario_validates(replay, example, name, today, first, expect):
    assert replay.validate_scenario(scenario(example, name), stem=name, brief=brief_of(example)) == []


def test_the_scenarios_of_each_example_are_the_old_ones_and_the_new_ones():
    """(step 5) The data author may add ask scenarios that verify (9.8): the ones of step 4 must all still be there."""
    stems = lambda example: {p.stem for p in (EXAMPLES / example / "scenarios").glob("*.json")}
    assert stems("wedding") >= {"build_monthly_surplus", "cover_each_payment", "no_family_contribution",
                                "decide_what_to_update", "aside_before_asking"}
    assert stems("moving") >= {"build_months_to_save", "months_at_current_saving", "upfront_and_monthly",
                               "keep_or_move_date", "aside_before_asking"}
