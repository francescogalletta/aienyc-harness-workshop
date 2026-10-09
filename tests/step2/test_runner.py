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


def test_a_call_converts_each_input_with_from_json(tmp_path):
    spec = [{"name": "income", "type": "number", "description": "."},
            {"name": "spending", "type": "integer", "description": "."}]
    folder = module_folder(tmp_path, **{"spec.json": spec_with("number", spec)},
                           **returning("income * spending"))
    answer = run(folder, {"action": "call", "inputs": {"income": "1,500.25", "spending": 2}})
    assert answer == {"ok": True, "output": "3000.50"}


@pytest.mark.parametrize("inputs", [
    {"income": "5000"},                                                  # one missing
    {"income": "5000", "spending": "1", "extra": "1"},                   # one extra
    {"income": "5000", "spending": "abc"},                               # one that does not fit
])
def test_a_call_with_inputs_that_do_not_fit_fails_with_its_reason(tmp_path, inputs):
    answer = run(module_folder(tmp_path), {"action": "call", "inputs": inputs})
    assert answer["ok"] is False and isinstance(answer["error"], str) and answer["error"]


def test_a_module_that_raises_is_reported_as_type_and_message(tmp_path):
    folder = module_folder(tmp_path, **{"module.py": "def calculate(income, spending):\n    raise ValueError('no good')\n"})
    assert run(folder, {"action": "call", "inputs": {"income": "1", "spending": "1"}}) == {
        "ok": False, "error": "ValueError: no good"}


def test_a_module_that_cannot_be_loaded_is_reported(tmp_path):
    folder = module_folder(tmp_path, **{"module.py": "def calculate(:\n"})
    answer = run(folder, {"action": "call", "inputs": {"income": "1", "spending": "1"}})
    assert answer["ok"] is False and answer["error"].startswith("SyntaxError")


def test_what_a_module_prints_is_thrown_away(tmp_path):
    chatty = "print('at import')\n\n\ndef calculate(income, spending):\n    print('in the call')\n    return income\n"
    answer = run(module_folder(tmp_path, **{"module.py": chatty}), {"action": "call", "inputs": {"income": "7", "spending": "1"}})
    assert answer == {"ok": True, "output": "7"}


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


def test_only_top_level_test_functions_are_run(tmp_path):
    tests = ("from module import calculate\n\n\ndef helper():\n    assert False\n\n\n"
             "def test_one():\n    assert calculate(1, 2) == -1\n")
    answer = run(module_folder(tmp_path, **{"tests.py": tests}), {"action": "test"})
    assert [t["name"] for t in answer["report"]["tests"]] == ["test_one"]


def test_a_failing_unit_test_carries_its_traceback(tmp_path):
    tests = "from module import calculate\n\n\ndef test_wrong():\n    assert calculate(1, 2) == 99\n"
    report = run(module_folder(tmp_path, **{"tests.py": tests}), {"action": "test"})["report"]
    assert report["passed"] is False
    [failed] = report["tests"]
    assert failed["name"] == "test_wrong" and failed["passed"] is False and "AssertionError" in failed["error"]


def test_a_wrong_worked_example_fails_the_report_and_shows_what_the_module_gave(tmp_path):
    examples = surplus_examples()
    examples[0] = {**examples[0], "expected": "9999"}
    golden = dump(golden_of(examples))
    report = run(module_folder(tmp_path, **{"golden.json": golden}), {"action": "test"})["report"]
    assert report["passed"] is False
    assert report["golden"][0] == {"index": 1, "passed": False, "got": "2023.35"}
    assert report["golden"][1]["passed"] and report["golden"][2]["passed"]


def test_an_example_that_raises_has_an_error_and_no_answer(tmp_path):
    raising = "def calculate(income, spending):\n    if spending > income:\n        raise ValueError('too much')\n    return income - spending\n"
    report = run(module_folder(tmp_path, **{"module.py": raising}), {"action": "test"})["report"]
    assert report["golden"][1] == {"index": 2, "passed": False, "error": "ValueError: too much"}
    assert report["passed"] is False


def test_an_example_is_checked_with_same(tmp_path):
    examples = surplus_examples()
    examples[0] = {**examples[0], "expected": "2023.354"}                # within half a cent
    report = run(module_folder(tmp_path, **{"golden.json": dump(golden_of(examples))}), {"action": "test"})["report"]
    assert report["golden"][0]["passed"] is True


def test_with_no_tests_the_run_does_not_pass(tmp_path):
    folder = module_folder(tmp_path, **{"tests.py": "from module import calculate\n"})
    report = run(folder, {"action": "test"})["report"]
    assert report["tests"] == [] and report["passed"] is False


def test_a_module_that_cannot_be_loaded_gives_no_report(tmp_path):
    answer = run(module_folder(tmp_path, **{"module.py": "raise RuntimeError('broken')\n"}), {"action": "test"})
    assert answer == {"ok": False, "error": "RuntimeError: broken"}


# The change of 5.3: a result must fit the spec's output type.

@pytest.mark.parametrize("output_type, expression", [
    ("number", "[income]"),                       # a list where a number is promised
    ("number", "'abc'"),
    ("integer", "income / 4"),                    # 1.25 is not a whole number
    ("date", "income"),
    ("boolean", "income"),
    ("list", "income"),
    ("object", "[income]"),
    ("text", "[income]"),
])
def test_a_result_that_does_not_fit_the_spec_fails_the_call(tmp_path, output_type, expression):
    folder = module_folder(tmp_path, **{"spec.json": spec_with(output_type)}, **returning(expression))
    answer = run(folder, {"action": "call", "inputs": {"income": "5", "spending": "1"}})
    assert answer["ok"] is False
    assert answer["error"].startswith("ValueError: the result does not fit the spec: ")


def test_a_result_that_does_not_fit_fails_its_worked_example(tmp_path):
    golden = dump([{"inputs": {"income": "5", "spending": "1"}, "expected": "5", "working": "w", "decision": "accepted"}])
    folder = module_folder(tmp_path, **returning("[income]"), **{"golden.json": golden})
    report = run(folder, {"action": "test"})["report"]
    assert report["passed"] is False
    assert report["golden"][0]["passed"] is False
    assert report["golden"][0]["error"].startswith("ValueError: the result does not fit the spec: ")


@pytest.mark.parametrize("output_type, expression, output", [
    ("number", "income", "5"),
    ("integer", "int(income)", "5"),
    ("date", "datetime.date(2026, 3, 15)", "2026-03-15"),
    ("boolean", "income > 1", True),
    ("text", "'words'", "words"),
    ("list", "[income, spending]", ["5", "1"]),
    ("object", "{'total': income}", {"total": "5"}),
])
def test_a_result_that_fits_the_spec_is_returned(tmp_path, output_type, expression, output):
    folder = module_folder(tmp_path, **{"spec.json": spec_with(output_type)}, **returning(expression))
    assert run(folder, {"action": "call", "inputs": {"income": "5", "spending": "1"}}) == {"ok": True, "output": output}
