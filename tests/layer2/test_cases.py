"""SPEC 4.2: a step over several cases. A module may take `cases`, a list of named cases, and then gives a list
with one row per case carrying its name; the harness checks the shape at the spec, at the inputs and at the
output, so a case can never be mislabelled on the way out."""
import json

import pytest

from harness.calc import gate, registry
from harness.config import load_config
from harness.core import Session
from harness.model import ScriptedModel
from layer2_helpers import PROPOSED, SETTLE, small_plan

CASES = {"name": "cases", "type": "list",
         "description": "one item per case: name, and guest_count, a whole number of people"}
PRICE = {"name": "price", "type": "number", "description": "the price per guest"}
OUT = {"type": "list", "description": "one item per case: name and total, money"}


def spec(**changes):
    found = {"name": "totals_by_case", "description": "the total of each case", "step_id": "c1",
             "method": "arithmetic", "formula": "guest_count x price, for each case", "inputs": [CASES, PRICE],
             "output": OUT}
    found.update(changes)
    return found


# --- The spec ---

def test_a_spec_with_cases_is_accepted_when_cases_is_a_list_and_the_output_is_a_list_naming_each_case():
    assert registry.validate_spec(spec()) == []


@pytest.mark.parametrize("changes", [
    {"inputs": [{**CASES, "type": "object"}, PRICE]},
    {"output": {"type": "number", "description": "the total"}},
    {"output": {"type": "list", "description": "one item per case: the total"}}])
def test_a_spec_with_cases_of_another_shape_is_refused(changes):
    found = registry.validate_spec(spec(**changes))
    assert found and all("cases" in each for each in found)


# --- The inputs ---

def test_the_cases_given_to_a_module_must_be_named_objects_with_distinct_names():
    good = {"cases": [{"name": "low", "guest_count": "100"}, {"name": "high", "guest_count": "200"}], "price": "10"}
    assert registry.input_problems(spec(), good) == []
    for cases in ([], [{"guest_count": "100"}], [{"name": "", "guest_count": "1"}], [{"name": 3, "guest_count": "1"}],
                  [{"name": "low", "guest_count": "1"}, {"name": "low", "guest_count": "2"}], ["low"]):
        found = registry.input_problems(spec(), {**good, "cases": cases})
        assert found and "cases" in found[0], cases


# --- The output, at the gate ---

HEAD = "from decimal import Decimal\n\n\n"
TEST_HEAD = "from decimal import Decimal\nfrom module import calculate\n\n\n"
GOOD = ("def calculate(cases, price):\n"
        "    return [{'name': c['name'], 'total': Decimal(str(c['guest_count'])) * price} for c in cases]\n")
BAD = ("def calculate(cases, price):\n"
       "    return [{'name': 'case ' + str(n), 'total': Decimal(str(c['guest_count'])) * price}"
       " for n, c in enumerate(cases)]\n")
TEST = ("def test_it():\n    assert calculate(cases=[{'name': 'a', 'guest_count': '2'}], price=Decimal('3'))"
        "[0]['total'] == Decimal('6')\n")
EXAMPLES = [{"inputs": {"cases": [{"name": "low", "guest_count": "10"}, {"name": "high", "guest_count": "20"}],
                        "price": "5"},
             "expected": [{"name": "low", "total": "50"}, {"name": "high", "total": "100"}],
             "working": "10 x 5 = 50; 20 x 5 = 100", "checked_by": "second_pass"},
            {"inputs": {"cases": [{"name": "one", "guest_count": "0"}], "price": "5"},
             "expected": [{"name": "one", "total": "0"}], "working": "0 x 5 = 0", "checked_by": "second_pass"}]


def _plan():
    step = {"method": "arithmetic", "cadence": "", "origin": PROPOSED}
    return small_plan(inputs=[{"name": "Guest count", "description": "people", "origin": PROPOSED},
                              {"name": "Price", "description": "per guest", "origin": PROPOSED}],
                      process=[{"id": "c1", "name": "Totals by case", "kind": "calculation",
                                "formula": "guest count x price for each case", "needs": ["Guest count", "Price"],
                                "produces": "the total of each case", **step}])


def _world(folder, code):
    (folder / "brief").mkdir(parents=True)
    (folder / "brief" / "domain_brief.json").write_text(json.dumps(_plan()), encoding="utf-8")
    module = folder / "modules" / "totals_by_case"
    module.mkdir(parents=True)
    (module / "spec.json").write_text(json.dumps(spec()), encoding="utf-8")
    (module / "golden.json").write_text(json.dumps(EXAMPLES), encoding="utf-8")
    (module / "module.py").write_text(HEAD + code, encoding="utf-8")
    (module / "tests.py").write_text(TEST_HEAD + TEST, encoding="utf-8")


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("HARNESS_LAYERS", "2")
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "harness.db"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "modules"))
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.delenv("HARNESS_EXAMPLE", raising=False)

    def make(code):
        _world(tmp_path, code)
        session = Session(load_config(), model_factory=lambda: ScriptedModel([]))
        session.settle(SETTLE)
        return session

    return make


def test_a_module_that_names_each_case_as_given_runs_and_gives_one_row_per_case_in_order(world):
    session = world(GOOD)
    try:
        run = gate.call(session.conn, "totals_by_case",
                        {"cases": [{"name": "high", "guest_count": "200"}, {"name": "low", "guest_count": "100"}],
                         "price": "10"}, assumptions=[], expected="two rows", session_id=session.conversation)
        assert run["output"] == [{"name": "high", "total": "2000"}, {"name": "low", "total": "1000"}]
        step = next(each for each in session.state()["steps"] if each["id"] == "c1")
        assert step["line"]["text"] == "→ 2 cases"
    finally:
        session.close()


def test_a_module_whose_rows_do_not_carry_the_case_names_in_order_does_not_pass_its_examples(world):
    session = world(BAD)
    try:
        step = next(each for each in session.state()["steps"] if each["id"] == "c1")
        assert step["build"]["status"] == "not_built"
        with pytest.raises(gate.Refused):
            gate.call(session.conn, "totals_by_case", EXAMPLES[0]["inputs"], assumptions=[], expected="x",
                      session_id=session.conversation)
    finally:
        session.close()
