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


def test_an_example_without_working_or_inputs_or_expected(build):
    good = surplus_examples()
    bad = [good[0], {"inputs": good[1]["inputs"], "expected": "1", "working": ""},
           {"inputs": good[2]["inputs"], "working": "w"}, "not an object", {"expected": "1", "working": "w"}]
    problems = refused_examples(build, bad)
    assert {p.split(":")[0] for p in problems} == {"example 2", "example 3", "example 4", "example 5"}


def test_inputs_that_do_not_fit_the_spec(build):
    good = surplus_examples()
    bad = [good[0], {**good[1], "inputs": {"income": "4000"}}, good[2]]
    assert refused_examples(build, bad) == ["example 2: missing input 'spending'"]


def test_an_expected_answer_that_does_not_fit_the_output_type(build):
    good = surplus_examples()
    bad = [good[0], good[1], {**good[2], "expected": "plenty"}]
    [problem] = refused_examples(build, bad)
    assert problem.startswith("example 3: the expected answer: ")


def test_every_problem_is_listed(build):
    good = surplus_examples()
    bad = [{**good[0], "expected": "x"}, {**good[1], "inputs": {}}]
    problems = refused_examples(build, bad)
    assert "at least 3 examples are needed" in problems
    assert any(p.startswith("example 1: the expected answer: ") for p in problems)
    assert "example 2: missing input 'income'" in problems and "example 2: missing input 'spending'" in problems


def test_an_expected_answer_may_be_a_json_value_of_the_output_type(build):
    examples = [{**e, "expected": float(e["expected"])} for e in surplus_examples()]
    results, _, _ = build([propose_spec(), propose_examples(examples), write_module()], built(), brief=only_step("s1"))
    assert results[0]["outcome"] == "built"


def test_more_than_three_examples_are_fine(build):
    examples = surplus_examples() + [{"inputs": {"income": "10", "spending": "4"}, "expected": "6", "working": "w"}]
    results, _, person = build([propose_spec(), propose_examples(examples), write_module()], built(examples=4),
                               brief=only_step("s1"))
    assert results[0]["outcome"] == "built" and person.asked.count(CONFIRM_EXAMPLE) == 4


def test_rejected_examples_are_recorded(build, conn):
    refused_examples(build, surplus_examples()[:2])
    assert events(conn, "calc.examples_rejected") == [("calc.examples_rejected", "harness", {
        "module": "monthly_surplus", "errors": ["at least 3 examples are needed"]})]


def test_three_refused_attempts_end_the_step_before_any_example_is_shown(build, conn):
    script = [propose_spec(), propose_examples([]), propose_examples([]), propose_examples([])]
    results, model, person = build(script, ["yes"], brief=only_step("s1"))
    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_EXAMPLES}]
    assert len(model.calls) == 4 and person.asked == [PLAN_QUESTION]
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_EXAMPLES}]


# ---- the person's answers --------------------------------------------------------------------

def decisions(conn):
    return [(p["index"], p["decision"], p["expected"]) for p in payloads(conn, "calc.golden_decision")]


def test_accept_confirms_the_proposed_answer(build, conn):
    build(surplus_script(), ["yes", "/accept", "  /accept  ", "/accept"], brief=only_step("s1"))
    assert decisions(conn) == [(1, "accepted", "2023.35"), (2, "accepted", "-500"), (3, "accepted", "0")]
    assert events(conn, "calc.golden_decision")[0][1] == "person"
    assert set(payloads(conn, "calc.golden_decision")[0]) == {"module", "index", "decision", "expected"}
    assert payloads(conn, "calc.golden_decision")[0]["module"] == "monthly_surplus"


@pytest.mark.parametrize("word", sorted(ACCEPT_WORDS) + ["YES", "Okay", "SÍ", "  Yes.  ", "Y"])
def test_every_accept_word_confirms_an_example_whatever_its_case(build, conn, word):
    build([propose_spec(), propose_examples()], ["yes", word, "/quit"], brief=only_step("s1"))
    assert decisions(conn) == [(1, "accepted", "2023.35")]


def test_an_empty_answer_asks_again_with_the_same_question(build, conn):
    _, _, person = build(surplus_script(), ["yes", "", "   ", "/accept", "/accept", "/accept"], brief=only_step("s1"))
    assert person.asked == [PLAN_QUESTION] + [CONFIRM_EXAMPLE] * 5
    assert decisions(conn)[0] == (1, "accepted", "2023.35")


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


def test_quit_keeps_what_was_registered_before(build, registry, conn):
    results, _, _ = build(surplus_script() + h.months_script()[:2], built() + ["yes", "/accept", "/quit"])
    assert [r["outcome"] for r in results] == ["built", "not_built"]
    assert [m["name"] for m in registry.list_modules(conn)] == ["monthly_surplus"]


@pytest.mark.parametrize("answers", [["/accept", "/skip", "/skip"], ["/skip", "/skip", "/skip"], ["/skip", "/accept", "/skip"]])
def test_fewer_than_two_confirmed_examples_end_the_step(build, conn, answers):
    results, model, _ = build([propose_spec(), propose_examples()], ["yes", *answers], brief=only_step("s1"))
    assert results == [{"step": "s1", "outcome": "not_built", "module": None, "reason": REASON_CONFIRMED}]
    assert len(model.calls) == 2                                  # the model is not asked for more
    assert payloads(conn, "calc.step_not_built") == [{"step": "s1", "reason": REASON_CONFIRMED}]


def test_two_confirmed_examples_are_enough(build):
    results, _, _ = build(surplus_script(), ["yes", "/skip", "/accept", "/accept"], brief=only_step("s1"))
    assert results[0]["outcome"] == "built"


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
    ("number", "1234.5", to_json(Decimal("1234.5"))),
    ("number", "$1,234.50", to_json(Decimal("1234.50"))),
    ("number", "€ 7", to_json(Decimal("7"))),
    ("number", "£7.25", to_json(Decimal("7.25"))),
    ("number", "1 000", to_json(Decimal("1000"))),
    ("number", "-3", to_json(Decimal("-3"))),
    ("integer", "1,200", "1200"),
    ("integer", "€ 40", "40"),
    ("integer", " 7 ", "7"),
    ("date", "2027-02-03", "2027-02-03"),
    ("boolean", "true", True), ("boolean", "TRUE", True), ("boolean", "True", True),
    ("boolean", "no", False), ("boolean", "N", False), ("boolean", "n", False), ("boolean", "False", False),
    ("boolean", "false", False),
])
def test_a_typed_answer_is_read_by_the_output_type(build, conn, kind, typed, confirmed):
    model, person = answer_first(build, kind, typed)
    assert decisions(conn) == [(1, "corrected", confirmed)]
    assert len(model.calls) == 2 and CONFIRM_ANSWER not in person.asked      # nothing is sent back for a yes


@pytest.mark.parametrize("typed", ["yes", "y", "Y", "YES"])
def test_for_a_yes_or_no_output_yes_accepts_the_proposed_answer(build, conn, typed):
    answer_first(build, "boolean", typed)
    assert decisions(conn) == [(1, "accepted", True)]


@pytest.mark.parametrize("kind, typed", [
    ("text", "free words"), ("list", '[1, "a"]'), ("list", "one, two"), ("object", '{"k": "v"}'),
    ("number", "abc"), ("number", "nan"), ("number", "Infinity"), ("number", "1.2.3"),
    ("integer", "1.5"), ("integer", "one"),
    ("date", "03/02/2027"), ("date", "2027-13-01"), ("date", "today"),
    ("boolean", "maybe"), ("boolean", "1"),
])
def test_an_answer_that_is_not_read_directly_goes_to_the_example_helper(build, conn, kind, typed):
    model, person = answer_first(build, kind, typed, respond("explain", message="It is a made-up example."))
    assert model.roles() == ["spec_writer", "example_writer", "example_helper"]
    assert payloads(conn, "calc.example_reply") == [{"module": "echo_value", "index": 1, "text": typed}]
    assert person.asked == [PLAN_QUESTION, CONFIRM_EXAMPLE, CONFIRM_EXAMPLE]
    assert decisions(conn) == []                                   # the next answer was /quit


def test_after_an_answer_that_is_not_read_the_next_one_counts(build, conn):
    build([propose_spec(echo_spec("number")), propose_examples(echo_examples("number")),
           respond("explain", message="It is a made-up example.")], ["yes", "abc", "12", "/quit"], brief=only_step("s1"))
    assert decisions(conn) == [(1, "corrected", "12")]
