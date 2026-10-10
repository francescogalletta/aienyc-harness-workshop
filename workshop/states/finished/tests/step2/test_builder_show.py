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

def test_the_worked_rendering_of_the_contract(builder):
    assert builder.show(SHOWN_VALUE) == SHOWN_TEXT


def test_a_value_is_shown_at_an_indent(builder):
    shifted = "\n".join("    " + line for line in SHOWN_TEXT.splitlines())
    assert builder.show(SHOWN_VALUE, 4) == shifted


@pytest.mark.parametrize("value, text", [
    ("some words", "some words"), ("", "(none)"), (True, "yes"), (False, "no"), (3, "3"), (2.5, "2.5"), (-4, "-4"),
    (None, "(none)"), ([], "(none)"), ({}, "(none)")])
def test_a_short_value_is_one_piece_of_text(builder, value, text):
    assert builder.show(value) == text
    assert builder.show(value, 6) == text                    # a short value has no indent of its own


def test_an_object_is_one_field_per_key_in_order_with_the_keys_as_they_are(builder):
    assert builder.show({"zeta key": "1", "Alpha_key": True}) == "zeta key: 1\nAlpha_key: yes"


def test_a_list_is_numbered_from_one(builder):
    assert builder.show(["a", "b", "c"]) == "1. a\n2. b\n3. c"


def test_the_text_has_no_line_break_at_the_start_or_the_end(builder):
    text = builder.show({"a": [1, {"b": [2]}]})
    assert not text.startswith("\n") and not text.endswith("\n")


def test_the_marks_of_a_list_at_an_indent(builder):
    assert builder.show([{"a": "1", "b": "2"}, "x"], 2) == "  1. a: 1\n     b: 2\n  2. x"


# ---- field -----------------------------------------------------------------------------------

@pytest.mark.parametrize("value, text", [
    ("x", "  label: x"), ("", "  label: (none)"), (True, "  label: yes"), ([], "  label: (none)"), ({}, "  label: (none)")])
def test_a_field_with_a_short_value_is_on_one_line(builder, value, text):
    assert builder.field("label", value, 2) == text


def test_a_field_with_a_list_puts_its_items_below(builder):
    assert builder.field("amounts", ["10", "20"], 2) == "  amounts:\n    1. 10\n    2. 20"


def test_a_field_with_an_object_puts_its_fields_below(builder):
    assert builder.field("pair", {"low": "1", "high": "2"}, 0) == "pair:\n  low: 1\n  high: 2"


# ---- plan_words ------------------------------------------------------------------------------

def test_the_plan_in_plain_words_of_the_contract(builder):
    assert builder.plan_words(RENT_SPEC) == RENT_PLAN


@pytest.mark.parametrize("kind, words", [
    ("number", "a number"), ("integer", "a whole number"), ("date", "a date"), ("boolean", "yes or no"),
    ("text", "text"), ("list", "a list"), ("object", "a few named values")])
def test_each_kind_has_its_words(builder, kind, words):
    spec = {**RENT_SPEC, "inputs": [{"name": "an_input", "type": kind, "description": "Some words."}]}
    assert builder.plan_words(spec).splitlines()[2] == f"  - an input ({words}): Some words."


def test_descriptions_are_kept_as_they_are(builder):
    spec = {**RENT_SPEC, "inputs": [{"name": "x", "type": "text", "description": "Keep_this_underscore"}],
            "output": {"type": "text", "description": "Out_put as is"}}
    lines = builder.plan_words(spec).splitlines()
    assert lines[2].endswith(": Keep_this_underscore") and lines[3] == "It gives back: Out_put as is"


# ---- what the person is shown while building ---------------------------------------------------

def test_the_plan_of_the_contract_is_what_the_person_is_told(build):
    _, _, person = build([propose_spec(RENT_SPEC), propose_examples(RENT_EXAMPLES)], ["/quit"], brief=only_step("s1"))
    assert RENT_PLAN in person.told
    assert person.log[person.log.index(("say", RENT_PLAN)) + 1] == ("ask", PLAN_QUESTION)


def test_the_example_of_the_contract_is_shown_exactly(build):
    _, _, person = build([propose_spec(RENT_SPEC), propose_examples(RENT_EXAMPLES)], ["yes", "/quit"],
                         brief=only_step("s1"))
    assert FIRST_BLOCK in person.told


def test_the_second_and_third_example_are_numbered_of_three(build):
    _, _, person = build([propose_spec(RENT_SPEC), propose_examples(RENT_EXAMPLES)], ["yes", "/accept", "/accept", "/quit"],
                         brief=only_step("s1"))
    assert [t.splitlines()[0] for t in person.told if t.startswith("Example ")] == [
        "Example 1 of 3", "Example 2 of 3", "Example 3 of 3"]
    assert "  one off costs: (none)" in person.told[person.told.index(FIRST_BLOCK) + 1]


def test_the_working_and_the_answer_of_a_text_output_are_shown_as_text(build):
    spec = surplus_spec(name="plan_label", output={"type": "text", "description": "A label."},
                        inputs=[{"name": "x", "type": "text", "description": "d"}])
    examples = [{"inputs": {"x": "a"}, "expected": "Plan B", "working": "pick B"}] * 3
    _, _, person = build([propose_spec(spec), propose_examples(examples)], ["yes", "/quit"], brief=only_step("s1"))
    assert "Example 1 of 3\n  x: a\n  Working: pick B\n  Proposed answer: Plan B" in person.told
