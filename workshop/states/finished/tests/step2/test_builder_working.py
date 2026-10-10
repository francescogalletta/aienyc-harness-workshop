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


def ranged_refusal(build, bad):
    return refusal(build, "s1", ranged_spec(), bad, ranged_examples(), write_module(h.RANGED_PY, h.RANGED_TESTS))[0]


def test_every_missing_number_is_listed_in_order_of_appearance_joined_by_commas(build):
    bad = ranged_examples()
    bad[0] = {**bad[0], "working": "no numbers here"}
    assert ranged_refusal(build, bad) == ["example 1: " + SHOWN + "13000, 17000, 23000"]


