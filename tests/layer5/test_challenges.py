"""SPEC 7.2: which challenges are kept, how they are ranked and capped, how they look in the state document
(ARCHITECTURE 3.3, 3.4), and the lookups behind them."""
import pytest

from layer5_helpers import (SOURCE, SINKING, FakeResearcher, challenge, events, look_up, open_challenges, pass_now,
                            problems, question, report, step_of, threads_of)


def test_a_kept_challenge_is_a_review_thread_and_a_count_on_its_step(open_session):
    session = open_session(reviewer=[report(challenge(step="c2", impact="high", change="plan"))])
    state = pass_now(session)
    (thread,) = threads_of(state)
    found = thread["challenge"]
    assert thread["step"] == "c2" and thread["status"] == "open" and thread["title"] == "Amount B may not hold"
    assert thread["after"] is None                              # no main-chat message yet to follow
    assert (found["step"], found["kind"], found["impact"], found["rank"], found["pass"], found["status"]) == \
        ("c2", "challenge", "high", 1, 1, "open")
    assert found["change"] == "plan" and found["sources"] == [] and found["id"] == "c1"
    first = thread["messages"][0]
    assert first["who"] == "reviewer" and "B is taken as fixed." in first["text"]
    assert "Proposed: Ask whether B can change." in first["text"] and first["sources"] == []
    assert step_of(state, "c2")["challenges"] == [found["id"]] and step_of(state, "c1")["challenges"] == []
    assert [(mark["symbol"], mark["count"]) for mark in step_of(state, "c2")["marks"]] == [("▲", 1)]
    assert state["review"] == {"open": 1, "running": False}
    assert problems(state, strict=True) == []
    (kept,) = events(session, "review.kept")
    assert kept["challenge"] == "c1" and kept["step"] == "c2" and kept["pass"] == 1


def test_a_thread_follows_the_last_main_message_when_it_starts(open_session):
    from layer5_helpers import say
    session = open_session(analyst=[{"text": "Hello."}], reviewer=[report(challenge())])
    state = say(session, "Hi")
    last = state["chat"][-1]["id"]
    assert threads_of(pass_now(session))[0]["after"] == last


DROPPED = [
    ("unknown_step", challenge(step="zz")),
    ("bad_title", challenge(title="")),
    ("bad_value", challenge(impact="huge")),
    ("bad_question", {**question(), "proposal": "Ask them."}),
    ("no_proposal", challenge(proposal="")),
    ("number_unbacked", challenge(concern="B is probably 31,415 in truth.")),
    ("source_not_fetched", challenge(sources=["https://example.org/never-fetched"])),
    ("source_not_fetched", challenge(concern="Wikipedia says this is unusual.")),
]


@pytest.mark.parametrize("reason, raw", DROPPED)
def test_a_challenge_that_fails_a_check_is_dropped_with_its_reason(open_session, reason, raw):
    session = open_session(reviewer=[report(raw)])
    state = pass_now(session)
    assert state["threads"] == [] and state["review"]["open"] == 0
    assert [each["reason"] for each in events(session, "review.dropped")] == [reason]
    assert events(session, "review.finished")[0]["dropped"] == 1


def test_a_number_the_plan_or_the_person_gave_is_not_made_up(open_session):
    from layer5_helpers import reply, run, say
    session = open_session(analyst=[run("total", {"a": 10, "b": 20}), reply("The total is 30.")],
                           reviewer=[report(challenge(concern="The total of 30 rests on B being 20."))])
    say(session, "A is 10 and B is 20, what is the total?")
    assert len(threads_of(pass_now(session))) == 1


def test_a_challenge_that_repeats_an_open_used_or_dismissed_one_is_dropped(open_session):
    session = open_session(reviewer=[report(challenge(title="One"), challenge(title="Two"), challenge(title="Three")),
                                     report(challenge(title="  one "), challenge(title="TWO"),
                                            challenge(title="three"), challenge(title="Four"))])
    state = pass_now(session)
    ids = [thread["challenge"]["id"] for thread in state["threads"]]
    session.act("dismiss_challenge", {"challenge": ids[1]})
    session.act("use_challenge", {"challenge": ids[2]})
    state = pass_now(session)
    assert [t["title"] for t in threads_of(state)] == ["One", "Two", "Three", "Four"]
    assert [each["reason"] for each in events(session, "review.dropped")] == ["repeat"] * 3


def test_the_same_title_on_another_step_is_not_a_repeat(open_session):
    session = open_session(reviewer=[report(challenge(step="c1"), challenge(step="c2"), challenge(step="c2"))])
    state = pass_now(session)
    assert [t["step"] for t in threads_of(state)] == ["c1", "c2"]


def test_a_pass_keeps_three_ranked_by_impact_then_the_reviewers_order(open_session):
    raw = [challenge(title=f"{impact} {n}", impact=impact)
           for n, impact in enumerate(["low", "medium", "high", "medium", "high"])]
    session = open_session(reviewer=[report(*raw)])
    state = pass_now(session)
    kept = [(t["title"], t["challenge"]["rank"]) for t in threads_of(state)]
    assert kept == [("high 2", 1), ("high 4", 2), ("medium 1", 3)]
    assert [each["reason"] for each in events(session, "review.dropped")] == ["over_cap"] * 2
    assert step_of(state, "c1")["challenges"] == ["c1", "c2", "c3"]


def test_with_three_open_a_pass_keeps_two_and_with_five_open_it_keeps_none(open_session):
    def named(*titles):
        return report(*[challenge(title=title) for title in titles])

    session = open_session(reviewer=[named("a", "b", "c"), named("d", "e"), named("f")])
    assert len(open_challenges(pass_now(session))) == 3
    assert len(open_challenges(pass_now(session))) == 5                 # room for two more: both are kept
    state = pass_now(session)
    assert len(open_challenges(state)) == 5 and "f" not in [t["title"] for t in threads_of(state)]
    assert events(session, "review.dropped")[-1]["reason"] == "too_many_open"


def test_the_sources_of_a_kept_challenge_are_the_ones_a_lookup_returned(open_session):
    fake = FakeResearcher(SINKING)
    session = open_session(researcher=fake, reviewer=[
        look_up("sinking fund"),
        report(challenge(concern="A sinking fund is money set aside on a schedule.", sources=[SOURCE["url"]]))])
    state = pass_now(session)
    (thread,) = threads_of(state)
    assert thread["challenge"]["sources"] == [SOURCE] and thread["messages"][0]["sources"] == [SOURCE]
    (lookup,) = events(session, "review.lookup")
    assert lookup["status"] == "found" and lookup["sources"] == [SOURCE] and lookup["query"] == "sinking fund"
    assert events(session, "review.kept")[0]["sources"] == [SOURCE["url"]]
    assert problems(state, strict=True) == []


def test_only_a_general_question_goes_out_and_a_figure_never_does(open_session):
    fake = FakeResearcher(SINKING)
    session = open_session(researcher=fake, reviewer=[look_up("sinking fund for 43000 euros"), look_up("sinking fund"),
                                                      report()])
    pass_now(session)
    assert fake.asked == ["sinking fund"]
    refused_one = events(session, "review.lookup")[0]
    assert refused_one["status"] == "failed" and refused_one["sources"] == []
    result = session.model_double.reviewer.calls[1]["messages"][-1]
    assert result["role"] == "tool" and result["is_error"]              # the reviewer was told no


def test_when_lookups_fail_the_reviewer_goes_on_without_a_source(open_session):
    fake = FakeResearcher(broken=True)
    session = open_session(researcher=fake, reviewer=[
        look_up("sinking fund"),
        report(challenge(title="Reasoned", sources=[]), challenge(title="Cited", sources=[SOURCE["url"]]))])
    state = pass_now(session)
    assert [t["title"] for t in threads_of(state)] == ["Reasoned"]      # no source fetched: the cited one is dropped
    assert events(session, "review.lookup")[0]["status"] == "failed"
    assert [each["reason"] for each in events(session, "review.dropped")] == ["source_not_fetched"]


def test_a_question_has_no_proposal_and_is_a_thread_like_any_challenge(open_session):
    session = open_session(reviewer=[report(question())])
    state = pass_now(session)
    found = threads_of(state)[0]["challenge"]
    assert (found["kind"], found["proposal"], found["change"]) == ("question", "", "none")
    assert "Proposed" not in threads_of(state)[0]["messages"][0]["text"]
    assert problems(state, strict=True) == []


def test_the_replay_expectation_counts_challenges_raised_and_their_steps(open_session):
    from harness.review.layer import LAYER
    expect = LAYER.expects["challenges"]
    session = open_session(reviewer=[report(challenge(step="c2"), challenge(title="Other", step="c2"))])
    pass_now(session)
    session.act("dismiss_challenge", {"challenge": "c1"})
    seen = expect.check({"min": 2, "max": 2, "steps": ["c2"]}, session)
    assert seen["passed"] and "2 challenges" in seen["seen"]                 # dismissed ones were raised too
    assert not expect.check({"steps": ["c1"]}, session)["passed"]
    assert expect.validate({"min": 1}) is None
    assert expect.validate({}) and expect.validate({"min": -1}) and expect.validate({"steps": "c1"})


def test_without_an_accepted_plan_a_pass_does_nothing(open_session, tmp_path):
    session = open_session(reviewer=[report(challenge())])
    (tmp_path / "brief" / "domain_brief.json").unlink()
    state = pass_now(session)
    assert events(session, "review.started") == [] and state["threads"] == []
    assert session.model_double.reviewer.calls == []
