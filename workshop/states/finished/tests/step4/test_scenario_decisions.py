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


@pytest.mark.parametrize("decisions", [
    [], [{"kind": "judgment", "step": "s2"}],
    [{"kind": "assumptions"}, {"kind": "judgment", "step": "s2", "choice": "2", "count": 3}]])
def test_decisions_that_are_fine(replay, decisions):
    assert problems(replay, decisions=decisions) == []


@pytest.mark.parametrize("entry", [{"kind": "approval"}])
def test_an_entry_that_is_not_in_the_shape(replay, entry):
    assert problems(replay, decisions=[entry]) == [ENTRY.format(k=1)]


def decide(decisions, conn, session=SESSION, kind="judgment", step="s2", choice="1", options=None):
    options = ["Keep", "Move"] if options is None and kind == "judgment" else (options or [])
    return decisions.record_decision(conn, session_id=session, kind=kind, step_id=step, question="q", options=options,
                                     choice=choice, words=choice, runs=[])


def check(replay, conn, session=SESSION, **expect):
    return replay.check_scenario(conn, session, scenario(**expect), None)


def test_no_decision_fails_with_the_counts_of_the_kind(replay, decisions, conn):
    [found] = check(replay, conn, decisions=[{"kind": "judgment"}])
    assert found == {"what": "at least 1 judgment decision", "passed": False, "seen": "0 matching of 0 judgment decisions"}


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


@pytest.mark.parametrize("asides, passed", [({"opened": 1}, [False]), ({"opened": 2, "turns": 3}, [True, True])])
def test_more_or_fewer_is_a_fail(replay, conn, asides, passed):
    aside_events(conn, SESSION, opened=2, messages=3)
    assert [c["passed"] for c in check(replay, conn, asides=asides)] == passed


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
