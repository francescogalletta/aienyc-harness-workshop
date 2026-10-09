"""SPEC 5.7, phase 2: a proposed answer must show its numbers in its own working."""
import step2_helpers as h
from step2_helpers import (EXAMPLES_REJECTED, REASON_EXAMPLES, built, events, months_examples, months_spec, only_step,
                           payloads, propose_examples, propose_spec, ranged_examples, ranged_spec, surplus_examples,
                           write_module)

SHOWN = "the expected answer has numbers its working does not show: "


def refusal(build, step, spec, bad, good, code):
    """Send the bad examples once, then the good ones. Return the bullets of the refusal and the person."""
    script = [propose_spec(spec), propose_examples(bad), propose_examples(good), code]
    results, model, person = build(script, built(), brief=only_step(step))
    [result] = [m for m in model.calls[2]["messages"] if m["role"] == "tool"]
    lines = [line for line in result["content"].splitlines() if line.strip()]
    assert result["is_error"] is True and lines[0] == EXAMPLES_REJECTED and results[0]["outcome"] == "built"
    return [line[2:] for line in lines[1:]], person


def months_refusal(build, replacement):
    good = months_examples()
    bad = [good[0], {**good[1], **replacement}, good[2]]
    return refusal(build, "s3", months_spec(), bad, good, write_module(h.MONTHS_PY, h.MONTHS_TESTS))[0]


def surplus_refusal(build, bad):
    return refusal(build, "s1", h.surplus_spec(), bad, surplus_examples(), write_module())[0]


def not_refused(build, examples, spec=None):
    """These examples are shown to the person at once: the model is not called again (it would run out of script)."""
    _, model, person = build([propose_spec(spec), propose_examples(examples)], ["yes", "/quit"], brief=only_step("s1"))
    assert len(model.calls) == 2 and any(t.startswith("Example 1 of") for t in person.told)


def test_the_example_whose_working_says_33_point_3_rounded_up_is_refused(build):
    assert months_refusal(build, {"working": "33.3 rounded up"}) == ["example 2: " + SHOWN + "34"]


def test_an_answer_whose_working_shows_it_passes(build):
    results, model, _ = build(h.months_script(), built(), brief=only_step("s3"))
    assert results[0]["outcome"] == "built" and len(model.calls) == 3


def test_a_working_that_shows_another_number_is_refused(build):
    assert months_refusal(build, {"working": "10000 / 300 = 33.3; rounded down to 33"}) == [
        "example 2: " + SHOWN + "34"]


def ranged_refusal(build, bad):
    return refusal(build, "s1", ranged_spec(), bad, ranged_examples(), write_module(h.RANGED_PY, h.RANGED_TESTS))[0]


def test_every_missing_number_is_listed_in_order_of_appearance_joined_by_commas(build):
    bad = ranged_examples()
    bad[0] = {**bad[0], "working": "no numbers here"}
    assert ranged_refusal(build, bad) == ["example 1: " + SHOWN + "13000, 17000, 23000"]


def test_only_the_numbers_not_shown_are_listed(build):
    bad = ranged_examples()
    bad[0] = {**bad[0], "working": "10000 + 3000 = 13000; 10000 + 13000 = 23000"}
    assert ranged_refusal(build, bad) == ["example 1: " + SHOWN + "17000"]


def test_small_whole_numbers_are_not_checked(build):
    not_refused(build, [{**e, "expected": "12", "working": "w"} for e in surplus_examples()])


def test_a_number_may_be_written_differently_in_the_working(build):
    not_refused(build, [{**e, "expected": "34000", "working": "34,000 in all"} for e in surplus_examples()])


def test_a_date_in_the_answer_needs_its_year_in_the_working(build):
    spec = months_spec(name="a_day", output={"type": "date", "description": "A day."},
                       inputs=[{"name": "x", "type": "text", "description": "d"}])
    bad = [{"inputs": {"x": "a"}, "expected": "2031-05-01", "working": "the first of May"}] * 3
    good = [{"inputs": {"x": "a"}, "expected": "2031-05-01", "working": "the first of May, 2031-05-01"}] * 3
    code = write_module("from datetime import date\n\n\ndef calculate(x):\n    return date(2031, 5, 1)\n",
                        "from datetime import date\n\nfrom module import calculate\n\n\n"
                        "def test_it():\n    assert calculate('a') == date(2031, 5, 1)\n")
    [problem, *rest], _ = refusal(build, "s1", spec, bad, good, code)
    assert problem.startswith("example 1: " + SHOWN) and rest[0].startswith("example 2: " + SHOWN)


def test_an_example_with_an_empty_working_gets_only_that_problem(build):
    good = surplus_examples()
    [problem] = surplus_refusal(build, [good[0], {**good[1], "working": ""}, good[2]])
    assert problem.startswith("example 2") and SHOWN not in problem


def test_the_problems_of_an_example_come_in_order_inputs_then_type_then_working(build):
    good = months_examples()
    bad = [good[0], {"inputs": {"target": "10000"}, "expected": "34.5", "working": "w"}, good[2]]
    problems, _ = refusal(build, "s3", months_spec(), bad, good, write_module(h.MONTHS_PY, h.MONTHS_TESTS))
    assert problems[0] == "example 2: missing input 'monthly_saving'"
    assert problems[1].startswith("example 2: the expected answer: ")
    assert problems[2] == "example 2: " + SHOWN + "34.5"
    assert len(problems) == 3


def test_a_refusal_for_the_working_is_recorded_and_the_person_sees_only_the_good_examples(build, conn):
    good = months_examples()
    bad = [good[0], {**good[1], "working": "33.3 rounded up"}, good[2]]
    _, person = refusal(build, "s3", months_spec(), bad, good, write_module(h.MONTHS_PY, h.MONTHS_TESTS))
    assert payloads(conn, "calc.examples_rejected") == [{"module": "months_to_goal",
                                                         "errors": ["example 2: " + SHOWN + "34"]}]
    assert events(conn, "calc.examples_rejected")[0][1] == "harness"
    shown = [t for t in person.told if t.startswith("Example ")]
    assert len(shown) == 3 and "rounded up to 34" in shown[1]


def test_three_refusals_for_the_working_end_the_step(build):
    bad = surplus_examples()
    bad[0] = {**bad[0], "working": "it is what it is"}
    results, model, person = build([propose_spec(), *[propose_examples(bad)] * 3], ["yes"], brief=only_step("s1"))
    assert results[0]["reason"] == REASON_EXAMPLES and len(model.calls) == 4
    assert not any(t.startswith("Example ") for t in person.told)
