"""SPEC 7.1, 7.2: when a pass runs, and what the reviewer is given and may do within one pass."""
import pytest

from harness.review import reviewer
from layer5_helpers import (SETTLE, challenge, events, look_up, pass_now, problems, question, reply, report,
                            reviewer_input, run,
                            say, until)


def test_a_plan_already_accepted_when_the_session_opens_is_reviewed_once(open_session):
    session = open_session(reviewer=[report(challenge())], review="auto")
    state = session.settle(SETTLE)
    assert [each["trigger"] for each in events(session, "review.started")] == ["loaded"]
    assert len(state["steps"][0]["challenges"]) == 1
    session.close()
    again = open_session(reviewer=[report(challenge(title="Another"))], review="auto")      # same database
    again.settle(SETTLE)
    assert events(again, "review.started")[-1]["pass"] == 1 and len(events(again, "review.started")) == 1


def test_review_off_starts_no_pass_by_itself(open_session):
    session = open_session(reviewer=[report(challenge())], review="off")
    session.queue("main", lambda work: (work.hook("plan_accepted", work), work.hook("plan_changed", work, ["c1"])),
                  what="tests")
    session.settle(SETTLE)
    assert events(session, "review.started") == [] and session.model_double.reviewer.calls == []


@pytest.mark.parametrize("hook, args, trigger", [("plan_accepted", (), "accepted"), ("plan_changed", (["c1"],), "plan_changed")])
def test_acceptance_and_a_plan_change_each_queue_a_pass(open_session, hook, args, trigger):
    session = open_session(reviewer=[report()], review="auto")
    session.settle(SETTLE)
    session.model_double.reviewer.script.append(report())
    session.queue("main", lambda work: work.hook(hook, work, *args), what="tests")
    session.settle(SETTLE)
    assert [each["trigger"] for each in events(session, "review.started")] == ["loaded", trigger]


def test_a_turn_with_a_new_assumption_starts_a_pass_and_an_old_one_does_not(open_session):
    ones = [run("total", {"a": 10, "b": 20}, ["Amount B stays at 20."]), reply("The total is 30.")]
    plain = [run("total", {"a": 10, "b": 20}), reply("The total is 30.")]
    session = open_session(analyst=ones + ones + plain, reviewer=[report(), report()], review="auto")
    session.settle(SETTLE)                                              # the pass at load
    say(session, "A is 10 and B is 20, what is the total?")
    assert [each["trigger"] for each in events(session, "review.started")] == ["loaded", "assumptions"]
    assert "Amount B stays at 20." in reviewer_input(session, 1)       # layer 4 had stored it by then
    say(session, "And again?")
    assert len(events(session, "review.started")) == 2                  # the same sentence is not new
    say(session, "Once more, with nothing assumed?")
    assert len(events(session, "review.started")) == 2                  # no assumption at all


def test_a_pass_asked_for_while_one_runs_is_one_more_not_many(open_session):
    import threading
    session = open_session(reviewer=[report(), report(), report(), report()])
    session.model_double.gate = threading.Event()
    reviewer.queue_pass(session, "tests")
    session.model_double.entered.wait(5)                                # the first is running
    for _ in range(3):
        reviewer.queue_pass(session, "tests")
    session.model_double.gate.set()
    session.settle(SETTLE)
    assert len(events(session, "review.finished")) == 2


def test_the_main_lane_is_never_held_up_by_a_pass(open_session):
    import threading
    session = open_session(analyst=[run("total", {"a": 10, "b": 20}), reply("The total is 30.")],
                           reviewer=[report(challenge())])
    session.model_double.gate = threading.Event()
    reviewer.queue_pass(session, "tests")
    session.model_double.entered.wait(5)
    state = session.state()
    assert state["lanes"]["review"] == "working" and state["review"]["running"] is True
    assert [each["what"] for each in state["activity"] if each["lane"] == "review"] == ["review"]
    session.act("say", {"text": "A is 10 and B is 20, what is the total?"})
    until(session, lambda s: s["lanes"]["main"] == "idle" and any(m["who"] == "assistant" for m in s["chat"]))
    assert session.lane("review") == "working"                          # the answer came while the pass waited
    session.model_double.gate.set()
    state = session.settle(SETTLE)
    assert state["review"] == {"open": 1, "running": False}


def test_a_failed_pass_is_an_error_on_the_review_lane_and_nothing_else(open_session):
    session = open_session(reviewer=[])                                  # the script is empty: the model call fails
    state = pass_now(session)
    assert state["error"] and state["lanes"] == {"main": "idle", "side": "idle", "review": "idle"}
    assert state["threads"] == [] and problems(state, strict=True) == []


def test_the_reviewer_has_a_context_of_its_own(open_session):
    session = open_session(analyst=[run("total", {"a": 10, "b": 20}, ["Amount B stays at 20."]),
                                    reply("The total is 30.")], reviewer=[report()])
    say(session, "Kindly work out a zebra total, A is 10 and B is 20.")
    pass_now(session)
    call = session.model_double.reviewer.calls[0]
    text = call["messages"][0]["content"]
    assert call["system"].startswith("You review how one person's personal finance plan")
    assert {tool.name for tool in call["tools"]} == {"look_up", "report"}
    assert len(call["messages"]) == 1
    for wanted in ("c1", "c2", "j1", "a + b", "Amount B stays at 20.", "unconfirmed", "Know the total", "2026-10-10",
                   "[today]", "[plan]", "[built specs]", "[assumptions]", "[decisions]", "[saved inputs]",
                   "[last runs]", "[earlier challenges]"):
        assert wanted in text
    assert "zebra" not in text and "def calculate" not in text           # not the main chat, never code
    assert "Amount B stays at 20." not in session.model_double.analyst.calls[0]["system"]


def test_what_it_was_told_about_earlier_challenges_and_replies_reaches_the_next_pass(open_session):
    session = open_session(reviewer=[report(challenge(title="One"), challenge(title="Two", step="c2"),
                                            question(title="Is B gross?")), report()])
    state = pass_now(session)
    _, dismissed, asked = [t["challenge"]["id"] for t in state["threads"]]
    session.act("dismiss_challenge", {"challenge": dismissed})
    threads = {t["challenge"]["id"]: t["id"] for t in session.state()["threads"]}
    session.post("It is before tax.", who="you", thread=threads[asked])
    pass_now(session)
    text = reviewer_input(session, 1)
    assert "dismissed" in text and "Two" in text and "It is before tax." in text and "Is B gross?" in text
    assert '"status": "open"' in text


def test_a_pass_makes_at_most_eight_model_calls_and_four_lookups(open_session):
    session = open_session(reviewer=[look_up(f"term {'abc'[n % 3]}x") for n in range(10)])
    pass_now(session)
    assert len(session.model_double.reviewer.calls) == 8
    assert len(events(session, "review.lookup")) == 4
    (finished,) = events(session, "review.finished")
    assert finished["kept"] == 0 and finished["reported"] is False


def test_a_reply_that_is_not_a_report_is_asked_once_more_then_the_pass_ends(open_session):
    session = open_session(reviewer=[{"text": "All fine."}, {"text": "All fine."}])
    pass_now(session)
    assert len(session.model_double.reviewer.calls) == 2
    assert events(session, "review.finished")[0]["reported"] is False
