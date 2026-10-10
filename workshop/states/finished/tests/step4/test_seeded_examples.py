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


# The scenarios that exist at step 4. Later steps add scenarios with keys this step's `validate_scenario` does not know.
STEP4_SCENARIOS = {"wedding": ["aside_before_asking", "build_monthly_surplus", "cover_each_payment",
                               "decide_what_to_update", "no_family_contribution"],
                   "moving": ["aside_before_asking", "build_months_to_save", "keep_or_move_date",
                              "months_at_current_saving", "upfront_and_monthly"]}


def test_every_scenario_still_loads_and_validates(replay, tmp_path):
    for example in NAMES:
        folder = tmp_path / example
        (folder / "scenarios").mkdir(parents=True)
        for name in STEP4_SCENARIOS[example]:
            (folder / "scenarios" / f"{name}.json").write_bytes((EXAMPLES / example / "scenarios" / f"{name}.json").read_bytes())
        scenarios = replay.load_scenarios(folder, brief_of(example))
        assert scenarios and {s["name"] for s in scenarios} == set(STEP4_SCENARIOS[example])


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
