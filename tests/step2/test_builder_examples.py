"""SPEC 5.7, phase 2 and the person's checks: the worked examples."""
import json
from decimal import Decimal

import pytest

import step2_helpers as h
from harness.calc.values import to_json
from step2_helpers import (ACCEPT_WORDS, CONFIRM_ANSWER, CONFIRM_EXAMPLE, EXAMPLES_REJECTED, PLAN_QUESTION,
                           REASON_CONFIRMED, REASON_EXAMPLES, REASON_STOPPED, built, events, only_step, payloads,
                           propose_examples, propose_spec, respond, surplus_examples, surplus_script, surplus_spec,
                           write_module)


def refused_examples(build, examples):
    """Send these examples once, then good ones. Return the bullets of the first refusal."""
    script = [propose_spec(), propose_examples(examples), propose_examples(), write_module()]
    results, model, _ = build(script, built(), brief=only_step("s1"))
    [result] = [m for m in model.calls[2]["messages"] if m["role"] == "tool"]
    assert result["is_error"] is True
    lines = [line for line in result["content"].splitlines() if line.strip()]
    assert lines[0] == EXAMPLES_REJECTED and all(line.startswith("- ") for line in lines[1:])
    assert results[0]["outcome"] == "built"
    return [line[2:] for line in lines[1:]]


# ---- the harness refuses examples ------------------------------------------------------------

def test_fewer_than_three_examples(build):
    assert refused_examples(build, surplus_examples()[:2]) == ["at least 3 examples are needed"]


# ---- the person's answers --------------------------------------------------------------------

def decisions(conn):
    return [(p["index"], p["decision"], p["expected"]) for p in payloads(conn, "calc.golden_decision")]


def test_accept_confirms_the_proposed_answer(build, conn):
    build(surplus_script(), ["yes", "/accept", "  /accept  ", "/accept"], brief=only_step("s1"))
    assert decisions(conn) == [(1, "accepted", "2023.35"), (2, "accepted", "-500"), (3, "accepted", "0")]
    assert events(conn, "calc.golden_decision")[0][1] == "person"
    assert set(payloads(conn, "calc.golden_decision")[0]) == {"module", "index", "decision", "expected"}
    assert payloads(conn, "calc.golden_decision")[0]["module"] == "monthly_surplus"


def test_skip_leaves_an_example_out_with_no_expected_answer(build, conn, modules_dir):
    results, _, _ = build(surplus_script(), ["yes", "/accept", "/skip", "/accept"], brief=only_step("s1"))
    assert decisions(conn) == [(1, "accepted", "2023.35"), (2, "skipped", None), (3, "accepted", "0")]
    golden = json.loads((modules_dir / "monthly_surplus" / "golden.json").read_text(encoding="utf-8"))
    assert [g["inputs"] for g in golden] == [surplus_examples()[0]["inputs"], surplus_examples()[2]["inputs"]]
    assert results[0]["outcome"] == "built"


def test_the_persons_word_is_final(build, conn, modules_dir):
    wrong = surplus_examples()
    wrong[0] = {**wrong[0], "expected": "1999", "working": "5123.45 less 3100.10 leaves 1999"}
    results, _, _ = build([propose_spec(), propose_examples(wrong), write_module()],
                          ["yes", " $2,023.35 ", "/accept", "/accept"], brief=only_step("s1"))
    assert results[0]["outcome"] == "built"
    assert decisions(conn)[0] == (1, "corrected", to_json(Decimal("2023.35")))
    golden = json.loads((modules_dir / "monthly_surplus" / "golden.json").read_text(encoding="utf-8"))
    assert golden[0] == {"inputs": wrong[0]["inputs"], "expected": "2023.35", "working": wrong[0]["working"],
                         "decision": "corrected"}
    assert [g["decision"] for g in golden] == ["corrected", "accepted", "accepted"]


def test_quit_stops_the_whole_build_at_once(build, conn, registry):
    results, model, person = build(surplus_script() + h.months_script(), ["yes", "/accept", " /quit "])
    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_STOPPED}]
    assert len(model.calls) == 2                                  # no code, and nothing for step s3
    assert not any(t.startswith("Step s3") for t in person.told)
    assert registry.list_modules(conn) == []
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_STOPPED}]
    assert decisions(conn) == [(1, "accepted", "2023.35")]        # the quit itself is not a decision


@pytest.mark.parametrize("answers", [["/accept", "/skip", "/skip"]])
def test_fewer_than_two_confirmed_examples_end_the_step(build, conn, answers):
    results, model, _ = build([propose_spec(), propose_examples()], ["yes", *answers], brief=only_step("s1"))
    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_CONFIRMED}]
    assert len(model.calls) == 2                                  # the model is not asked for more
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_CONFIRMED}]


# ---- how a typed answer is read --------------------------------------------------------------

def echo_spec(kind):
    return surplus_spec(name="echo_value", inputs=[{"name": "x", "type": "text", "description": "Any word."}],
                        output={"type": kind, "description": "The result."})


PROPOSED = {"number": "1", "integer": "1", "date": "2026-01-01", "text": "a", "boolean": True, "list": [], "object": {}}


def echo_examples(kind):
    return [{"inputs": {"x": "a"}, "expected": PROPOSED[kind], "working": f"the answer is {PROPOSED[kind]}"}] * 3


def answer_first(build, kind, typed, *calls):
    """Answer the plan, then the first example with `typed`, then quit. Return (model, person)."""
    _, model, person = build([propose_spec(echo_spec(kind)), propose_examples(echo_examples(kind)), *calls],
                             ["yes", typed, "/quit"], brief=only_step("s1"))
    return model, person


@pytest.mark.parametrize("kind, typed, confirmed", [
    ("number", "$1,234.50", to_json(Decimal("1234.50"))),
])
def test_a_typed_answer_is_read_by_the_output_type(build, conn, kind, typed, confirmed):
    model, person = answer_first(build, kind, typed)
    assert decisions(conn) == [(1, "corrected", confirmed)]
    assert len(model.calls) == 2 and CONFIRM_ANSWER not in person.asked      # nothing is sent back for a yes


@pytest.mark.parametrize("kind, typed", [("number", "abc")])
def test_an_answer_that_is_not_read_directly_goes_to_the_example_helper(build, conn, kind, typed):
    model, person = answer_first(build, kind, typed, respond("explain", message="It is a made-up example."))
    assert model.roles() == ["spec_writer", "example_writer", "example_helper"]
    assert payloads(conn, "calc.example_reply") == [{"module": "echo_value", "index": 1, "text": typed}]
    assert person.asked == [PLAN_QUESTION, CONFIRM_EXAMPLE, CONFIRM_EXAMPLE]
    assert decisions(conn) == []                                   # the next answer was /quit


