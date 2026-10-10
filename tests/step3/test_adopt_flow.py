"""SPEC 6.3 and 6.8: adopting module folders, the question, the lines said, the events and the registry."""
import json

import pytest

import step3_helpers as s3
from step3_helpers import (ADOPT_INTRO, ADOPT_QUESTION, REASON_DECLINED, REASON_TESTS, adopted_line, h, listing,
                           refused_line, result, run_adopt)

SESSION = h.SESSION


@pytest.fixture
def folders(modules_dir):
    s3.surplus_folder(modules_dir)
    s3.months_folder(modules_dir)
    return modules_dir


def kinds_of(conn):
    return [kind for kind, _, _ in h.events(conn)]


# ---- the strings ----------------------------------------------------------------------------------


# ---- accepted ---------------------------------------------------------------------------------------

def test_two_folders_are_adopted_after_one_question(adopt, conn, brief, folders):
    results, person = run_adopt(conn, brief, "yes")
    assert results == [result("monthly_surplus", "s1"), result("months_to_goal", "s3")]
    assert all(list(r) == ["module", "step", "outcome", "reason"] for r in results)
    assert person.log == [
        ("say", ADOPT_INTRO),
        ("say", listing("monthly_surplus", "s1")),
        ("say", listing("months_to_goal", "s3")),
        ("ask", ADOPT_QUESTION),
        ("say", adopted_line("monthly_surplus", "s1")),
        ("say", adopted_line("months_to_goal", "s3"))]


def test_each_module_is_registered_on_a_test_run_with_the_reason_adopt(adopt, conn, brief, folders):
    run_adopt(conn, brief, "yes")
    runs = h.rows(conn, "test_runs")
    assert [(r["module"], r["reason"], r["passed"]) for r in runs] == [
        ("monthly_surplus", "adopt", 1), ("months_to_goal", "adopt", 1)]
    modules = {r["name"]: r for r in h.rows(conn, "modules")}
    assert modules["monthly_surplus"]["test_run_id"] == runs[0]["id"]
    assert modules["months_to_goal"]["test_run_id"] == runs[1]["id"]
    assert runs[0]["fingerprint"] == modules["monthly_surplus"]["fingerprint"]
    assert json.loads(runs[0]["report"])["passed"] is True


@pytest.mark.parametrize("word", ["YES"])
def test_an_accept_word_accepts_whatever_its_case(adopt, conn, brief, modules_dir, word):
    s3.surplus_folder(modules_dir)
    results, _ = run_adopt(conn, brief, word)
    assert [r["outcome"] for r in results] == ["adopted"]
    [(_, _, decision)] = h.events(conn, "calc.adopt_decision")
    assert decision["decision"] == "accepted" and decision["text"] == word.strip()


# ---- declined ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("answer", ["yes please"])
def test_any_other_answer_declines_and_the_leniency_of_6_6_does_not_apply(adopt, conn, brief, folders, answer):
    results, person = run_adopt(conn, brief, answer)
    assert results == [result("monthly_surplus", "s1", "not_adopted", REASON_DECLINED),
                       result("months_to_goal", "s3", "not_adopted", REASON_DECLINED)]
    assert person.told[-2:] == [refused_line("monthly_surplus", REASON_DECLINED),
                                refused_line("months_to_goal", REASON_DECLINED)]
    assert h.events(conn) == [("calc.adopt_decision", "person", {
        "modules": ["monthly_surplus", "months_to_goal"], "decision": "declined", "text": answer.strip(),
        "how": "asked"})]
    assert h.rows(conn, "test_runs") == [] and h.rows(conn, "modules") == [] and h.rows(conn, "step_modules") == []


# ---- replay: nobody is asked ------------------------------------------------------------------------

def test_with_how_replay_nobody_is_asked_and_nothing_is_shown_before_the_adoption(adopt, conn, brief, folders):
    person = h.Person()                                     # asking would fail: it has no answer to give
    results = adopt.adopt(conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=SESSION, how="replay")
    assert [r["outcome"] for r in results] == ["adopted", "adopted"]
    assert person.asked == []
    assert ADOPT_INTRO not in person.told and ADOPT_QUESTION not in person.told
    assert not [line for line in person.told if line.startswith("  ")]


# ---- nothing to adopt -----------------------------------------------------------------------------------


# ---- a mix ------------------------------------------------------------------------------------------------


# ---- tests that fail ------------------------------------------------------------------------------------------


def test_one_failing_module_does_not_stop_the_others(adopt, conn, brief, modules_dir):
    s3.put_module(modules_dir, s3.renamed_files({**h.surplus_files("s1"), "module.py": h.WRONG_SURPLUS_PY}, "a_surplus"))
    s3.months_folder(modules_dir)
    results, person = run_adopt(conn, brief, "yes")
    assert results == [result("a_surplus", "s1", "not_adopted", REASON_TESTS), result("months_to_goal", "s3")]
    assert person.told[-2:] == [refused_line("a_surplus", REASON_TESTS), adopted_line("months_to_goal", "s3")]
    assert kinds_of(conn) == ["calc.adopt_decision", "calc.tests_run", "calc.adopt_refused", "calc.tests_run",
                              "calc.module_registered", "calc.module_adopted"]
    assert [m["name"] for m in h.rows(conn, "modules")] == ["months_to_goal"]


# ---- register has the last word -------------------------------------------------------------------------------------
