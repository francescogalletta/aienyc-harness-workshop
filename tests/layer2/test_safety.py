"""SPEC 5.2: model-written code is read before it is run."""
import re

import pytest

from harness.calc import safety
from harness.calc.safety import ALLOWED_IMPORTS, FORBIDDEN_NAMES, check_code

CLEAN = """\
from decimal import Decimal


def calculate(income, spending):
    total = [income - spending for _ in range(2)]
    return sum(total, Decimal("0"))
"""


def test_a_plain_calculation_may_run():
    assert check_code(CLEAN) == []


def test_code_that_is_not_python_is_refused():
    problems = check_code("def calculate(:\n")
    assert len(problems) == 1 and re.match(r"line \d+: ", problems[0])


@pytest.mark.parametrize("source", [
    "import os",
])
def test_other_imports_are_refused(source):
    problems = check_code(source)
    assert problems and problems[0].startswith("line 1: ")


@pytest.mark.parametrize("name", ["open"])
def test_forbidden_names_are_refused(name):
    assert name in FORBIDDEN_NAMES
    problems = check_code(f"def f(x):\n    return {name}(x)\n")
    assert problems and all(p.startswith("line 2: ") for p in problems)


def test_an_attribute_starting_with_two_underscores_is_refused():
    problems = check_code("def f(x):\n    return x.__class__\n")
    assert problems and problems[0].startswith("line 2: ")


@pytest.mark.parametrize("attribute", ["today"])
def test_reading_the_clock_is_refused(attribute):
    assert attribute in safety.FORBIDDEN_ATTRIBUTES
    source = f"from datetime import datetime\n\n\ndef f():\n    return datetime.{attribute}()\n"
    assert check_code(source) == [
        f"line 5: uses '{attribute}', which makes the answer depend on when it runs"]


