"""SPEC 5.3: the runner runs one module in a process of its own."""
import json
import subprocess
import sys

import pytest

from step2_helpers import (CALC, dump, golden_of, saved_spec, surplus_examples, surplus_files, surplus_spec,
                           write_files)


def run(folder, request):
    """Start the runner as the harness does, and read the one JSON object it writes."""
    result = subprocess.run([sys.executable, "-I", str(CALC / "runner.py"), str(folder)],
                            input=json.dumps(request), capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout)


def module_folder(tmp_path, **changes):
    return write_files(tmp_path / "m", {**surplus_files(), **changes})


def spec_with(output_type, inputs=None):
    spec = saved_spec(surplus_spec(), "s1")
    spec["output"] = {"type": output_type, "description": "The result."}
    if inputs is not None:
        spec["inputs"] = inputs
    return dump(spec)


def returning(expression, *tests):
    """A module.py whose calculate returns the given expression, and its tests.py."""
    body = "\n\n\n".join(tests) or "def test_runs():\n    assert calculate(1, 2) is not None"
    return {"module.py": f"from decimal import Decimal\nimport datetime\n\n\ndef calculate(income, spending):\n    return {expression}\n",
            "tests.py": f"from module import calculate\n\n\n{body}\n"}


def test_a_call_returns_the_output_as_json(tmp_path):
    answer = run(module_folder(tmp_path), {"action": "call", "inputs": {"income": "5000", "spending": "3000.50"}})
    assert answer == {"ok": True, "output": "1999.50"}


def test_a_module_that_raises_is_reported_as_type_and_message(tmp_path):
    folder = module_folder(tmp_path, **{"module.py": "def calculate(income, spending):\n    raise ValueError('no good')\n"})
    assert run(folder, {"action": "call", "inputs": {"income": "1", "spending": "1"}}) == {
        "ok": False, "error": "ValueError: no good"}


def test_a_test_run_gives_the_report(tmp_path):
    answer = run(module_folder(tmp_path), {"action": "test"})
    assert answer["ok"] is True
    report = answer["report"]
    assert report["passed"] is True
    assert report["tests"] == [{"name": "test_a_shortfall", "passed": True},
                               {"name": "test_a_surplus", "passed": True}]       # in name order
    assert [g["index"] for g in report["golden"]] == [1, 2, 3]                    # numbered from 1
    assert [g["got"] for g in report["golden"]] == ["2023.35", "-500", "0"]
    assert all(g["passed"] for g in report["golden"])


def test_a_wrong_worked_example_fails_the_report_and_shows_what_the_module_gave(tmp_path):
    examples = surplus_examples()
    examples[0] = {**examples[0], "expected": "9999"}
    golden = dump(golden_of(examples))
    report = run(module_folder(tmp_path, **{"golden.json": golden}), {"action": "test"})["report"]
    assert report["passed"] is False
    assert report["golden"][0] == {"index": 1, "passed": False, "got": "2023.35"}
    assert report["golden"][1]["passed"] and report["golden"][2]["passed"]


# The change of 5.3: a result must fit the spec's output type.

@pytest.mark.parametrize("output_type, expression", [
    ("number", "[income]"),                       # a list where a number is promised
    ("integer", "income / 4"),                    # 1.25 is not a whole number
])
def test_a_result_that_does_not_fit_the_spec_fails_the_call(tmp_path, output_type, expression):
    folder = module_folder(tmp_path, **{"spec.json": spec_with(output_type)}, **returning(expression))
    answer = run(folder, {"action": "call", "inputs": {"income": "5", "spending": "1"}})
    assert answer["ok"] is False
    assert answer["error"].startswith("ValueError: the result does not fit the spec: ")


