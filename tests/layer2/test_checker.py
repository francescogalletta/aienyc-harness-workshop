"""SPEC 4.5: the second pass counts an answer only when it fits and its working shows it."""
from harness.calc.checker import check_examples
from harness.model import ScriptedModel
from layer2_helpers import TOTAL_SPEC, call

EXAMPLES = [{"n": n, "inputs": {"a": "1", "b": str(n)}, "expected": str(1 + n), "working": "secret"}
            for n in range(1, 6)]


def answers(*found):
    return call("answer_examples", answers=[{"n": n, "answer": answer, "working": working}
                                            for n, answer, working in found])


def test_an_answer_counts_only_when_it_fits_and_its_working_shows_it():
    model = ScriptedModel([answers((1, "2", "1 + 1 = 2"), (2, "3.004", "1 + 2 = 3.004"), (3, "40", "1 + 3 = 4"),
                                   (4, "five", "1 + 4 = five"), (5, "7", "1 + 5 = 7"))])
    found = check_examples(model, {**TOTAL_SPEC, "step_id": "c1"}, EXAMPLES)
    assert [(each["n"], each["agrees"], each["answer"]) for each in found] == [
        (1, True, "2"), (2, True, "3.004"), (3, False, None), (4, False, None), (5, False, "7")]
    assert "40" in found[2]["why"] and found[2]["given"]["answer"] == "40" and found[0]["why"] == ""
    sent = model.calls[0]["messages"][0]["content"]
    assert "secret" not in sent and "expected" not in sent and "step_id" not in sent


def test_a_value_copied_from_the_inputs_counts_without_being_in_the_working():
    spec = {**TOTAL_SPEC, "output": {"type": "object", "description": "the date and the total"}}
    example = {"n": 1, "inputs": {"a": "1", "b": "2026-03-01"}, "expected": {"date": "2026-03-01", "total": "1"}}
    model = ScriptedModel([answers((1, {"date": "2026-03-01", "total": "1"}, "the date stays"))])
    assert check_examples(model, spec, [example])[0]["agrees"]


def test_a_missing_answer_a_reply_without_the_tool_or_a_failed_call_leaves_examples_out():
    assert [each["agrees"] for each in check_examples(ScriptedModel([answers((2, "3", "1 + 2 = 3"))]),
                                                      TOTAL_SPEC, EXAMPLES[:2])] == [False, True]
    assert not any(each["agrees"] for each in check_examples(ScriptedModel([{"text": "2"}]), TOTAL_SPEC, EXAMPLES))
    assert not any(each["agrees"] for each in check_examples(ScriptedModel([]), TOTAL_SPEC, EXAMPLES))
