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

def test_every_data_file_of_every_example_passes_read_table_and_a_scenario_uses_them(adapter):
    for example in examples_with_data():
        files = data_files(example)
        assert files, example
        for path in files:
            adapter.read_table(path.read_bytes())                 # raises NotLoaded when it does not pass
            assert NAME.match(adapter.account_name(path.name)), path
        assert verifying(example), f"{example} ships no scenario that verifies and loads its data"


# ---- what the data author adds to the wedding example ------------------------------------------------------------------------------------------

def test_the_wedding_example_has_account_files():
    assert data_files("wedding")


def test_each_wedding_file_passes_read_table_and_names_an_account(adapter):
    files = data_files("wedding")
    assert files
    for path in files:
        reading = adapter.read_table(path.read_bytes())
        assert reading["rows"], path
        name = adapter.account_name(path.name)
        assert NAME.match(name) and name != "all"


def test_the_wedding_example_ships_a_scenario_that_verifies():
    assert verifying("wedding")


def test_a_verifying_scenario_names_files_of_the_data_folder_with_their_signs():
    names = {p.name for p in data_files("wedding")}
    assert names and verifying("wedding")
    for scenario in verifying("wedding"):
        for item in scenario["data"]:
            assert item["file"] in names and item["sign"] in SIGNS
            assert "account" not in item or NAME.match(item["account"])


def test_a_verifying_scenario_passes_validation(replay):
    scenarios = verifying("wedding")
    assert scenarios
    for scenario in scenarios:
        assert replay.validate_scenario(scenario, stem=scenario["name"], brief=brief_of("wedding")) == []


def test_a_verifying_scenario_describes_itself_and_expects_a_finding():
    assert verifying("wedding")
    for scenario in verifying("wedding"):
        assert isinstance(scenario.get("description"), str) and scenario["description"].strip()
        assert scenario["expect"]["findings"], scenario["name"]
        assert all(entry["kind"] in ("earlier", "data", "brief") for entry in scenario["expect"]["findings"])
