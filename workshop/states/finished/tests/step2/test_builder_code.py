"""SPEC 5.7, phase 3: the code, its checks, its tests and the feedback the writer gets."""
import json

import pytest

import step2_helpers as h
from harness.calc.safety import check_code
from step2_helpers import (CODE_REJECTED, DISAGREEMENT, EXAMPLES_DISAGREE, EXAMPLE_FAILED, GOAL, PARTICULAR, REASON_CODE, TESTS_FAILED, built, events,
                           only_step, payloads, propose_examples, propose_spec, rows, surplus_examples,
                           write_module)

START = [propose_spec(), propose_examples()]            # the first two phases, built at the first try
WRONG = write_module(h.WRONG_SURPLUS_PY, h.WRONG_SURPLUS_TESTS)       # passes its own tests, fails the examples


def code_feedback(model, call_index):
    """The content of the tool result the writer got before call number `call_index` (counting all calls)."""
    [result] = [m for m in model.calls[call_index]["messages"] if m["role"] == "tool"]
    assert result["is_error"] is True
    return result["content"]


def inputs_json(example):
    return json.dumps(example["inputs"], ensure_ascii=False)


def lines_of(content):
    return [line for line in content.splitlines() if line.strip()]


# ---- what the writer is sent -------------------------------------------------------------------

def test_the_writer_never_sees_the_brief_or_the_worked_examples(build):
    results, model, _ = build([*START, WRONG, write_module()], built(), brief=only_step("s1"))
    assert results[0]["outcome"] == "built"
    writer_calls = h.phase_calls(model, "module_writer.md")
    assert len(writer_calls) == 2
    secrets = [GOAL, PARTICULAR, "Count it as spending", "Emergency fund",
               *[e["working"] for e in surplus_examples()], *[e["expected"] for e in surplus_examples() if e["expected"] != "0"],
               "8223.55", "8500", "6000"]                       # what the wrong module gave
    for call in writer_calls:
        text = json.dumps([call["system"], call["messages"]])
        for secret in secrets:
            assert secret not in text, secret
    first = json.dumps(writer_calls[0]["messages"])
    assert "5123.45" not in first                               # not even the inputs of the examples


# ---- the staging folder ------------------------------------------------------------------------


# ---- attempts ----------------------------------------------------------------------------------


# ---- the checks on the code --------------------------------------------------------------------

def rejected_once(build, module_py, tests_py):
    """Send this code once, then good code. Return the bullets of the first refusal."""
    results, model, _ = build([*START, write_module(module_py, tests_py), write_module()], built(),
                              brief=only_step("s1"))
    assert results[0]["outcome"] == "built"
    lines = lines_of(code_feedback(model, 3))
    assert lines[0] == CODE_REJECTED and all(line.startswith("- ") for line in lines[1:])
    return [line[2:] for line in lines[1:]]


def test_unsafe_module_code_is_named_with_its_file(build):
    bad = "import os\n" + h.SURPLUS_PY
    assert rejected_once(build, bad, h.SURPLUS_TESTS) == ["module.py: " + p for p in check_code(bad)]


@pytest.mark.parametrize("module_py", [
    "def calculate(income):\n    return income\n",
])
def test_calculate_must_have_exactly_the_spec_inputs_as_parameters(build, module_py):
    problems = rejected_once(build, module_py, h.SURPLUS_TESTS)
    assert "module.py must define calculate with exactly these parameters: income, spending" in problems


# ---- the feedback after a failed run -----------------------------------------------------------

def test_failing_examples_are_named_by_their_inputs_and_nothing_else(build):
    _, model, _ = build([*START, WRONG, write_module()], built(), brief=only_step("s1"))
    lines = lines_of(code_feedback(model, 3))
    assert lines == [TESTS_FAILED] + ["- " + EXAMPLE_FAILED.format(index=i, inputs=inputs_json(e))
                                      for i, e in enumerate(surplus_examples(), start=1)]


# ---- when the code and the examples disagree: said to the person, never to the writer ----------

def disagreement(k, confirmed, gives):
    """The block said for one failing example: `confirmed` and `gives` are the lines already laid out."""
    return "\n".join([DISAGREEMENT.format(k=k), confirmed, gives])


def short(k, confirmed, gives):
    return disagreement(k, f"  You confirmed: {confirmed}", f"  The code gives: {gives}")


def test_three_failed_attempts_with_failing_examples_tell_the_person(build):
    results, _, person = build([*START, WRONG, WRONG, WRONG], built(), brief=only_step("s1"))
    assert results[0]["reason"] == REASON_CODE
    assert person.told[-4:] == [EXAMPLES_DISAGREE, short(1, "2023.35", "8223.55"),
                                short(2, "-500", "8500"), short(3, "0", "6000")]
    assert person.told.count(EXAMPLES_DISAGREE) == 1


def test_it_never_reaches_the_model(build):
    _, model, _ = build([*START, WRONG, WRONG, WRONG], built(), brief=only_step("s1"))
    everything = json.dumps([c["messages"] for c in model.calls])
    for text in ("disagree", "You confirmed", "The code gives", "8223.55", "2023.35", "an error"):
        assert text not in everything, text


# ---- the exact wording of the file checks -------------------------------------------------------


