"""SPEC 6.1 and 9.8: the account files and the verifying scenario the data author adds to `examples/wedding/`.

The seeded data is added after step 5 is implemented, so the tests about `examples/wedding/data/` are expected to fail
until then (xfail, not strict). The rule for every example that has a `data/` folder holds already, and so is not marked.
"""
import json
import re

import pytest

from step5_helpers import EXAMPLES, SIGNS, h

NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def data_files(example):
    folder = EXAMPLES / example / "data"
    return sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")) if folder.is_dir() else []


def scenarios_of(example):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((EXAMPLES / example / "scenarios").glob("*.json"))]


def verifying(example):
    return [s for s in scenarios_of(example) if s["kind"] == "ask" and s.get("verify") is True and s.get("data")
            and (s["expect"].get("findings") is not None)]


def brief_of(example):
    from harness.calc.builder import load_brief
    return load_brief(EXAMPLES / example / "brief")


def examples_with_data():
    return sorted(p.name for p in EXAMPLES.iterdir() if p.is_dir() and (p / "data").is_dir())


# ---- the rule for every example that has a data folder (9.8) --------------------------------------------------------------------



# ---- what the data author adds to the wedding example ------------------------------------------------------------------------------------------

def test_the_wedding_example_has_account_files():
    assert data_files("wedding")








def test_a_verifying_scenario_passes_validation(replay):
    scenarios = verifying("wedding")
    assert scenarios
    for scenario in scenarios:
        assert replay.validate_scenario(scenario, stem=scenario["name"], brief=brief_of("wedding")) == []


