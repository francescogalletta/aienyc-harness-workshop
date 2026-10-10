"""SPEC 5.7: the plan in plain words, and values shown without JSON. The SPEC's worked renderings, byte for byte."""
import json

import pytest

from step2_helpers import PLAN_QUESTION, only_step, propose_examples, propose_spec, surplus_spec

# The value of "Showing values" in the SPEC.
SHOWN_VALUE = json.loads(
    '{"plan": "B", "paid": false, "count": 3, "rate": 0.5, "items": [], "extra": {}, "note": null, "label": "", '
    '"schedule": [{"date": "2027-01-01", "amounts": ["10", "20"]}, "later", [1, 2]], '
    '"nested": {"inner": {"a": "1"}}}')

SHOWN_TEXT = """\
plan: B
paid: no
count: 3
rate: 0.5
items: (none)
extra: (none)
note: (none)
label: (none)
schedule:
  1. date: 2027-01-01
     amounts:
       1. 10
       2. 20
  2. later
  3. 1. 1
     2. 2
nested:
  inner:
    a: 1"""

# The spec and the example of "The plan check" and "The person checks every example".
RENT_SPEC = {
    "name": "rent_total", "description": "The total cost of renting.", "step_id": "s1", "method": "arithmetic",
    "formula": "low = months_low x monthly_rent + the sum of one_off_costs; "
               "high = months_high x monthly_rent + the sum of one_off_costs",
    "inputs": [{"name": "months_low", "type": "integer", "description": "The fewest months you expect to rent."},
               {"name": "months_high", "type": "integer", "description": "The most months you expect to rent."},
               {"name": "monthly_rent", "type": "number", "description": "The rent for one month, in your currency."},
               {"name": "one_off_costs", "type": "list",
                "description": "Each cost paid once. Each item has name and amount."}],
    "output": {"type": "object", "description": "low and high: the total cost for the fewest and for the most months."},
}

RENT_PLAN = """\
To work this out: low = months low x monthly rent + the sum of one off costs; high = months high x monthly rent + the sum of one off costs
I will need from you:
  - months low (a whole number): The fewest months you expect to rent.
  - months high (a whole number): The most months you expect to rent.
  - monthly rent (a number): The rent for one month, in your currency.
  - one off costs (a list): Each cost paid once. Each item has name and amount.
It gives back: low and high: the total cost for the fewest and for the most months."""

RENT_EXAMPLES = [
    {"inputs": {"months_low": "2", "months_high": "3", "monthly_rent": "1000",
                "one_off_costs": [{"name": "deposit", "amount": "500"}, {"name": "van", "amount": "200"}]},
     "expected": {"low": "2700", "high": "3700"},
     "working": "2 x 1000 = 2000; 3 x 1000 = 3000; 500 + 200 = 700; 2000 + 700 = 2700; 3000 + 700 = 3700"},
    {"inputs": {"months_low": "1", "months_high": "2", "monthly_rent": "100", "one_off_costs": []},
     "expected": {"low": "100", "high": "200"}, "working": "1 x 100 = 100; 2 x 100 = 200; no one-off costs"},
    {"inputs": {"months_low": "1", "months_high": "1", "monthly_rent": "500",
                "one_off_costs": [{"name": "fee", "amount": "50"}]},
     "expected": {"low": "550", "high": "550"}, "working": "1 x 500 = 500; 500 + 50 = 550"},
]

FIRST_BLOCK = """\
Example 1 of 3
  months low: 2
  months high: 3
  monthly rent: 1000
  one off costs:
    1. name: deposit
       amount: 500
    2. name: van
       amount: 200
  Working: 2 x 1000 = 2000; 3 x 1000 = 3000; 500 + 200 = 700; 2000 + 700 = 2700; 3000 + 700 = 3700
  Proposed answer:
    low: 2700
    high: 3700"""


# ---- show ------------------------------------------------------------------------------------


# ---- field -----------------------------------------------------------------------------------


# ---- plan_words ------------------------------------------------------------------------------

def test_the_plan_in_plain_words_of_the_contract(builder):
    assert builder.plan_words(RENT_SPEC) == RENT_PLAN


# ---- what the person is shown while building ---------------------------------------------------


def test_the_example_of_the_contract_is_shown_exactly(build):
    _, _, person = build([propose_spec(RENT_SPEC), propose_examples(RENT_EXAMPLES)], ["yes", "/quit"],
                         brief=only_step("s1"))
    assert FIRST_BLOCK in person.told


