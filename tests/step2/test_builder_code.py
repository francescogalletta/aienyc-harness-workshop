"""SPEC 5.7, phase 3: the code, its checks, its tests and the feedback the writer gets."""
import json

import pytest

import step2_helpers as h
from harness.calc.safety import check_code
from step2_helpers import (CODE_REJECTED, DISAGREEMENT, EXAMPLES_DISAGREE, EXAMPLE_FAILED, GOAL, PARTICULAR, REASON_CODE, TESTS_FAILED, accepts, events,
                           only_step, payloads, propose_examples, propose_spec, rows, surplus_examples,
                           write_module)

START = [propose_spec(), propose_examples()]            # the first two phases, built at the first try
WRONG = write_module(h.WRONG_SURPLUS_PY, h.WRONG_SURPLUS_TESTS)       # passes its own tests, fails the examples


def code_feedback(model, call_index):
    """The content of the tool result the writer got before call number `call_index` (counting all calls)."""
    [result] = [m for m in model.calls[call_index]["messages"] if m["role"] == "tool"]
    assert result["is_error"] is True
    return result["content"]


def lines_of(content):
    return [line for line in content.splitlines() if line.strip()]


def inputs_json(example):
    return json.dumps(example["inputs"], ensure_ascii=False)


# ---- what the writer is sent -------------------------------------------------------------------

def test_the_writer_never_sees_the_brief_or_the_worked_examples(build):
    results, model, _ = build([*START, WRONG, write_module()], accepts(3), brief=only_step("s1"))
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


def test_the_writer_is_given_the_spec(build):
    _, model, _ = build([*START, write_module()], accepts(3), brief=only_step("s1"))
    [call] = h.phase_calls(model, "module_writer.md")
    assert call["messages"] == [{"role": "user", "content": h.sections(("spec", h.saved_spec(h.surplus_spec(), "s1")))}]


# ---- the staging folder ------------------------------------------------------------------------

def test_the_staging_folder_is_emptied_and_holds_the_spec_and_the_confirmed_examples(build, modules_dir):
    stale = modules_dir / "_build" / "monthly_surplus"
    stale.mkdir(parents=True)
    (stale / "left_over.txt").write_text("from an earlier build", encoding="utf-8")
    results, _, _ = build([*START, WRONG, WRONG, WRONG], ["/accept", "/skip", "/accept"], brief=only_step("s1"))
    assert results[0]["reason"] == REASON_CODE
    assert not (stale / "left_over.txt").exists()
    assert (stale / "spec.json").read_text(encoding="utf-8") == h.dump(h.saved_spec(h.surplus_spec(), "s1"))
    expected = h.golden_of([surplus_examples()[0], surplus_examples()[2]])
    assert (stale / "golden.json").read_text(encoding="utf-8") == h.dump(expected)


def test_a_step_that_fails_leaves_the_last_attempt_in_staging_and_registers_nothing(build, conn, modules_dir):
    last = write_module(h.WRONG_SURPLUS_PY + "\n# the last one\n", h.WRONG_SURPLUS_TESTS)
    results, model, _ = build([*START, WRONG, WRONG, last], accepts(3), brief=only_step("s1"))
    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_CODE}]
    assert len(model.calls) == 2 + 3
    staging = modules_dir / "_build" / "monthly_surplus"
    assert "# the last one" in (staging / "module.py").read_text(encoding="utf-8")
    assert rows(conn, "modules") == [] and rows(conn, "step_modules") == []
    assert not (modules_dir / "monthly_surplus").exists()
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_CODE}]


# ---- attempts ----------------------------------------------------------------------------------

def test_each_attempt_is_written_checked_run_and_recorded(build, conn):
    results, _, person = build([*START, WRONG, WRONG, write_module()], accepts(3), brief=only_step("s1"))
    assert results[0]["outcome"] == "built"
    assert [p["attempt"] for p in payloads(conn, "calc.code_written")] == [1, 2, 3]
    assert [p["passed"] for p in payloads(conn, "calc.tests_run")] == [False, False, True]
    assert [r["passed"] for r in rows(conn, "test_runs")] == [0, 0, 1]
    assert {r["reason"] for r in rows(conn, "test_runs")} == {"build"}
    assert person.told.count(h.RUNNING_TESTS) == 3


def test_a_module_is_registered_only_on_the_run_that_passed(build, conn, registry):
    build([*START, WRONG, write_module()], accepts(3), brief=only_step("s1"))
    passing = [r for r in rows(conn, "test_runs") if r["passed"]]
    assert registry.get_module(conn, "monthly_surplus")["test_run_id"] == passing[0]["id"]


def test_the_writer_gets_three_attempts_in_all(build):
    results, model, _ = build([*START, WRONG, WRONG, WRONG, write_module()], accepts(3), brief=only_step("s1"))
    assert results[0]["reason"] == REASON_CODE and len(model.calls) == 5      # the sixth entry is never asked for


# ---- the checks on the code --------------------------------------------------------------------

def rejected_once(build, module_py, tests_py):
    """Send this code once, then good code. Return the bullets of the first refusal."""
    results, model, _ = build([*START, write_module(module_py, tests_py), write_module()], accepts(3),
                              brief=only_step("s1"))
    assert results[0]["outcome"] == "built"
    lines = lines_of(code_feedback(model, 3))
    assert lines[0] == CODE_REJECTED and all(line.startswith("- ") for line in lines[1:])
    return [line[2:] for line in lines[1:]]


def test_unsafe_module_code_is_named_with_its_file(build):
    bad = "import os\n" + h.SURPLUS_PY
    assert rejected_once(build, bad, h.SURPLUS_TESTS) == ["module.py: " + p for p in check_code(bad)]


def test_unsafe_test_code_is_named_with_its_file(build):
    bad = h.SURPLUS_TESTS + "\nimport os\n"
    assert rejected_once(build, h.SURPLUS_PY, bad) == [
        "tests.py: " + p for p in check_code(bad, also_allow=("module",))]


def test_the_clock_is_refused_in_a_module(build):
    bad = "from datetime import date\n\n\ndef calculate(income, spending):\n    return date.today()\n"
    [problem] = rejected_once(build, bad, h.SURPLUS_TESTS)
    assert problem == "module.py: line 5: uses 'today', which makes the answer depend on when it runs"


@pytest.mark.parametrize("module_py", [
    "def calculate(income):\n    return income\n",
    "def calculate(income, spending, extra):\n    return income\n",
    "def calculate(income, other):\n    return income\n",
    "def calculate(income, spending, *args):\n    return income\n",
    "def calculate(income, spending, **kwargs):\n    return income\n",
    "def calculate(*args, **kwargs):\n    return 1\n",
    "def helper(income, spending):\n    return income\n",
    "def outer():\n    def calculate(income, spending):\n        return income\n",
])
def test_calculate_must_have_exactly_the_spec_inputs_as_parameters(build, module_py):
    problems = rejected_once(build, module_py, h.SURPLUS_TESTS)
    assert "module.py must define calculate with exactly these parameters: income, spending" in problems


def test_keyword_only_parameters_count(build):
    module_py = "def calculate(income, *, spending):\n    return income - spending\n"
    tests_py = ("from decimal import Decimal\n\nfrom module import calculate\n\n\n"
                "def test_it():\n    assert calculate(Decimal('5'), spending=Decimal('3')) == Decimal('2')\n")
    results, model, _ = build([*START, write_module(module_py, tests_py)], accepts(3), brief=only_step("s1"))
    assert results[0]["outcome"] == "built" and len(model.calls) == 3


@pytest.mark.parametrize("tests_py", [
    "from module import calculate\n",
    "from module import calculate\n\n\ndef helper():\n    assert True\n",
])
def test_the_tests_need_at_least_one_test_function(build, tests_py):
    problems = rejected_once(build, h.SURPLUS_PY, tests_py)
    assert "tests.py must hold at least one test_ function" in problems


def test_every_problem_is_collected(build):
    bad_module, bad_tests = "import os\ndef calculate(income):\n    return income\n", "import sys\n"
    problems = rejected_once(build, bad_module, bad_tests)
    assert "module.py: " + check_code(bad_module)[0] in problems
    assert "module.py must define calculate with exactly these parameters: income, spending" in problems
    assert "tests.py: " + check_code(bad_tests, also_allow=("module",))[0] in problems
    assert "tests.py must hold at least one test_ function" in problems


@pytest.mark.parametrize("module_py, tests_py", [("", h.SURPLUS_TESTS), (h.SURPLUS_PY, ""), ("", "")])
def test_both_files_must_be_non_empty(build, module_py, tests_py):
    assert rejected_once(build, module_py, tests_py)


def test_rejected_code_is_recorded_and_not_run(build, conn):
    bad = "import os\n" + h.SURPLUS_PY
    rejected_once(build, bad, h.SURPLUS_TESTS)
    [(_, actor, payload)] = events(conn, "calc.code_rejected")
    assert actor == "harness"
    assert payload["module"] == "monthly_surplus" and payload["attempt"] == 1
    assert any("module.py: " in p and "os" in p for p in payload["problems"])
    assert [p["attempt"] for p in payloads(conn, "calc.code_written")] == [1, 2]       # written, then checked
    assert len(rows(conn, "test_runs")) == 1                                            # only the good code was run


def test_three_rejected_attempts_end_the_step(build, conn):
    bad = write_module("import os\n" + h.SURPLUS_PY, h.SURPLUS_TESTS)
    results, model, person = build([*START, bad, bad, bad], accepts(3), brief=only_step("s1"))
    assert results[0]["reason"] == REASON_CODE and len(model.calls) == 5
    assert rows(conn, "test_runs") == [] and h.RUNNING_TESTS not in person.told


def test_a_reply_without_code_counts_as_an_attempt(build):
    results, model, _ = build([*START, h.say_text("done"), h.say_text("done"), write_module()], accepts(3),
                              brief=only_step("s1"))
    assert results[0]["outcome"] == "built" and len(model.calls) == 5


# ---- the feedback after a failed run -----------------------------------------------------------

def test_failing_examples_are_named_by_their_inputs_and_nothing_else(build):
    _, model, _ = build([*START, WRONG, write_module()], accepts(3), brief=only_step("s1"))
    lines = lines_of(code_feedback(model, 3))
    assert lines == [TESTS_FAILED] + ["- " + EXAMPLE_FAILED.format(index=i, inputs=inputs_json(e))
                                      for i, e in enumerate(surplus_examples(), start=1)]


def test_the_feedback_never_holds_an_expected_or_an_actual_answer(build):
    _, model, _ = build([*START, WRONG, write_module()], accepts(3), brief=only_step("s1"))
    feedback = code_feedback(model, 3)
    for answer in ("2023.35", "8223.55", "8500", "6000", "-500"):
        assert answer not in feedback


def test_an_example_that_raised_adds_what_it_stopped_with(build):
    raising = write_module(h.RAISING_SURPLUS_PY, h.RAISING_SURPLUS_TESTS)
    _, model, _ = build([*START, raising, write_module()], accepts(3), brief=only_step("s1"))
    second = surplus_examples()[1]
    assert lines_of(code_feedback(model, 3)) == [
        TESTS_FAILED,
        "- " + EXAMPLE_FAILED.format(index=2, inputs=inputs_json(second)) + " It stopped with: ValueError: spending is above income"]


def test_a_failing_unit_test_is_named_with_its_error_in_full(build, conn):
    failing = ("from decimal import Decimal\n\nfrom module import calculate\n\n\n"
               "def test_zeta_fails():\n    assert calculate(Decimal('2'), Decimal('1')) == Decimal('9')\n\n\n"
               "def test_alpha_fails():\n    assert calculate(Decimal('2'), Decimal('1')) == Decimal('8')\n\n\n"
               "def test_passes():\n    assert calculate(Decimal('2'), Decimal('1')) == Decimal('1')\n")
    bad = write_module(h.SURPLUS_PY, failing)
    _, model, _ = build([*START, bad, write_module()], accepts(3), brief=only_step("s1"))
    feedback = code_feedback(model, 3)
    lines = lines_of(feedback)
    assert lines[0] == TESTS_FAILED
    assert "- test_alpha_fails failed:" in lines and "- test_zeta_fails failed:" in lines
    assert lines.index("- test_alpha_fails failed:") < lines.index("- test_zeta_fails failed:")     # name order
    assert "test_passes" not in feedback
    assert feedback.count("AssertionError") == 2
    reported = json.loads([r for r in rows(conn, "test_runs") if not r["passed"]][0]["report"])
    for test in reported["tests"]:
        if not test["passed"]:
            assert test["error"].strip() in feedback


def test_a_run_that_stopped_says_why(build):
    broken = write_module("raise ValueError('broken import')\n" + h.SURPLUS_PY, h.SURPLUS_TESTS)
    _, model, _ = build([*START, broken, write_module()], accepts(3), brief=only_step("s1"))
    assert lines_of(code_feedback(model, 3)) == [TESTS_FAILED, "- The run stopped: ValueError: broken import"]


def test_failing_tests_come_before_failing_examples(build):
    failing_tests = h.WRONG_SURPLUS_TESTS + "\n\ndef test_nonsense():\n    assert False\n"
    bad = write_module(h.WRONG_SURPLUS_PY, failing_tests)
    _, model, _ = build([*START, bad, write_module()], accepts(3), brief=only_step("s1"))
    lines = lines_of(code_feedback(model, 3))
    assert lines.index("- test_nonsense failed:") < min(i for i, line in enumerate(lines) if line.startswith("- Example "))
    assert lines[0] == TESTS_FAILED


def test_the_feedback_is_an_error_result_after_the_assistant_message(build):
    _, model, _ = build([*START, WRONG, write_module()], accepts(3), brief=only_step("s1"))
    messages = model.calls[3]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
    assert messages[1]["tool_calls"][0]["arguments"]["module_py"] == h.WRONG_SURPLUS_PY


def test_the_two_steps_are_independent_when_one_fails(build, registry, conn):
    script = [*START, WRONG, WRONG, WRONG, *h.months_script()]
    results, _, _ = build(script, accepts(6))
    assert [r["outcome"] for r in results] == ["not_built", "built"]
    assert [m["name"] for m in registry.list_modules(conn)] == ["months_to_goal"]


# ---- when the code and the examples disagree: said to the person, never to the writer ----------

def disagreement(example, got):
    return DISAGREEMENT.format(inputs=inputs_json(example), expected=json.dumps(example["expected"]), got=got)


def test_three_failed_attempts_with_failing_examples_tell_the_person(build):
    results, _, person = build([*START, WRONG, WRONG, WRONG], accepts(3), brief=only_step("s1"))
    assert results[0]["reason"] == REASON_CODE
    first, second, third = surplus_examples()
    assert person.told[-4:] == [EXAMPLES_DISAGREE, disagreement(first, '"8223.55"'),
                                disagreement(second, '"8500"'), disagreement(third, '"6000"')]
    assert person.told.count(EXAMPLES_DISAGREE) == 1


def test_the_message_names_only_the_examples_that_failed(build):
    raising = write_module(h.RAISING_SURPLUS_PY, h.RAISING_SURPLUS_TESTS)
    _, _, person = build([*START, raising, raising, raising], accepts(3), brief=only_step("s1"))
    assert person.told[-2:] == [EXAMPLES_DISAGREE, disagreement(surplus_examples()[1], "an error")]


def test_the_confirmed_answer_is_the_persons_correction(build):
    _, _, person = build([*START, WRONG, WRONG, WRONG], ["/accept", "-499.5", "/accept"], brief=only_step("s1"))
    assert any("you confirmed \"-499.5\"" in line for line in person.told)


def test_the_message_uses_the_numbering_of_the_confirmed_examples(build):
    _, _, person = build([*START, WRONG, WRONG, WRONG], ["/skip", "/accept", "/accept"], brief=only_step("s1"))
    second, third = surplus_examples()[1:]
    assert person.told[-3:] == [EXAMPLES_DISAGREE, disagreement(second, '"8500"'), disagreement(third, '"6000"')]


def test_it_is_not_said_while_the_writer_still_has_attempts(build):
    results, _, person = build([*START, WRONG, WRONG, write_module()], accepts(3), brief=only_step("s1"))
    assert results[0]["outcome"] == "built"
    assert EXAMPLES_DISAGREE not in person.told and not any("you confirmed" in line for line in person.told)


def test_it_is_not_said_when_only_unit_tests_failed(build):
    failing = h.SURPLUS_TESTS + "\n\ndef test_nonsense():\n    assert False\n"
    bad = write_module(h.SURPLUS_PY, failing)
    results, _, person = build([*START, bad, bad, bad], accepts(3), brief=only_step("s1"))
    assert results[0]["reason"] == REASON_CODE
    assert EXAMPLES_DISAGREE not in person.told and not any("you confirmed" in line for line in person.told)


def test_it_is_not_said_when_the_code_never_ran(build):
    unsafe = write_module("import os\n" + h.SURPLUS_PY, h.SURPLUS_TESTS)
    results, _, person = build([*START, unsafe, unsafe, unsafe], accepts(3), brief=only_step("s1"))
    assert results[0]["reason"] == REASON_CODE
    assert EXAMPLES_DISAGREE not in person.told


def test_it_never_reaches_the_model(build):
    _, model, _ = build([*START, WRONG, WRONG, WRONG], accepts(3), brief=only_step("s1"))
    everything = json.dumps([[c["system"], c["messages"]] for c in model.calls])
    for text in ("disagree", "you confirmed", "the code gives", "8223.55", "2023.35", "an error"):
        assert text not in everything, text


# ---- the exact wording of the file checks -------------------------------------------------------

def test_an_empty_module_file_is_named(build):
    assert "module.py is empty" in rejected_once(build, "", h.SURPLUS_TESTS)


def test_an_empty_tests_file_is_named(build):
    assert "tests.py is empty" in rejected_once(build, h.SURPLUS_PY, "")


def test_a_file_that_does_not_parse_gets_only_its_syntax_problem(build):
    problems = rejected_once(build, "def calculate(income, spending:\n", "def test_x(:\n")
    assert problems == ["module.py: " + p for p in check_code("def calculate(income, spending:\n")] + [
        "tests.py: " + p for p in check_code("def test_x(:\n", also_allow=("module",))]
    assert all(problem.startswith(("module.py: line", "tests.py: line")) for problem in problems)


def test_parameter_names_are_compared_as_a_set_so_their_order_does_not_matter(build):
    module_py = "def calculate(spending, income):\n    return income - spending\n"
    tests_py = ("from decimal import Decimal\n\nfrom module import calculate\n\n\n"
                "def test_it():\n    assert calculate(spending=Decimal('3'), income=Decimal('5')) == Decimal('2')\n")
    results, model, _ = build([*START, write_module(module_py, tests_py)], accepts(3), brief=only_step("s1"))
    assert results[0]["outcome"] == "built" and len(model.calls) == 3
