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

@pytest.mark.parametrize("name", [
    "ADOPT_INTRO", "ADOPT_QUESTION", "ADOPT_MISSING", "ADOPT_BAD_SPEC", "ADOPT_BAD_EXAMPLES", "ADOPT_NO_STEP",
    "ADOPT_STEP_TAKEN", "REASON_DECLINED", "REASON_TESTS", "ADOPTED_STEP"])
def test_the_fixed_strings(adopt, name):
    assert getattr(adopt, name) == getattr(s3, name)


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


def test_the_exact_lines_of_the_listing(adopt, conn, brief, folders):
    _, person = run_adopt(conn, brief, "yes")
    assert person.told[1:3] == [
        "  monthly_surplus for step s1: 3 worked examples (accepted, accepted, accepted)",
        "  months_to_goal for step s3: 3 worked examples (accepted, accepted, accepted)"]
    assert person.told[3:] == ["monthly_surplus -> s1 (adopted)", "months_to_goal -> s3 (adopted)"]


def test_adopted_modules_are_registered_and_mapped_like_any_other(adopt, registry, conn, brief, folders):
    run_adopt(conn, brief, "yes", session_id="adopt-session")
    surplus, months = registry.get_module(conn, "monthly_surplus"), registry.get_module(conn, "months_to_goal")
    assert surplus["fingerprint"] == h.expected_fingerprint(folders / "monthly_surplus")
    assert months["fingerprint"] == h.expected_fingerprint(folders / "months_to_goal")
    assert (surplus["steps"], months["steps"]) == (["s1"], ["s3"])
    assert registry.step_map(conn) == {"s1": "monthly_surplus", "s3": "months_to_goal"}
    assert registry.file_status(conn, "monthly_surplus") == "unchanged"
    assert h.rows(conn, "modules")[0]["session_id"] == "adopt-session"
    assert adopt.candidates(conn) == []


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


def test_the_events_of_an_adoption_in_order(adopt, conn, brief, folders):
    run_adopt(conn, brief, "yes")
    assert kinds_of(conn) == [
        "calc.adopt_decision",
        "calc.tests_run", "calc.module_registered", "calc.module_adopted",
        "calc.tests_run", "calc.module_registered", "calc.module_adopted"]
    assert {r["session_id"] for r in conn.execute("SELECT session_id FROM events")} == {SESSION}


def test_the_payloads_and_actors_of_the_events(adopt, conn, brief, folders):
    run_adopt(conn, brief, "  yes \n")
    runs = {r["module"]: r["id"] for r in h.rows(conn, "test_runs")}
    prints = {name: h.expected_fingerprint(folders / name) for name in ("monthly_surplus", "months_to_goal")}
    mine = [(k, a, p) for k, a, p in h.events(conn)]
    assert mine[0] == ("calc.adopt_decision", "person", {
        "modules": ["monthly_surplus", "months_to_goal"], "decision": "accepted", "text": "yes", "how": "asked"})
    assert list(mine[0][2]) == ["modules", "decision", "text", "how"]
    steps = {"monthly_surplus": "s1", "months_to_goal": "s3"}
    for index, name in enumerate(("monthly_surplus", "months_to_goal")):
        tests_run, registered, adopted = mine[1 + 3 * index:4 + 3 * index]
        assert tests_run == ("calc.tests_run", "harness", {
            "module": name, "test_run_id": runs[name], "reason": "adopt", "passed": True, "fingerprint": prints[name]})
        assert registered == ("calc.module_registered", "harness", {
            "module": name, "step": steps[name], "fingerprint": prints[name], "test_run_id": runs[name]})
        assert adopted == ("calc.module_adopted", "harness", {
            "module": name, "step": steps[name], "fingerprint": prints[name], "test_run_id": runs[name],
            "how": "asked"})
        assert list(adopted[2]) == ["module", "step", "fingerprint", "test_run_id", "how"]


@pytest.mark.parametrize("word", sorted(h.ACCEPT_WORDS) + ["YES", "Okay", "  Yes.  ", "Sí", "\n/accept\n"])
def test_an_accept_word_accepts_whatever_its_case(adopt, conn, brief, modules_dir, word):
    s3.surplus_folder(modules_dir)
    results, _ = run_adopt(conn, brief, word)
    assert [r["outcome"] for r in results] == ["adopted"]
    [(_, _, decision)] = h.events(conn, "calc.adopt_decision")
    assert decision["decision"] == "accepted" and decision["text"] == word.strip()


def test_an_empty_answer_asks_again_with_the_same_question_and_records_nothing(adopt, conn, brief, folders):
    results, person = run_adopt(conn, brief, "", "   ", "\n", "yes")
    assert person.asked == [ADOPT_QUESTION] * 4
    assert person.told.count(ADOPT_INTRO) == 1
    assert len(h.events(conn, "calc.adopt_decision")) == 1
    assert [r["outcome"] for r in results] == ["adopted", "adopted"]


def test_the_question_is_asked_once_for_many_folders(adopt, conn, brief, folders):
    s3.put_module(folders, s3.renamed_files(h.yearly_files("added_1"), "yearly_cost"))
    _, person = run_adopt(conn, brief, "yes")
    assert person.asked == [ADOPT_QUESTION]


def test_how_defaults_to_asked(adopt, conn, brief, modules_dir):
    s3.surplus_folder(modules_dir)
    person = h.Person("yes")
    adopt.adopt(conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=SESSION)
    assert h.payloads(conn, "calc.adopt_decision")[0]["how"] == "asked"
    assert h.payloads(conn, "calc.module_adopted")[0]["how"] == "asked"


def test_the_decisions_in_the_listing_are_those_of_the_entries(adopt, conn, brief, modules_dir):
    files = h.surplus_files("s1")
    golden = json.loads(files["golden.json"])
    golden[0]["decision"] = "corrected"
    del golden[1]["decision"]
    golden[2]["decision"] = 5
    s3.put_module(modules_dir, {**files, "golden.json": s3.dump(golden)})
    _, person = run_adopt(conn, brief, "no")
    assert person.told[1] == "  monthly_surplus for step s1: 3 worked examples (corrected, ?, ?)"


def test_n_is_the_length_of_golden_json(adopt, conn, brief, modules_dir):
    files = h.surplus_files("s1")
    golden = json.loads(files["golden.json"])[:2]
    s3.put_module(modules_dir, {**files, "golden.json": s3.dump(golden)})
    _, person = run_adopt(conn, brief, "no")
    assert person.told[1] == "  monthly_surplus for step s1: 2 worked examples (accepted, accepted)"


def test_a_changed_registered_module_is_adopted_again_with_its_new_files(adopt, registry, conn, brief, modules_dir):
    h.install_surplus(conn, "s1")
    old = registry.get_module(conn, "monthly_surplus")["fingerprint"]
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    results, person = run_adopt(conn, brief, "yes")
    assert results == [result("monthly_surplus", "s1")]
    new = registry.get_module(conn, "monthly_surplus")
    assert new["fingerprint"] != old and new["fingerprint"] == h.expected_fingerprint(modules_dir / "monthly_surplus")
    assert registry.file_status(conn, "monthly_surplus") == "unchanged"
    assert registry.step_map(conn) == {"s1": "monthly_surplus"}
    assert len(h.rows(conn, "modules")) == 1
    assert person.told[1] == listing("monthly_surplus", "s1")


def test_the_adopted_module_runs_through_the_gate(adopt, gate, conn, brief, folders):
    run_adopt(conn, brief, "yes")
    ran = gate.call(conn, "monthly_surplus", {"income": "5000", "spending": "3000"}, assumptions=[],
                    expected="2000", session_id=SESSION)
    assert ran["output"] == "2000"


# ---- declined ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("answer", ["no", "/quit", "yes please", "Yes, adopt them", "yeah", "/skip", "/accept now",
                                    "ok sure", "n", "later", "yes!"])
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


def test_a_decline_runs_no_test_and_leaves_the_folders_alone(adopt, conn, brief, folders):
    before = {n: h.snapshot(folders / n) for n in ("monthly_surplus", "months_to_goal")}
    run_adopt(conn, brief, "no")
    assert {n: h.snapshot(folders / n) for n in before} == before
    assert sorted(p.name for p in (folders / "monthly_surplus").iterdir()) == [
        "golden.json", "module.py", "spec.json", "tests.py"]                      # not even a __pycache__


# ---- replay: nobody is asked ------------------------------------------------------------------------

def test_with_how_replay_nobody_is_asked_and_nothing_is_shown_before_the_adoption(adopt, conn, brief, folders):
    person = h.Person()                                     # asking would fail: it has no answer to give
    results = adopt.adopt(conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=SESSION, how="replay")
    assert [r["outcome"] for r in results] == ["adopted", "adopted"]
    assert person.asked == []
    assert ADOPT_INTRO not in person.told and ADOPT_QUESTION not in person.told
    assert not [line for line in person.told if line.startswith("  ")]


def test_with_how_replay_the_decision_is_the_harness_s_and_how_is_replay(adopt, conn, brief, folders):
    person = h.Person()
    adopt.adopt(conn=conn, brief=brief, ask=person.ask, say=person.say, session_id=SESSION, how="replay")
    assert h.events(conn, "calc.adopt_decision") == [("calc.adopt_decision", "harness", {
        "modules": ["monthly_surplus", "months_to_goal"], "decision": "accepted", "text": "", "how": "replay"})]
    assert [p["how"] for p in h.payloads(conn, "calc.module_adopted")] == ["replay", "replay"]
    assert kinds_of(conn)[:4] == ["calc.adopt_decision", "calc.tests_run", "calc.module_registered",
                                  "calc.module_adopted"]
    assert [r["reason"] for r in h.rows(conn, "test_runs")] == ["adopt", "adopt"]


# ---- nothing to adopt -----------------------------------------------------------------------------------

def test_with_no_candidate_nothing_is_asked_said_or_recorded(adopt, conn, brief):
    results, person = run_adopt(conn, brief)
    assert results == [] and person.log == []
    assert h.events(conn) == []


def test_with_registered_folders_only_there_is_nothing_to_do(adopt, conn, brief):
    h.install_surplus(conn, "s1")
    before = len(h.events(conn))
    results, person = run_adopt(conn, brief)
    assert results == [] and person.log == [] and len(h.events(conn)) == before


# ---- a mix ------------------------------------------------------------------------------------------------

def test_the_results_come_in_name_order_whatever_became_of_them(adopt, conn, brief, modules_dir):
    s3.put_module(modules_dir, s3.renamed_files(h.surplus_files("s1"), "a_surplus"))
    h.write_files(modules_dir / "b_incomplete", {"module.py": "x = 1\n"})
    s3.put_module(modules_dir, s3.renamed_files(h.months_files("s3"), "c_months"))
    results, _ = run_adopt(conn, brief, "yes")
    assert [(r["module"], r["outcome"]) for r in results] == [
        ("a_surplus", "adopted"), ("b_incomplete", "not_adopted"), ("c_months", "adopted")]
    assert results[1]["step"] is None


def test_what_a_check_refuses_is_said_before_the_question_and_recorded_before_the_decision(adopt, conn, brief, modules_dir):
    s3.surplus_folder(modules_dir)
    h.write_files(modules_dir / "a_incomplete", {"module.py": "x = 1\n"})
    _, person = run_adopt(conn, brief, "yes")
    missing = "missing files: spec.json, golden.json, tests.py"
    assert person.log[:3] == [("say", refused_line("a_incomplete", missing)), ("say", ADOPT_INTRO),
                              ("say", listing("monthly_surplus", "s1"))]
    assert kinds_of(conn) == ["calc.adopt_refused", "calc.adopt_decision", "calc.tests_run",
                              "calc.module_registered", "calc.module_adopted"]
    [(_, actor, refused)] = h.events(conn, "calc.adopt_refused")
    assert actor == "harness" and refused == {"module": "a_incomplete", "step": None, "reason": missing}
    assert h.payloads(conn, "calc.adopt_decision")[0]["modules"] == ["monthly_surplus"]


def test_a_decline_still_records_the_refused_folders_first(adopt, conn, brief, modules_dir):
    s3.surplus_folder(modules_dir)
    h.write_files(modules_dir / "a_incomplete", {"module.py": "x = 1\n"})
    run_adopt(conn, brief, "no")
    assert kinds_of(conn) == ["calc.adopt_refused", "calc.adopt_decision"]


# ---- tests that fail ------------------------------------------------------------------------------------------

BAD_MODULES = {
    "tests_fail": dict(module_py=h.WRONG_SURPLUS_PY),
    "only_the_examples_catch_it": dict(module_py=h.WRONG_SURPLUS_PY, tests_py=h.WRONG_SURPLUS_TESTS),
    "does_not_run": dict(module_py="def calculate(:\n"),
    "no_tests": dict(tests_py="x = 1\n"),
}


@pytest.mark.parametrize("fault", sorted(BAD_MODULES))
def test_a_module_whose_tests_or_examples_fail_is_not_adopted(adopt, registry, conn, brief, modules_dir, fault):
    s3.surplus_folder(modules_dir, **BAD_MODULES[fault])
    results, person = run_adopt(conn, brief, "yes")
    assert results == [result("monthly_surplus", "s1", "not_adopted", REASON_TESTS)]
    assert person.told[-1] == refused_line("monthly_surplus", REASON_TESTS)
    assert registry.list_modules(conn) == [] and registry.step_map(conn) == {}
    [run] = h.rows(conn, "test_runs")
    assert (run["module"], run["reason"], run["passed"]) == ("monthly_surplus", "adopt", 0)
    assert kinds_of(conn) == ["calc.adopt_decision", "calc.tests_run", "calc.adopt_refused"]
    assert h.payloads(conn, "calc.adopt_refused") == [{"module": "monthly_surplus", "step": "s1", "reason": REASON_TESTS}]
    assert h.payloads(conn, "calc.tests_run")[0]["passed"] is False


def test_one_failing_module_does_not_stop_the_others(adopt, conn, brief, modules_dir):
    s3.put_module(modules_dir, s3.renamed_files({**h.surplus_files("s1"), "module.py": h.WRONG_SURPLUS_PY}, "a_surplus"))
    s3.months_folder(modules_dir)
    results, person = run_adopt(conn, brief, "yes")
    assert results == [result("a_surplus", "s1", "not_adopted", REASON_TESTS), result("months_to_goal", "s3")]
    assert person.told[-2:] == [refused_line("a_surplus", REASON_TESTS), adopted_line("months_to_goal", "s3")]
    assert kinds_of(conn) == ["calc.adopt_decision", "calc.tests_run", "calc.adopt_refused", "calc.tests_run",
                              "calc.module_registered", "calc.module_adopted"]
    assert [m["name"] for m in h.rows(conn, "modules")] == ["months_to_goal"]


def test_a_failing_module_does_not_free_or_take_its_step(adopt, registry, conn, brief, modules_dir):
    s3.surplus_folder(modules_dir, module_py=h.WRONG_SURPLUS_PY)
    run_adopt(conn, brief, "yes")
    assert registry.step_map(conn) == {}


def test_a_module_that_adopts_cleanly_after_its_files_are_fixed(adopt, registry, conn, brief, modules_dir):
    folder = s3.surplus_folder(modules_dir, module_py=h.WRONG_SURPLUS_PY)
    run_adopt(conn, brief, "yes")
    (folder / "module.py").write_text(h.SURPLUS_PY, encoding="utf-8")
    results, _ = run_adopt(conn, brief, "yes", session_id="second")
    assert [r["outcome"] for r in results] == ["adopted"]
    assert registry.get_module(conn, "monthly_surplus")["steps"] == ["s1"]


# ---- register has the last word -------------------------------------------------------------------------------------

def test_a_refusal_of_register_is_the_reason_shown(adopt, registry, conn, brief, modules_dir):
    """Code that imports `os` passes its tests but may not be registered (SPEC 5.2, 5.5); adopt does not check it."""
    s3.surplus_folder(modules_dir, module_py="import os\n\n" + h.SURPLUS_PY)
    results, person = run_adopt(conn, brief, "yes")
    [outcome] = results
    assert outcome["outcome"] == "not_adopted" and outcome["step"] == "s1"
    reason = outcome["reason"]
    assert reason and reason != REASON_TESTS
    assert person.told[-1] == refused_line("monthly_surplus", reason)
    assert h.payloads(conn, "calc.adopt_refused") == [{"module": "monthly_surplus", "step": "s1", "reason": reason}]
    assert kinds_of(conn) == ["calc.adopt_decision", "calc.tests_run", "calc.adopt_refused"]
    assert registry.get_module(conn, "monthly_surplus") is None and registry.step_map(conn) == {}
    assert h.payloads(conn, "calc.tests_run")[0]["passed"] is True
