"""ARCHITECTURE.md 3.5, 4.4 and 12.1: the trunk, the branch columns, `decide`, `set_outcome`, `history`,
`changed_by`, and the sample state of the decision graph. Layer 0 alone: nothing here relies on a real layer."""
import copy
import json
from pathlib import Path

import pytest

from harness import db
from harness.core import add_thread, decide, list_threads, list_trunk, set_outcome
from layer0_helpers import SETTLE, fake_layer
from state_shape import problems

SAMPLE = Path(__file__).parent / "states" / "decision_graph.json"


def events(session, kind) -> list[dict]:
    return [json.loads(row["payload"]) for row in db.list_events(session.conn, kind=kind)]


def sample() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_history_is_in_the_state_with_an_empty_trunk_at_layer_0(open_session):
    state = open_session().state()
    assert state["history"] == {"trunk": [], "latest": None}
    assert problems(state) == []


def test_decide_stores_a_node_after_the_last_main_message_and_records_it(open_session):
    session = open_session()
    session.post("one", who="you")
    last = session.post("two")
    node = session.decide(who="you", kind="value", text="Guest count: 120 → 150",
                          change={"input": "guest_count", "label": "Guest count", "from": "120", "to": "150",
                                  "runs": {}, "failed": []},
                          touched={"inputs": ["in:guest_count"], "steps": ["s1"]})
    assert node == "n1"
    history = session.state()["history"]
    assert history["latest"] == "n1"
    [found] = history["trunk"]
    assert (found["id"], found["who"], found["kind"], found["branch"], found["after"]) == ("n1", "you", "value", None, last)
    assert found["touched"] == {"inputs": ["in:guest_count"], "steps": ["s1"]}
    assert found["change"]["to"] == "150" and found["ts"]
    [event] = events(session, "core.decided")
    assert event == {"node": "n1", "kind": "value", "who": "you", "branch": None,
                     "touched": {"inputs": ["in:guest_count"], "steps": ["s1"]}}


def test_a_node_has_a_short_text_and_defaults_for_what_is_left_out(open_session):
    session = open_session()
    session.decide(who="harness", kind="plan_accepted", text="x" * 200)
    [found] = session.state()["history"]["trunk"]
    assert len(found["text"]) == 80
    assert found["change"] == {} and found["touched"] == {"inputs": [], "steps": []} and found["after"] is None


def test_decide_checks_who_kind_and_branch(open_session):
    session = open_session()
    with pytest.raises(ValueError):
        session.decide(who="nobody", kind="value", text="x")
    with pytest.raises(ValueError):
        session.decide(who="you", kind="no_such_kind", text="x")
    with pytest.raises(ValueError):
        session.decide(who="you", kind="value", text="x", branch="t9")
    assert list_trunk(session.conn, session.conversation) == []


def test_a_node_from_a_branch_joins_it(open_session):
    session = open_session()
    session.post("a question", who="you")
    first = add_thread(session.conn, session.conversation, kind="side", title="A branch", step="s1")
    other = add_thread(session.conn, session.conversation, kind="side", title="Another")
    node = session.decide(who="you", kind="value", text="Guest count: 120 → 150", branch=first)
    by_id = {thread["id"]: thread for thread in list_threads(session.conn, session.conversation)}
    assert (by_id[first]["outcome"], by_id[first]["node"]) == ("joined", node)
    assert (by_id[other]["outcome"], by_id[other]["node"]) == ("open", None)
    assert list_trunk(session.conn, session.conversation)[0]["branch"] == first
    assert events(session, "core.decided")[0]["branch"] == first


def test_a_thread_is_a_branch_that_leaves_from_the_newest_node(open_session):
    session = open_session()
    first = add_thread(session.conn, session.conversation, kind="side", title="before any node", step="s2")
    node = session.decide(who="you", kind="plan_accepted", text="Plan accepted")
    second = add_thread(session.conn, session.conversation, kind="review", title="after", origin="reviewer",
                        subject={"kind": "decision", "node": node})
    third = add_thread(session.conn, session.conversation, kind="side", title="plain")
    by_id = {thread["id"]: thread for thread in list_threads(session.conn, session.conversation)}
    assert (by_id[first]["origin"], by_id[first]["from"], by_id[first]["outcome"], by_id[first]["node"]) == (
        "you", None, "open", None)
    assert by_id[first]["subject"] == {"kind": "step", "step": "s2"}
    assert (by_id[second]["origin"], by_id[second]["from"]) == ("reviewer", node)
    assert by_id[second]["subject"] == {"kind": "decision", "node": node}
    assert by_id[third]["subject"] == {"kind": "plan"} and by_id[third]["from"] == node
    with pytest.raises(ValueError):
        add_thread(session.conn, session.conversation, kind="side", title="x", origin="somebody")


def test_set_outcome_makes_a_branch_dead_or_open_and_never_joins_it(open_session):
    session = open_session()
    thread = add_thread(session.conn, session.conversation, kind="side", title="A branch")
    set_outcome(session.conn, thread, "dead")
    assert list_threads(session.conn, session.conversation)[0]["outcome"] == "dead"
    set_outcome(session.conn, thread, "open")
    assert list_threads(session.conn, session.conversation)[0]["outcome"] == "open"
    for bad in ("joined", "gone"):
        with pytest.raises(ValueError):
            set_outcome(session.conn, thread, bad)
    with pytest.raises(ValueError):
        set_outcome(session.conn, "t99", "dead")


def test_work_decide_records_on_the_jobs_connection_and_changes_the_version(open_session):
    session = open_session()
    seen = {}

    def job(work):
        before = session.version
        seen["node"] = work.decide(who="assistant", kind="built", text="Built", change={"steps": {}, "why": "new"})
        seen["moved"] = session.version > before

    session.queue("main", job, what="answer")
    state = session.settle(SETTLE)
    assert seen == {"node": "n1", "moved": True}
    assert [node["who"] for node in state["history"]["trunk"]] == ["assistant"]
    assert session.version > 1


def test_a_new_conversation_has_its_own_trunk(open_session):
    session = open_session()
    session.decide(who="you", kind="plan_accepted", text="Plan accepted")
    session.new_conversation()
    assert session.state()["history"] == {"trunk": [], "latest": None}
    session.decide(who="you", kind="plan_accepted", text="Plan accepted again")
    assert [node["text"] for node in session.state()["history"]["trunk"]] == ["Plan accepted again"]


def test_changed_by_is_the_newest_node_that_touched_a_step_or_an_input(open_session):
    def contribute(view, state):
        state["steps"] = [{"id": "s1", "number": 1, "name": "One", "kind": "calculation", "open_questions": []},
                          {"id": "s2", "number": 2, "name": "Two", "kind": "calculation", "open_questions": []},
                          {"id": "s3", "number": 3, "name": "Three", "kind": "calculation", "open_questions": []}]
        state["inputs"] = {"in:guests": {"id": "in:guests"}, "in:price": {"id": "in:price"}}

    session = open_session(fake_layer(1, contribute=contribute))
    session.decide(who="you", kind="value", text="a", touched={"inputs": ["in:guests"], "steps": ["s1", "s2"]})
    session.decide(who="you", kind="value", text="b", touched={"inputs": [], "steps": ["s2"]})
    state = session.state()
    assert [step["changed_by"] for step in state["steps"]] == ["n1", "n2", None]
    assert {key: entry["changed_by"] for key, entry in state["inputs"].items()} == {"in:guests": "n1", "in:price": None}


def test_the_sample_state_has_a_joined_branch_a_dead_one_a_pending_proposal_and_four_kinds_of_chip():
    state = sample()
    assert problems(state) == []
    threads = {thread["id"]: thread for thread in state["threads"]}
    joined = [thread for thread in threads.values() if thread["outcome"] == "joined"]
    assert len(joined) == 1 and joined[0]["node"] == "n2"
    assert state["history"]["trunk"][1]["branch"] == joined[0]["id"] and state["history"]["latest"] == "n2"
    assert [thread["outcome"] for thread in threads.values() if thread["outcome"] == "dead"] == ["dead"]
    assert [thread["proposal"]["status"] for thread in threads.values() if thread["proposal"]
            and thread["outcome"] == "open"] == ["pending"]
    chips = [chip for message in state["chat"] for chip in message["chips"]]
    assert {chip["kind"] for chip in chips} == {"value", "assumption", "result", "decision"}
    assert state["steps"][0]["changed_by"] == "n2" and state["inputs"]["in:guest_count"]["changed_by"] == "n2"


def test_the_validator_notices_a_wrong_history():
    state = sample()
    broken = copy.deepcopy(state)
    broken["history"]["latest"] = "n1"
    broken["threads"][0]["node"] = None
    broken["threads"][1]["subject"] = {"kind": "somewhere"}
    broken["steps"][0]["changed_by"] = None
    broken["threads"][2]["origin"] = "somebody"
    found = problems(broken)
    assert any("latest is not the newest node" in line for line in found)
    assert any("outcome joined but node None" in line for line in found)
    assert any("unknown subject" in line for line in found)
    assert any("s1: changed_by" in line for line in found)
    assert any("origin" in line for line in found)
    broken = copy.deepcopy(state)
    chip = broken["chat"][-2]["chips"][0]
    chip["kind"], chip["subject"] = "number", {"kind": "value", "run": "r1"}
    broken["history"]["trunk"][1]["branch"] = "t2"
    del broken["inputs"]["in:guest_count"]["changed_by"]
    found = problems(broken)
    assert any("chips" in line for line in found)
    assert any("not joined" in line for line in found)
    assert any("changed_by" in line for line in found)


def test_the_validator_accepts_the_join_activity_and_a_harness_branch():
    state = sample()
    state["activity"] = [{"lane": "main", "what": "join", "step": "s2", "thread": "t3",
                          "text": "running step 2 again", "since": "2026-10-11T10:00:00+00:00"}]
    state["threads"][2]["kind"] = "harness"
    state["threads"][2]["origin"] = "harness"
    state["threads"][2]["messages"][0]["who"] = "harness"
    assert problems(state) == []
