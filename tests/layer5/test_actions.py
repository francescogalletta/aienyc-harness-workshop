"""SPEC 7.3: use this, dismiss, replying, the setting, and what the analyst is told about the reviewer."""
import pytest

from harness.core import BadAction
from layer5_helpers import (act, ask, challenge, chat_of, events, open_challenges, pass_now, problems, question, refused,
                            reply, report, run, say, step_of, threads_of, until)


def one_challenge(open_session, *more, **fields):
    session = open_session(*more[:1], reviewer=[report(challenge(**fields))]) if more else \
        open_session(reviewer=[report(challenge(**fields))])
    state = pass_now(session)
    return session, state, state["threads"][0]["challenge"]["id"]


def test_use_this_posts_the_persons_own_message_on_the_step_and_marks_both_used(open_session):
    session, state, cid = one_challenge(open_session, [reply("Understood.")], step="c2", change="plan",
                                        proposal="Count B only once.")
    applied, why = session.act("use_challenge", {"challenge": cid})
    assert applied, why
    state = session.settle(20)
    message = chat_of(state, "you")[-1]
    assert message["step"] == "c2" and "Count B only once." in message["text"] and "2" in message["text"]
    assert "Double" in message["text"]                                  # the step's number and name
    thread = threads_of(state)[0]
    assert thread["status"] == "used" and thread["challenge"]["status"] == "used"
    assert step_of(state, "c2")["challenges"] == [] and state["review"]["open"] == 0
    assert events(session, "review.used")[0]["challenge"] == cid
    assert any("Count B only once." in str(call["messages"]) for call in session.model_double.analyst.calls)
    assert problems(state, strict=True) == []


@pytest.mark.parametrize("change", ["assumption", "input"])
def test_using_a_correction_changes_nothing_by_itself(open_session, change):
    session, state, cid = one_challenge(open_session, [reply("I will ask.")], change=change,
                                        proposal="Run it again on a different value for B.")
    before = (session.conn.execute("SELECT COUNT(*) FROM assumptions").fetchone()[0],
              session.conn.execute("SELECT COUNT(*) FROM inputs").fetchone()[0],
              session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0])
    session.act("use_challenge", {"challenge": cid})
    session.settle(20)
    after = (session.conn.execute("SELECT COUNT(*) FROM assumptions").fetchone()[0],
             session.conn.execute("SELECT COUNT(*) FROM inputs").fetchone()[0],
             session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0])
    assert before == after                                              # only the analyst, on that message, may act


def test_the_analyst_is_told_how_to_treat_a_used_suggestion(open_session):
    session, state, cid = one_challenge(open_session, [reply("Done.")])
    session.act("use_challenge", {"challenge": cid})
    session.settle(20)
    assert "Suggestions from the reviewer" in session.model_double.analyst.calls[0]["system"]


def test_dismiss_closes_the_challenge_and_its_thread_and_later_passes_are_told(open_session):
    session = open_session(reviewer=[report(challenge()), report()])
    state = pass_now(session)
    cid = state["threads"][0]["challenge"]["id"]
    assert session.act("dismiss_challenge", {"challenge": cid}) == (True, "")
    state = session.state()
    assert state["threads"][0]["status"] == "dismissed" and state["threads"][0]["challenge"]["status"] == "dismissed"
    assert state["review"]["open"] == 0 and state["steps"][0]["challenges"] == []
    assert events(session, "review.dismissed")[0]["challenge"] == cid
    assert chat_of(state, "you") == []                                  # nothing is said in the main chat
    pass_now(session)
    assert '"status": "dismissed"' in session.model_double.reviewer.calls[0 + 1]["messages"][0]["content"]


def test_a_challenge_can_be_settled_only_once(open_session):
    session, state, cid = one_challenge(open_session, [reply("Ok.")])
    session.act("dismiss_challenge", {"challenge": cid})
    assert "dismissed" in refused(session, "dismiss_challenge", challenge=cid)
    assert refused(session, "use_challenge", challenge=cid)
    assert refused(session, "use_challenge", challenge="c99")


def test_a_bad_payload_is_a_bad_action(open_session):
    session = open_session()
    for payload in ({}, {"challenge": 3}, {"challenge": "x1"}):
        with pytest.raises(BadAction):
            session.act("dismiss_challenge", payload)


def test_a_question_is_answered_in_its_thread_not_used_and_the_next_pass_reads_the_answer(open_session):
    session = open_session(analyst=[reply("Noted, thank you.")], reviewer=[report(question()), report()])
    state = pass_now(session)
    cid, thread = state["threads"][0]["challenge"]["id"], state["threads"][0]["id"]
    assert "question" in refused(session, "use_challenge", challenge=cid)
    state = act(session, "side", text="It is before tax.", thread=thread)      # a reply is the side action (6.4)
    assert [m["who"] for m in state["threads"][0]["messages"]] == ["reviewer", "you", "assistant"]
    assert open_challenges(state)[0]["id"] == cid and state["chat"] == []     # nothing changes now, nothing in the chat
    pass_now(session)
    assert "It is before tax." in session.model_double.reviewer.calls[1]["messages"][0]["content"]
    assert session.act("dismiss_challenge", {"challenge": cid}) == (True, "")


def test_use_this_is_refused_while_the_main_lane_waits_for_a_decision(open_session):
    session = open_session(analyst=[ask("j1", "Is it enough?", ["Yes", "No"])], reviewer=[report(challenge())])
    state = pass_now(session)
    session.act("say", {"text": "Is it enough?"})
    until(session, lambda s: s["waiting"] and s["waiting"]["kind"] == "decision")
    assert "waiting" in refused(session, "use_challenge", challenge=state["threads"][0]["challenge"]["id"])


def test_a_review_thread_is_a_branch_of_the_reviewer_about_the_step(open_session):
    session, state, cid = one_challenge(open_session, [reply("Understood.")], step="c2")
    [thread] = threads_of(state)
    assert (thread["origin"], thread["subject"], thread["outcome"], thread["node"]) == (
        "reviewer", {"kind": "step", "step": "c2"}, "open", None)
    assert thread["from"] == state["history"]["latest"]                 # it left from the newest node


def test_use_this_records_challenge_used_and_joins_the_branch(open_session):
    session, state, cid = one_challenge(open_session, [reply("Understood.")], step="c2", change="plan",
                                        proposal="Count B only once.")
    thread_id = threads_of(state)[0]["id"]
    before = len(state["history"]["trunk"])
    state = act(session, "use_challenge", challenge=cid)
    nodes = [node for node in state["history"]["trunk"] if node["kind"] == "challenge_used"]
    assert len(state["history"]["trunk"]) == before + 1 and len(nodes) == 1
    [node] = nodes
    assert (node["who"], node["branch"], node["touched"]) == ("reviewer", thread_id, {"inputs": [], "steps": ["c2"]})
    assert node["text"] == "Reviewer's suggestion used on step 2"
    assert node["change"] == {"challenge": cid, "step": "c2", "change": "plan"}
    [thread] = threads_of(state)
    assert (thread["outcome"], thread["node"]) == ("joined", node["id"])
    assert node["after"] is None and chat_of(state, "you")             # recorded before the person's message
    assert step_of(state, "c2")["changed_by"] == node["id"]


def test_dismiss_makes_the_branch_dead_and_records_no_node(open_session):
    session, state, cid = one_challenge(open_session)
    before = state["history"]["trunk"]
    assert session.act("dismiss_challenge", {"challenge": cid}) == (True, "")
    state = session.state()
    [thread] = threads_of(state)
    assert (thread["outcome"], thread["node"], thread["status"]) == ("dead", None, "dismissed")
    assert state["history"]["trunk"] == before and events(session, "review.dismissed")[0]["challenge"] == cid


def test_a_question_branch_stays_open_until_it_is_dismissed(open_session):
    session = open_session(reviewer=[report(question())])
    state = pass_now(session)
    assert threads_of(state)[0]["outcome"] == "open"
    session.act("dismiss_challenge", {"challenge": state["threads"][0]["challenge"]["id"]})
    assert threads_of(session.state())[0]["outcome"] == "dead"
