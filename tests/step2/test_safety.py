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


def test_every_problem_is_one_line_starting_with_its_line_number():
    problems = check_code("import os\nx = open('f')\n")
    assert len(problems) == 2
    assert problems[0].startswith("line 1: ") and problems[1].startswith("line 2: ")


def test_code_that_is_not_python_is_refused():
    problems = check_code("def calculate(:\n")
    assert len(problems) == 1 and re.match(r"line \d+: ", problems[0])


def test_the_allowed_imports():
    assert ALLOWED_IMPORTS == {"decimal", "datetime", "math", "fractions", "calendar", "statistics"}
    for module in ALLOWED_IMPORTS:
        assert check_code(f"import {module}\nfrom {module} import *\n") == []


@pytest.mark.parametrize("source", [
    "import os", "import os.path", "from os import path", "import sys", "import json",
    "from . import decimal", "from .decimal import Decimal", "import decimal, subprocess",
])
def test_other_imports_are_refused(source):
    problems = check_code(source)
    assert problems and problems[0].startswith("line 1: ")


def test_also_allow_names_one_more_module():
    source = "from module import calculate\n"
    assert check_code(source)
    assert check_code(source, also_allow=("module",)) == []
    assert check_code("import os\n", also_allow=("module",))


@pytest.mark.parametrize("name", ["open", "eval", "exec", "getattr", "print", "type", "input", "__import__"])
def test_forbidden_names_are_refused(name):
    assert name in FORBIDDEN_NAMES
    problems = check_code(f"def f(x):\n    return {name}(x)\n")
    assert problems and all(p.startswith("line 2: ") for p in problems)


def test_an_attribute_starting_with_two_underscores_is_refused():
    problems = check_code("def f(x):\n    return x.__class__\n")
    assert problems and problems[0].startswith("line 2: ")


@pytest.mark.parametrize("source", [
    "def f():\n    global x\n",
    "def f():\n    x = 1\n    def g():\n        nonlocal x\n",
    "class A:\n    pass\n",
    "async def f():\n    pass\n",
    "def f(x):\n    with x:\n        pass\n",
    "def f():\n    try:\n        pass\n    except Exception:\n        pass\n",
    "def f(x):\n    while x:\n        pass\n",
    "f = lambda x: x\n",
])
def test_these_statements_are_refused(source):
    assert check_code(source)


@pytest.mark.parametrize("attribute", ["today", "now", "utcnow"])
def test_reading_the_clock_is_refused(attribute):
    assert attribute in safety.FORBIDDEN_ATTRIBUTES
    source = f"from datetime import datetime\n\n\ndef f():\n    return datetime.{attribute}()\n"
    assert check_code(source) == [
        f"line 5: uses '{attribute}', which makes the answer depend on when it runs"]


def test_the_clock_is_refused_even_without_calling_it():
    source = "import datetime\nclock = datetime.datetime.now\n"
    assert check_code(source) == ["line 2: uses 'now', which makes the answer depend on when it runs"]


def test_the_set_of_forbidden_attributes():
    assert safety.FORBIDDEN_ATTRIBUTES == {"today", "now", "utcnow"}
