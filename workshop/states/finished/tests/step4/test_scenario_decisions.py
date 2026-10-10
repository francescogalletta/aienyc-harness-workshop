"""SPEC 6.4, 6.5 and 8.8: the expectations `decisions` and `asides` of a scenario: validation, checks, and a replay with
the scripted model and the scripted person."""
import pytest

import step4_helpers as s4
from step4_helpers import h, side

s3 = s4.s3
DELETE = object()
SESSION = h.SESSION
OTHER = "another-session"
ENTRY = ("expect.decisions: entry {k} must be an object with a kind (assumptions, judgment or build) and, optionally, "
         "step, choice and count (1 or more)")
NOT_A_STEP = "expect.decisions: entry {k}: '{step}' is not a step of the brief"
BAD_CHOICE = ("expect.decisions: entry {k}: choice must be yes or no for assumptions and build, and 1, 2, 3, 4 or "
              "something else for judgment")
BAD_ASIDES = "expect.asides must be an object with opened, turns or both, each a whole number, 0 or more"


def validate(replay, value, stem="upfront", brief=None):
    return replay.validate_scenario(value, stem=stem, brief=brief or h.make_brief())


def scenario(kind="ask", **expect):
    base = s3.ask_scenario("upfront") if kind == "ask" else s3.build_scenario("upfront")
    base["expect"] = expect
    return base


def problems(replay, **expect):
    return validate(replay, scenario(**expect))


# ---- validation: what is fine -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("decisions", [
    [], [{"kind": "assumptions"}], [{"kind": "judgment"}], [{"kind": "build"}], [{"kind": "judgment", "step": "s2"}],
    [{"kind": "judgment", "step": "s1"}], [{"kind": "judgment", "step": "s3", "choice": "1"}],
    [{"kind": "judgment", "step": "added_1"}], [{"kind": "build", "step": "added_77", "choice": "yes"}],
    [{"kind": "assumptions", "choice": "no", "count": 2}], [{"kind": "judgment", "choice": "something else"}],
    [{"kind": "judgment", "choice": c} for c in ("1", "2", "3", "4")],
    [{"kind": "assumptions", "choice": "yes", "count": 1}], [{"kind": "build", "choice": "no", "count": 10}],
    [{"kind": "assumptions"}, {"kind": "judgment", "step": "s2", "choice": "2", "count": 3}]])
def test_decisions_that_are_fine(replay, decisions):
    assert problems(replay, decisions=decisions) == []


@pytest.mark.parametrize("asides", [{"opened": 0}, {"turns": 0}, {"opened": 1}, {"turns": 3}, {"opened": 1, "turns": 0},
                                    {"opened": 2, "turns": 7}])
def test_asides_that_are_fine(replay, asides):
    assert problems(replay, asides=asides) == []


def test_the_new_expectations_go_with_the_old_ones(replay):
    assert problems(replay, runs=[{"module": "monthly_surplus"}], shown=["2,000"], max_withheld=0, max_corrections=0,
                    decisions=[{"kind": "assumptions"}], asides={"opened": 0}) == []


# ---- validation: decisions ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [{}, "judgment", None, 5, {"kind": "judgment"}, True])
def test_decisions_that_is_not_a_list(replay, value):
    assert problems(replay, decisions=value) == ["expect.decisions must be a list"]


@pytest.mark.parametrize("entry", [
    "judgment", 5, None, [], {}, {"step": "s2"}, {"kind": "approval"}, {"kind": "Judgment"}, {"kind": 5}, {"kind": None},
    {"kind": "judgment", "step": ""}, {"kind": "judgment", "step": 5}, {"kind": "judgment", "step": None},
    {"kind": "judgment", "choice": 1}, {"kind": "judgment", "choice": None}, {"kind": "judgment", "count": 0},
    {"kind": "judgment", "count": -1}, {"kind": "judgment", "count": True}, {"kind": "judgment", "count": "1"},
    {"kind": "judgment", "count": 1.5}, {"kind": "judgment", "count": None}, {"kind": "judgment", "extra": 1},
    {"kind": "judgment", "steps": "s2"}])
def test_an_entry_that_is_not_in_the_shape(replay, entry):
    assert problems(replay, decisions=[entry]) == [ENTRY.format(k=1)]


def test_entries_are_numbered_from_1_and_each_bad_one_is_named(replay):
    found = problems(replay, decisions=[{"kind": "judgment"}, {"kind": "x"}, {"kind": "build"}, 5])
    assert found == [ENTRY.format(k=2), ENTRY.format(k=4)]


def test_nothing_more_is_checked_for_an_entry_that_is_not_in_the_shape(replay):
    found = problems(replay, decisions=[{"kind": "approval", "step": "zz", "choice": "maybe"}])
    assert found == [ENTRY.format(k=1)]


@pytest.mark.parametrize("step", ["s9", "x", "S2", "added", "Added_1", " s2", "step_1"])
def test_a_step_that_is_not_in_the_brief(replay, step):
    assert problems(replay, decisions=[{"kind": "judgment", "step": step}]) == [NOT_A_STEP.format(k=1, step=step)]


def test_a_step_with_the_added_prefix_needs_no_step_in_the_brief(replay):
    assert problems(replay, decisions=[{"kind": "build", "step": "added_"}]) == []


@pytest.mark.parametrize("kind, choice", [
    ("assumptions", "1"), ("assumptions", "something else"), ("assumptions", "Yes"), ("assumptions", ""), ("build", "2"),
    ("build", "something else"), ("build", "maybe"), ("judgment", "yes"), ("judgment", "no"), ("judgment", "5"),
    ("judgment", "0"), ("judgment", "Something else"), ("judgment", "something_else"), ("judgment", "")])
def test_a_choice_that_does_not_go_with_the_kind(replay, kind, choice):
    assert problems(replay, decisions=[{"kind": kind, "choice": choice}]) == [BAD_CHOICE.format(k=1)]


def test_each_entry_gets_its_own_messages_in_order(replay):
    found = problems(replay, decisions=[{"kind": "judgment", "step": "s9", "choice": "yes"}, {"kind": "build"},
                                        {"kind": "assumptions", "choice": "3"}])
    assert found == [NOT_A_STEP.format(k=1, step="s9"), BAD_CHOICE.format(k=1), BAD_CHOICE.format(k=3)]


# ---- validation: asides ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [[], "yes", None, 5, True, {}, {"other": 1}, {"opened": 1, "other": 1}, {"opened": -1},
                                   {"turns": -1}, {"opened": True}, {"turns": False}, {"opened": "1"}, {"turns": 1.5},
                                   {"opened": None}, {"opened": 1, "turns": "2"}])
def test_asides_that_is_not_in_the_shape(replay, value):
    assert problems(replay, asides=value) == [BAD_ASIDES]


# ---- validation: kind and order ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("key, value", [("decisions", [{"kind": "judgment"}]), ("asides", {"opened": 1})])
def test_the_new_expectations_are_for_ask_scenarios_only(replay, key, value):
    found = validate(replay, scenario("build", **{key: value}))
    assert found == [f"expect.{key} is only for ask scenarios"]


def test_steps_is_still_for_build_only(replay):
    assert validate(replay, scenario("ask", steps={"s1": "built"})) == ["expect.steps is only for build scenarios"]


def test_unknown_keys_are_still_unknown(replay):
    assert problems(replay, decision=[{"kind": "judgment"}]) == ["expect: unknown key: decision"]


def test_the_errors_come_in_the_order_of_the_table_not_of_the_object(replay):
    found = problems(replay, asides={}, decisions={}, max_withheld=-1)
    assert found == ["expect.max_withheld must be a whole number, 0 or more", "expect.decisions must be a list", BAD_ASIDES]


# ---- checks ---------------------------------------------------------------------------------------------------------------------------------

def decide(decisions, conn, session=SESSION, kind="judgment", step="s2", choice="1", options=None):
    options = ["Keep", "Move"] if options is None and kind == "judgment" else (options or [])
    return decisions.record_decision(conn, session_id=session, kind=kind, step_id=step, question="q", options=options,
                                     choice=choice, words=choice, runs=[])


def check(replay, conn, session=SESSION, **expect):
    return replay.check_scenario(conn, session, scenario(**expect), None)


def test_a_decision_check_has_the_what_passed_and_seen_keys(replay, decisions, conn):
    decide(decisions, conn)
    [found] = check(replay, conn, decisions=[{"kind": "judgment"}])
    assert list(found) == ["what", "passed", "seen"]
    assert found == {"what": "at least 1 judgment decision", "passed": True, "seen": "1 matching of 1 judgment decisions"}


def test_no_decision_fails_with_the_counts_of_the_kind(replay, decisions, conn):
    [found] = check(replay, conn, decisions=[{"kind": "judgment"}])
    assert found == {"what": "at least 1 judgment decision", "passed": False, "seen": "0 matching of 0 judgment decisions"}


@pytest.mark.parametrize("entry, what", [
    ({"kind": "assumptions"}, "at least 1 assumptions decision"),
    ({"kind": "build"}, "at least 1 build decision"),
    ({"kind": "judgment", "count": 1}, "at least 1 judgment decision"),
    ({"kind": "judgment", "count": 2}, "at least 2 judgment decisions"),
    ({"kind": "judgment", "count": 10}, "at least 10 judgment decisions"),
    ({"kind": "judgment", "step": "s2"}, "at least 1 judgment decision for step s2"),
    ({"kind": "judgment", "step": "added_1"}, "at least 1 judgment decision for step added_1 (not in the brief)"),
    ({"kind": "judgment", "choice": "2"}, "at least 1 judgment decision choosing 2"),
    ({"kind": "judgment", "choice": "something else"}, "at least 1 judgment decision choosing something else"),
    ({"kind": "judgment", "step": "s2", "choice": "2", "count": 3}, "at least 3 judgment decisions for step s2 choosing 2"),
    ({"kind": "build", "step": "s1", "choice": "yes", "count": 2}, "at least 2 build decisions for step s1 choosing yes")])
def test_what_each_decision_check_says(replay, conn, entry, what):
    [found] = check(replay, conn, decisions=[entry])
    assert found["what"] == what


def test_a_decision_must_match_the_step_and_the_choice(replay, decisions, conn):
    decide(decisions, conn, step="s2", choice="1")
    decide(decisions, conn, step="s2", choice="2")
    decide(decisions, conn, step="s1", choice="2")
    decide(decisions, conn, kind="assumptions", step=None, choice="yes", options=[])
    found = check(replay, conn, decisions=[
        {"kind": "judgment"}, {"kind": "judgment", "step": "s2"}, {"kind": "judgment", "choice": "2"},
        {"kind": "judgment", "step": "s2", "choice": "2"}, {"kind": "judgment", "step": "s3"},
        {"kind": "judgment", "step": "s2", "choice": "3"}, {"kind": "assumptions", "choice": "yes"},
        {"kind": "assumptions", "choice": "no"}, {"kind": "build"}])
    assert [(c["passed"], c["seen"]) for c in found] == [
        (True, "3 matching of 3 judgment decisions"), (True, "2 matching of 3 judgment decisions"),
        (True, "2 matching of 3 judgment decisions"), (True, "1 matching of 3 judgment decisions"),
        (False, "0 matching of 3 judgment decisions"), (False, "0 matching of 3 judgment decisions"),
        (True, "1 matching of 1 assumptions decisions"), (False, "0 matching of 1 assumptions decisions"),
        (False, "0 matching of 0 build decisions")]


def test_the_count_is_at_least(replay, decisions, conn):
    for _ in range(3):
        decide(decisions, conn)
    found = check(replay, conn, decisions=[{"kind": "judgment", "count": 2}, {"kind": "judgment", "count": 3},
                                           {"kind": "judgment", "count": 4}])
    assert [c["passed"] for c in found] == [True, True, False]
    assert found[2]["seen"] == "3 matching of 3 judgment decisions"


def test_the_default_count_is_one(replay, decisions, conn):
    decide(decisions, conn)
    assert check(replay, conn, decisions=[{"kind": "judgment"}])[0]["passed"] is True


def test_only_the_decisions_of_the_session_count(replay, decisions, conn):
    decide(decisions, conn, session=OTHER)
    decide(decisions, conn, session=OTHER, kind="build", step="s1", choice="yes", options=[])
    [found] = check(replay, conn, decisions=[{"kind": "judgment"}])
    assert found["passed"] is False and found["seen"] == "0 matching of 0 judgment decisions"
    assert check(replay, conn, session=OTHER, decisions=[{"kind": "judgment"}])[0]["passed"] is True


def test_a_decision_about_no_step_does_not_match_a_step(replay, decisions, conn):
    decide(decisions, conn, kind="assumptions", step=None, choice="yes", options=[])
    [found] = check(replay, conn, decisions=[{"kind": "assumptions", "step": "s1"}])
    assert found["passed"] is False


def test_a_step_added_by_the_conversation_is_matched_by_its_id(replay, decisions, conn):
    decide(decisions, conn, kind="build", step="added_1", choice="yes", options=[])
    [found] = check(replay, conn, decisions=[{"kind": "build", "step": "added_1", "choice": "yes"}])
    assert found == {"what": "at least 1 build decision for step added_1 (not in the brief) choosing yes", "passed": True,
                     "seen": "1 matching of 1 build decisions"}


def test_checking_records_nothing_and_writes_no_decision(replay, decisions, conn):
    decide(decisions, conn)
    before = len(h.events(conn)), len(s4.decision_rows(conn))
    check(replay, conn, decisions=[{"kind": "judgment"}], asides={"opened": 0, "turns": 0})
    assert (len(h.events(conn)), len(s4.decision_rows(conn))) == before


def aside_events(conn, session, opened, messages):
    for n in range(1, opened + 1):
        s3.record(conn, session, "aside.opened", "person", aside=n, first="x", looking_at=None)
    for n in range(messages):
        s3.record(conn, session, "aside.message", "person", aside=1, text=f"message {n}")


def test_an_aside_check_counts_exactly(replay, conn):
    aside_events(conn, SESSION, opened=2, messages=3)
    found = check(replay, conn, asides={"opened": 2, "turns": 3})
    assert found == [{"what": "2 side conversations opened", "passed": True, "seen": "2 opened"},
                     {"what": "3 side conversation turns", "passed": True, "seen": "3 turns"}]


@pytest.mark.parametrize("asides, passed", [
    ({"opened": 1}, [False]), ({"opened": 3}, [False]), ({"opened": 2}, [True]), ({"turns": 2}, [False]),
    ({"turns": 4}, [False]), ({"turns": 3}, [True]), ({"opened": 2, "turns": 2}, [True, False]),
    ({"opened": 3, "turns": 3}, [False, True]), ({"opened": 2, "turns": 3}, [True, True])])
def test_more_or_fewer_is_a_fail(replay, conn, asides, passed):
    aside_events(conn, SESSION, opened=2, messages=3)
    assert [c["passed"] for c in check(replay, conn, asides=asides)] == passed


def test_one_check_only_for_the_key_given(replay, conn):
    aside_events(conn, SESSION, opened=1, messages=1)
    assert [c["what"] for c in check(replay, conn, asides={"opened": 1})] == ["1 side conversations opened"]
    assert [c["what"] for c in check(replay, conn, asides={"turns": 1})] == ["1 side conversation turns"]


def test_no_aside_means_zero_and_zero_can_be_expected(replay, conn):
    found = check(replay, conn, asides={"opened": 0, "turns": 0})
    assert found == [{"what": "0 side conversations opened", "passed": True, "seen": "0 opened"},
                     {"what": "0 side conversation turns", "passed": True, "seen": "0 turns"}]


def test_only_the_side_conversations_of_the_session_count(replay, conn):
    aside_events(conn, OTHER, opened=3, messages=5)
    aside_events(conn, SESSION, opened=1, messages=2)
    assert [c["seen"] for c in check(replay, conn, asides={"opened": 1, "turns": 2})] == ["1 opened", "2 turns"]


def test_other_aside_events_are_not_turns(replay, conn):
    aside_events(conn, SESSION, opened=1, messages=1)
    s3.record(conn, SESSION, "aside.reply", "agent", aside=1, text="x")
    s3.record(conn, SESSION, "aside.closed", "person", aside=1, turns=1, how="back", carried=None)
    assert [c["seen"] for c in check(replay, conn, asides={"opened": 1, "turns": 1})] == ["1 opened", "1 turns"]


def test_the_order_of_the_checks(replay, decisions, conn):
    decide(decisions, conn)
    aside_events(conn, SESSION, opened=1, messages=1)
    s3.record(conn, SESSION, "ask.reply", "agent", text="You have 2,000.")
    found = check(replay, conn, asides={"turns": 1, "opened": 1}, decisions=[{"kind": "build"}, {"kind": "judgment"}],
                  max_corrections=1, max_withheld=1, not_shown=["9,999"], shown=["2,000"], runs=[{"module": "monthly_surplus"}])
    assert [c["what"] for c in found] == [
        "ran monthly_surplus", "shows 2,000", "does not show 9,999", "at most 1 replies withheld", "at most 1 corrections",
        "at least 1 build decision", "at least 1 judgment decision", "1 side conversations opened",
        "1 side conversation turns"]


def test_a_build_scenario_is_checked_as_before(replay, conn):
    found = replay.check_scenario(conn, SESSION, scenario("build", steps={"s1": "built"}),
                                  [{"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""}])
    assert [c["what"] for c in found] == ["step s1 built"]


# ---- replay with the scripted model and the scripted person -----------------------------------------------------------------------------------

@pytest.fixture
def scratch(replay_scratch):
    return replay_scratch


def replay_ask(replay, example, lines, script, **expect):
    from harness.model import ScriptedModel
    folder = example(scenarios={})
    wanted = {"name": "upfront", "kind": "ask", "lines": lines, "expect": expect}
    assert validate(replay, wanted) == []
    return replay.run_scenario(wanted, example_dir=folder, model=ScriptedModel(script))


def seen(result):
    return {c["what"]: c["seen"] for c in result["checks"]}


def test_a_gate_answered_yes_by_the_scripted_person(replay, example, scratch):
    result = replay_ask(replay, example, [s3.ASK_QUESTION, "yes"], [s4.run(), h.say_text("You have 2,000 left each month.")],
                        decisions=[{"kind": "assumptions", "choice": "yes"}], runs=[{"module": "monthly_surplus"}],
                        shown=["2,000"], max_withheld=0)
    assert result["error"] is None and result["passed"] is True
    assert seen(result)["at least 1 assumptions decision choosing yes"] == "1 matching of 1 assumptions decisions"


def test_when_the_lines_run_out_a_gate_is_a_no(replay, example, scratch):
    result = replay_ask(replay, example, [s3.ASK_QUESTION], [s4.run(), h.say_text("I did not run it.")],
                        decisions=[{"kind": "assumptions", "choice": "no"}], max_withheld=0)
    assert result["error"] is None and result["passed"] is True
    assert replay_ask(replay, example, [s3.ASK_QUESTION], [s4.run(), h.say_text("I did not run it.")],
                      runs=[{"module": "monthly_surplus"}])["passed"] is False


def test_when_the_lines_run_out_a_decision_is_something_else(replay, example, scratch):
    result = replay_ask(replay, example, [s3.ASK_QUESTION], [s4.ask_decision(step="s2"), h.say_text("Understood.")],
                        decisions=[{"kind": "judgment", "step": "s2", "choice": "something else"}])
    assert result["error"] is None and result["passed"] is True


def test_a_yes_at_a_decision_takes_the_suggestion(replay, example, scratch):
    script = [s4.ask_decision(step="s2", recommendation=2, why="Safer."), h.say_text("Understood.")]
    result = replay_ask(replay, example, [s3.ASK_QUESTION, "yes"], script,
                        decisions=[{"kind": "judgment", "step": "s2", "choice": "2"}])
    assert result["passed"] is True


def test_a_yes_at_a_decision_without_a_suggestion_is_the_persons_own_words(replay, example, scratch):
    script = [s4.ask_decision(step="s2"), h.say_text("Understood.")]
    result = replay_ask(replay, example, [s3.ASK_QUESTION, "yes"], script,
                        decisions=[{"kind": "judgment", "step": "s2", "choice": "something else"}])
    assert result["passed"] is True


def test_a_failed_decision_expectation_is_a_failed_scenario_with_what_was_seen(replay, example, scratch):
    result = replay_ask(replay, example, [s3.ASK_QUESTION], [h.say_text("Hello.")], decisions=[{"kind": "judgment"}])
    assert result["error"] is None and result["passed"] is False
    assert seen(result) == {"at least 1 judgment decision": "0 matching of 0 judgment decisions"}


def test_a_side_conversation_at_the_opening_question(replay, example, scratch):
    lines = ["/aside What is a sinking fund?", "/back", "no", s3.ASK_QUESTION]
    script = [side("It is money set aside."), h.run_module(), h.say_text("You have 2,000 left each month.")]
    result = replay_ask(replay, example, lines, script, asides={"opened": 1, "turns": 1},
                        runs=[{"module": "monthly_surplus"}], max_withheld=0)
    assert result["error"] is None and result["passed"] is True
    assert seen(result)["1 side conversations opened"] == "1 opened" and seen(result)["1 side conversation turns"] == "1 turns"


def test_a_side_conversation_that_runs_out_of_lines_ends_the_scenario(replay, example, scratch):
    result = replay_ask(replay, example, ["/aside What is a sinking fund?"], [side("It is money set aside.")],
                        asides={"opened": 1, "turns": 1})
    assert result["error"] is None and result["passed"] is True


def test_a_scenario_with_no_aside_has_zero(replay, example, scratch):
    result = replay_ask(replay, example, [s3.ASK_QUESTION], [h.say_text("Hello.")], asides={"opened": 0, "turns": 0})
    assert result["passed"] is True


def test_an_aside_at_a_gate_in_a_replay(replay, example, scratch):
    lines = [s3.ASK_QUESTION, "/aside What does steady mean?", "/back", "no", "yes"]
    script = [s4.run(), side("It does not change."), h.say_text("You have 2,000 left each month.")]
    result = replay_ask(replay, example, lines, script, asides={"opened": 1, "turns": 1},
                        decisions=[{"kind": "assumptions", "choice": "yes"}], shown=["2,000"])
    assert result["error"] is None and result["passed"] is True


def test_the_decisions_of_a_replay_are_in_its_scratch_database(replay, example, scratch, monkeypatch):
    from pathlib import Path
    from harness.model import ScriptedModel
    folder = example(scenarios={})
    wanted = {"name": "upfront", "kind": "ask", "lines": [s3.ASK_QUESTION, "yes"],
              "expect": {"decisions": [{"kind": "assumptions"}]}}
    result = replay.run_scenario(wanted, example_dir=folder, model=ScriptedModel([s4.run(), h.say_text("Done.")]), keep=True)
    rows = s3.stored_events(Path(result["folder"]) / "harness.db", kind="ask.decision")
    assert len(rows) == 1 and rows[0]["payload"]["kind"] == "assumptions" and rows[0]["payload"]["words"] == "yes"
