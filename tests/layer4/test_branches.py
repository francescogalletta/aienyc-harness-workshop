"""SPEC 6.4 and 6.6, ARCHITECTURE.md 3.5, 4.4, 5, 6 and 12: branches on a subject, the side assistant's
`propose_change`, proposals, the join (save the input, run again with no model call, a trunk node, the branch
joined), the death rule, decision chips and assumption-chip status.

Written from the contract alone. The small plan gains two plan inputs, `A` and `B`, so that `in:a` and `in:b` are
plan inputs named as the module `total` keys them (no step needs them: a step that changed would be stale);
`double` takes the total. Replies the side assistant
is scripted to give carry no digits, so the number check never touches them."""
import json
import re
from decimal import Decimal

import pytest

from harness.config import load_config
from harness.core import BadAction, Session, add_thread
from harness.model import ScriptedModel
from layer4_helpers import SETTLE, act, ask, call, events, notices, problems, refused, reply, run, say, step_of

SIDE_START = "You help one person understand"
OPTIONS = ["Keep it at 30", "Raise it"]

ASKED = "A is 10 and B is 20, what is twice the total?"
MAIN = [run("total", {"a": 10, "b": 20}), run("double", {"total": 30}), reply("The total is 30 and twice that is 60.")]
VALUE = {"kind": "value", "run": "r1", "key": "a", "value": "10", "input": "in:a", "step": "c1"}
INPUT = {"kind": "input", "input": "in:a", "step": "c1"}
FIFTY = "A will be no less than 50."
WORDS = "no less than 50"
ACK = "I have put that to you as a change. Say yes or no under it."


def propose(value="50", words=WORDS, *, input="a"):
    return call("propose_change", kind="value", input=input, value=value, step="", words=words)


def propose_plan(step, words):
    return call("propose_change", kind="plan", input="", value="", step=step, words=words)


class Routed:
    """One model for the session: the side assistant's calls go to `side`, every other to `main`."""

    def __init__(self, main, side):
        self.main, self.side = main, side

    def complete(self, *, system, messages, tools=()):
        target = self.side if system.startswith(SIDE_START) else self.main
        return target.complete(system=system, messages=messages, tools=tools)


@pytest.fixture
def keyed(world, tmp_path):
    """The small world with two more plan inputs, `A` and `B`: the ids `in:a` and `in:b`."""
    path = tmp_path / "brief" / "domain_brief.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["inputs"] += [{"name": name, "description": f"the {name}", "origin": {"kind": "proposed"}}
                       for name in ("A", "B")]
    path.write_text(json.dumps(plan), encoding="utf-8")
    return world


@pytest.fixture
def routed(keyed):
    opened = []

    def make(side=(), main=MAIN, *, ask_first=True):
        model = Routed(ScriptedModel(main), ScriptedModel(side))
        session = Session(load_config(), model_factory=lambda: model)
        session.models = model
        session.memory["today"] = "2026-10-10"
        opened.append(session)
        session.settle(SETTLE)
        if ask_first:
            say(session, ASKED)
        return session

    yield make
    for session in opened:
        session.close()


# --- helpers ---

def branch(session, text, subject=None, **more):
    payload = {"text": text, **({"subject": subject} if subject is not None else {}), **more}
    state = act(session, "side", **payload)
    return state["threads"][-1], state


def thread_of(session, thread):
    return next(each for each in session.state()["threads"] if each["id"] == thread)


def proposal_of(session, thread):
    return thread_of(session, thread)["proposal"]


def proposed(session, subject=VALUE, text=FIFTY):
    """A branch with a pending proposal to make `a` 50."""
    found, _ = branch(session, text, subject)
    assert found["proposal"] is not None and found["proposal"]["status"] == "pending"
    return found["id"]


def runs_count(session):
    return session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0]


def runs_after(session, last):
    rows = session.conn.execute("SELECT * FROM calc_runs WHERE id > ? ORDER BY id", (last,)).fetchall()
    return [{"id": row["id"], "module": row["module"], "inputs": json.loads(row["inputs"]),
             "output": json.loads(row["output"]), "assumptions": json.loads(row["assumptions"])} for row in rows]


def trunk(state):
    return state["history"]["trunk"]


def number(text):
    return Decimal(str(text).replace(",", ""))


def tool_results(session):
    return [m for m in session.models.side.calls[-1]["messages"] if m["role"] == "tool"]


def refusal_reasons(session):
    return [each["reason"] for each in events(session, "you.proposal_refused")]


def join_value(session, thread, proposal="p1"):
    """Accept; returns the state, the node and the runs the join made."""
    last = session.conn.execute("SELECT MAX(id) FROM calc_runs").fetchone()[0]
    state = act(session, "accept_proposal", proposal=proposal)
    node = trunk(state)[-1]
    return state, node, runs_after(session, last)


# --- Opening a branch on a subject (6.4) ---

def test_a_branch_opens_on_each_kind_of_subject_and_keeps_it(routed):
    session = routed(side=[reply("It is about that.")] * 7, main=[
        run("total", {"a": 10, "b": 20}, ["B stays at 20."]), run("double", {"total": 30}),
        reply("The total is 30 and twice that is 60.")])
    assumption = step_of(session.state(), "c1")["unconfirmed"][0]["id"]
    subjects = [{"kind": "plan"}, {"kind": "step", "step": "c2"}, INPUT, VALUE,
                {"kind": "result", "run": "r2", "step": "c2", "value": "60"},
                {"kind": "assumption", "run": "r1", "step": "c1", "text": "B stays at 20.", "assumption": assumption},
                {"kind": "decision", "node": "n1"}]
    for subject in subjects:
        found, state = branch(session, "Tell me about this.", subject)
        assert found["subject"] == subject
        assert found["step"] == subject.get("step")
        assert (found["kind"], found["origin"], found["outcome"], found["node"]) == ("side", "you", "open", None)
        assert found["from"] == "n1"                      # the newest node when it opened
        assert found["proposal"] is None
    assert len(state["threads"]) == len(subjects)
    assert problems(state, strict=True) == []
    assert len(trunk(state)) == 1                          # opening a branch decides nothing


def test_without_a_subject_the_branch_is_about_the_step_else_the_whole_plan(routed):
    session = routed(side=[reply("One."), reply("Two.")])
    attached, _ = branch(session, "What is this step?", step="c2")
    assert attached["subject"] == {"kind": "step", "step": "c2"} and attached["step"] == "c2"
    whole, state = branch(session, "What is this plan?")
    assert whole["subject"] == {"kind": "plan"} and whole["step"] is None
    assert problems(state, strict=True) == []


def test_a_subject_whose_ids_do_not_exist_is_a_bad_action_and_opens_nothing(routed):
    session = routed(side=[])
    bad = [{"kind": "step", "step": "zz"},
           {"kind": "input", "input": "in:nothing", "step": None},
           {"kind": "value", "run": "r99", "key": "a", "value": "10", "input": None, "step": None},
           {"kind": "result", "run": "r99", "step": None, "value": "1"},
           {"kind": "assumption", "run": "r1", "step": "c1", "text": "none", "assumption": "a99"},
           {"kind": "decision", "node": "n99"},
           {"kind": "nonsense"}, "plan"]
    for subject in bad:
        with pytest.raises(BadAction):
            session.act("side", {"text": "What is this?", "subject": subject})
    state = session.state()
    assert state["threads"] == [] and session.models.side.calls == []


# --- Proposals (12.3, 6.6) ---

def test_the_side_assistant_proposes_through_its_tool_and_the_proposal_is_on_the_thread(routed):
    session = routed(side=[propose(), reply(ACK)])
    found, state = branch(session, FIFTY, VALUE)
    proposal = found["proposal"]
    assert proposal["id"] == "p1" and proposal["status"] == "pending" and proposal["node"] is None
    assert proposal["reason"] == "" and proposal["words"] == WORDS
    assert proposal["change"] == {"kind": "value", "input": "a", "label": state["inputs"]["in:a"]["name"],
                                  "from": "10", "to": "50"}
    assert isinstance(proposal["text"], str) and "10" in proposal["text"] and "50" in proposal["text"]
    assert proposal["impact"] == {"inputs": ["in:a"], "runs": ["r1", "r2"], "steps": ["c1", "c2"],
                                  "downstream": ["c3", "j1"]}
    assert problems(state, strict=True) == []
    results = tool_results(session)
    assert len(results) == 1 and not results[0].get("is_error")
    (event,) = events(session, "you.proposed")
    assert {"thread", "proposal", "change", "impact"} <= set(event) and event["thread"] == found["id"]
    assert found["messages"][-1]["who"] == "assistant"
    assert runs_count(session) == 2 and session.state()["inputs"]["in:a"]["value"] is None      # it applied nothing
    assert len(trunk(state)) == 1


def test_the_impact_of_a_value_no_run_used_has_no_runs_and_no_old_value(routed):
    session = routed(side=[propose(), reply(ACK)], main=[run("double", {"total": 30}), reply("Twice that is 60.")],
                     ask_first=False)
    say(session, "The total is 30. What is twice it?")
    found, state = branch(session, FIFTY, INPUT)
    assert found["proposal"]["change"]["from"] is None
    assert found["proposal"]["impact"] == {"inputs": ["in:a"], "runs": [], "steps": [], "downstream": []}
    assert problems(state, strict=True) == []


def test_a_plan_proposal_names_a_step_or_none(routed):
    session = routed(side=[propose_plan("c1", "include a fee"), reply(ACK), propose_plan("", "include a fee"), reply(ACK)])
    found, state = branch(session, "The total should include a fee.", {"kind": "step", "step": "c1"})
    proposal = found["proposal"]
    assert proposal["status"] == "pending" and proposal["change"]["kind"] == "plan" and proposal["change"]["step"] == "c1"
    assert proposal["words"] == "include a fee" and proposal["text"]
    state = act(session, "side", text="It should include a fee, in the whole plan.", thread=found["id"])
    assert state["threads"][0]["proposal"]["change"]["step"] is None
    assert problems(state, strict=True) == []


def test_words_the_person_did_not_write_in_this_branch_are_refused_and_come_first(routed):
    session = routed(side=[propose(words="A is 10 and B is 20, what is twice the total?"), reply("I cannot propose that."),
                           propose(input="zzz", words="something never said"), reply("I cannot propose that.")])
    found, state = branch(session, "Can A change?", VALUE)         # the words are the main chat's, not this branch's
    assert found["proposal"] is None
    assert tool_results(session)[0]["is_error"] is True
    state = act(session, "side", text="Say it differently.", thread=found["id"])
    assert state["threads"][0]["proposal"] is None
    assert refusal_reasons(session) == ["not_their_words", "not_their_words"]      # before unknown_input
    assert {"thread", "reason", "change"} <= set(events(session, "you.proposal_refused")[0])
    assert runs_count(session) == 2 and len(trunk(state)) == 1


def test_a_value_the_person_never_said_in_this_branch_is_refused(routed):
    session = routed(
        main=MAIN + [reply("Noted.")],
        side=[propose(words="A will be higher"), reply("I need the figure from you."),
              propose(words="plus 40 more"), reply("I need the figure from you.")])
    say(session, "Maybe I will have 50 for A.")
    found, _ = branch(session, "A will be higher.", VALUE)           # 50 was said in the main chat, not here
    assert found["proposal"] is None
    state = act(session, "side", text="A is 10 plus 40 more.", thread=found["id"])       # 50 is worked out, not said
    assert state["threads"][0]["proposal"] is None
    assert refusal_reasons(session) == ["value_unbacked", "value_unbacked"]
    assert all(result["is_error"] for result in tool_results(session))


def test_the_other_refusals_each_have_their_reason(routed):
    session = routed(side=[propose(input="zzz"), reply("No."),
                           propose(value="10", words="Keep A at 10"), reply("No."),
                           propose_plan("zz", "add a new step"), reply("No.")])
    found, _ = branch(session, "A will be no less than 50.", VALUE)
    act(session, "side", text="Keep A at 10.", thread=found["id"])
    state = act(session, "side", text="Please add a new step.", thread=found["id"])
    assert refusal_reasons(session) == ["unknown_input", "same", "unknown_step"]
    assert state["threads"][0]["proposal"] is None and problems(state, strict=True) == []


def test_a_value_with_two_old_values_in_the_last_answer_is_ambiguous(routed):
    ranged = [run("total", {"a": 10, "b": 20}), run("total", {"a": 40, "b": 20}),
              reply("The totals are 30 and 60.")]
    session = routed(main=ranged, side=[propose(), reply("Which one do you mean?")], ask_first=False)
    say(session, "A is 10 or 40, and B is 20. What are the totals?")
    found, state = branch(session, FIFTY)                            # a plan branch: no subject value to take it from
    assert found["proposal"] is None and refusal_reasons(session) == ["ambiguous"]
    assert tool_results(session)[0]["is_error"] is True and problems(state, strict=True) == []


def test_only_one_proposal_is_taken_per_reply(routed):
    twice = {"tool_calls": [propose()["tool_calls"][0], propose(value="60", words="no more than 60")["tool_calls"][0]]}
    session = routed(side=[twice, reply(ACK)])
    found, _ = branch(session, "A will be no less than 50 and no more than 60.", VALUE)
    assert found["proposal"]["change"]["to"] == "50"
    assert refusal_reasons(session) == ["one_per_reply"]
    assert [bool(result.get("is_error")) for result in tool_results(session)] == [False, True]
    assert session.conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 1


def test_a_new_proposal_replaces_the_pending_one(routed):
    session = routed(side=[propose(), reply(ACK), propose(value="60", words="no more than 60"), reply(ACK)])
    found, _ = branch(session, FIFTY, VALUE)
    state = act(session, "side", text="Make it no more than 60 instead.", thread=found["id"])
    assert state["threads"][0]["proposal"]["id"] == "p2" and state["threads"][0]["proposal"]["status"] == "pending"
    assert state["threads"][0]["proposal"]["change"]["to"] == "60"
    statuses = [row["status"] for row in session.conn.execute("SELECT status FROM proposals ORDER BY id")]
    assert statuses == ["replaced", "pending"]
    assert refused(session, "accept_proposal", proposal="p1")           # a replaced proposal cannot be accepted


def test_propose_change_is_offered_only_in_a_side_branch_of_an_accepted_plan(routed, tmp_path):
    session = routed(side=[reply("Yes."), reply("Yes.")])
    branch(session, "Hello there.", VALUE)
    assert {"look_up", "propose_change"} <= {tool.name for tool in session.models.side.calls[-1]["tools"]}
    review = add_thread(session.conn, session.conversation, kind="review", title="A challenge", step="c1",
                        origin="reviewer", subject={"kind": "step", "step": "c1"})
    session.post("Is the plan too tight?", who="reviewer", thread=review)
    act(session, "side", text="What does that mean?", thread=review)
    assert "propose_change" not in {tool.name for tool in session.models.side.calls[-1]["tools"]}


def test_propose_change_is_not_offered_before_the_plan_is_accepted(tmp_path):
    model = ScriptedModel([reply("A running balance is what is left after each payment.")])
    session = Session(load_config(), model_factory=lambda: model)
    try:
        assert session.state()["phase"] == "empty"
        act(session, "side", text="What is a running balance?")
        assert "propose_change" not in {tool.name for tool in model.calls[-1]["tools"]}
    finally:
        session.close()


# --- Yes: the join (12.3, 12.4) ---

def test_yes_saves_the_input_and_runs_the_affected_runs_again_with_no_model_call(routed):
    from harness.answers import agent, rerun

    session = routed(side=[propose(), reply(ACK)])
    thread = proposed(session)
    main_calls, side_calls = len(session.models.main.calls), len(session.models.side.calls)
    before = runs_count(session)
    last = session.conn.execute("SELECT MAX(id) FROM calc_runs").fetchone()[0]
    state = act(session, "accept_proposal", proposal="p1")
    assert (len(session.models.main.calls), len(session.models.side.calls)) == (main_calls, side_calls)
    saved = agent.saved_inputs(session.conn)["a"]
    assert saved["value"] == "50" and saved["note"].startswith("on a branch") and WORDS in saved["note"]
    assert state["inputs"]["in:a"]["value"] == "50"
    first, second = runs_after(session, last)
    assert runs_count(session) == before + 2
    assert (first["module"], first["inputs"]) == ("total", {"a": "50", "b": "20"})
    assert (second["module"], second["inputs"]) == ("double", {"total": "70"})
    assert number(first["output"]) == 70 and number(second["output"]) == 140
    assert number(step_of(state, "c1")["last_run"]["output"]) == 70
    assert number(step_of(state, "c2")["last_run"]["output"]) == 140
    assert rerun.last_answer_runs(session.conn, session.conversation) == [first["id"], second["id"]]
    assert state["lanes"]["main"] == "idle" and state["activity"] == []
    assert proposal_of(session, thread)["status"] == "accepted"
    assert problems(state, strict=True) == []


def test_yes_posts_the_join_notice_with_a_decision_chip_and_the_new_results(routed):
    session = routed(side=[propose(), reply(ACK)])
    thread = proposed(session)
    first_answer = [m for m in session.state()["chat"] if m["who"] == "assistant"][-1]
    state, node, new = join_value(session, thread)
    notice = state["chat"][-1]
    assert notice["who"] == "harness" and notice["id"] != first_answer["id"]
    assert "50" in notice["text"] and "10" in notice["text"]
    chips = notice["chips"]
    assert [chip["kind"] for chip in chips] == ["decision", "value", "result", "result"]   # B did not change
    assert (chips[0]["label"], chips[0]["text"], chips[0]["subject"]) == ("Decided", node["text"],
                                                                         {"kind": "decision", "node": node["id"]})
    assert (chips[1]["label"], chips[1]["text"]) == ("A", "50 (was 10)")
    assert chips[1]["subject"]["run"] == f"r{new[0]['id']}" and chips[1]["subject"]["input"] == "in:a"
    assert [chip["label"] for chip in chips[2:]] == ["Total", "Double"]
    assert [chip["text"] for chip in chips[2:]] == ["70 (was 30)", "140 (was 60)"]
    assert [chip["subject"]["run"] for chip in chips[2:]] == [f"r{each['id']}" for each in new]
    again = next(m for m in state["chat"] if m["id"] == first_answer["id"])
    assert [chip["text"] for chip in again["chips"] if chip["kind"] == "value"] == ["10", "20"]      # the old ones stay
    assert problems(state, strict=True) == []


def test_yes_records_a_value_node_joins_the_branch_and_marks_what_it_changed(routed):
    session = routed(side=[propose(), reply(ACK)])
    thread = proposed(session)
    state, node, new = join_value(session, thread)
    assert (node["who"], node["kind"], node["branch"]) == ("you", "value", thread)
    assert node["text"] == "A: 50 (was 10)" and len(node["text"]) <= 80
    assert node["touched"] == {"inputs": ["in:a"], "steps": ["c1", "c2"]}
    assert node["change"] == {"input": "a", "label": "A", "from": "10", "to": "50",
                              "runs": {"r1": f"r{new[0]['id']}", "r2": f"r{new[1]['id']}"}, "failed": []}
    assert state["history"]["latest"] == node["id"] and len(trunk(state)) == 2
    found = thread_of(session, thread)
    assert (found["outcome"], found["node"]) == ("joined", node["id"])
    assert found["proposal"]["status"] == "accepted" and found["proposal"]["node"] == node["id"]
    assert [step_of(state, step)["changed_by"] for step in ("c1", "c2", "c3", "j1")] == [node["id"], node["id"], None, None]
    assert state["inputs"]["in:a"]["changed_by"] == node["id"] and state["inputs"]["in:b"]["changed_by"] is None
    (accepted,) = events(session, "you.proposal_accepted")
    assert (accepted["thread"], accepted["proposal"]) == (thread, "p1")
    (joined,) = events(session, "you.joined")
    assert (joined["thread"], joined["proposal"]) == (thread, "p1") and {"node", "runs", "failed"} <= set(joined)
    decided = events(session, "core.decided")[-1]
    assert (decided["kind"], decided["who"], decided["branch"]) == ("value", "you", thread)


def test_the_analyst_is_told_what_was_decided_before_the_next_message(routed):
    session = routed(side=[propose(), reply(ACK)], main=MAIN + [reply("Anything else?")])
    thread = proposed(session)
    join_value(session, thread)
    say(session, "Thanks.")
    sent = session.models.main.calls[-1]["messages"][-1]["content"]
    assert "[harness]" in sent and WORDS in sent and "Thanks." in sent
    assert "total gives" in sent and "double gives" in sent
    assert not re.search(r"\br\d+\b", sent)                              # never a run id


def test_a_branch_on_an_assumption_corrects_it_and_the_runs_do_not_carry_it(routed):
    sentence = "B stays at 20."
    session = routed(
        main=[run("total", {"a": 10, "b": 20}, [sentence]), run("double", {"total": 30}),
              reply("The total is 30 and twice that is 60.")],
        side=[propose(input="b", value="25", words="B will be 25"), reply(ACK)])
    state = session.state()
    assumption = step_of(state, "c1")["unconfirmed"][0]["id"]
    subject = {"kind": "assumption", "run": "r1", "step": "c1", "text": sentence, "assumption": assumption}
    found, _ = branch(session, "B will be 25.", subject)
    assert found["proposal"]["change"]["from"] == "20" and found["proposal"]["change"]["to"] == "25"
    state, node, new = join_value(session, found["id"])
    assert (new[0]["module"], new[0]["inputs"]) == ("total", {"a": "10", "b": "25"}) and new[0]["assumptions"] == []
    row = session.conn.execute("SELECT status, words FROM assumptions").fetchone()
    assert row["status"] == "corrected" and "B will be 25" in row["words"]
    answer = next(m for m in state["chat"] if m["who"] == "assistant")
    (chip,) = [chip for chip in answer["chips"] if chip["kind"] == "assumption"]
    assert (chip["status"], chip["subject"]["assumption"]) == ("corrected", assumption)
    assert step_of(state, "c1")["unconfirmed"] == [] and step_of(state, "c1")["marks"] == []
    assert node["kind"] == "value" and thread_of(session, found["id"])["outcome"] == "joined"


def test_a_value_no_run_used_is_saved_and_joined_with_nothing_run_again(routed):
    session = routed(side=[propose(), reply(ACK)], main=[run("double", {"total": 30}), reply("Twice that is 60.")],
                     ask_first=False)
    say(session, "The total is 30. What is twice it?")
    found, _ = branch(session, FIFTY, INPUT)
    before = runs_count(session)
    state, node, new = join_value(session, found["id"])
    assert new == [] and runs_count(session) == before
    assert state["inputs"]["in:a"]["value"] == "50"
    assert node["kind"] == "value" and node["touched"] == {"inputs": ["in:a"], "steps": []}
    assert node["change"]["from"] is None and node["change"]["to"] == "50"
    notice = state["chat"][-1]
    assert notice["who"] == "harness" and "result" not in [chip["kind"] for chip in notice["chips"]]
    assert notice["chips"][0]["kind"] == "decision"
    assert thread_of(session, found["id"])["outcome"] == "joined"


def test_a_run_the_gate_refuses_is_reported_and_the_value_is_still_saved_and_joined(routed):
    from harness.answers import agent, rerun

    session = routed(side=[propose(value="lots", words="will be lots"), reply(ACK)])
    found, _ = branch(session, "A will be lots.", VALUE)
    assert found["proposal"]["status"] == "pending"
    before = runs_count(session)
    state, node, new = join_value(session, found["id"])
    assert new == [] and runs_count(session) == before
    assert agent.saved_inputs(session.conn)["a"]["value"] == "lots"
    failed = node["change"]["failed"]
    assert [(each["run"], each["step"]) for each in failed] == [("r1", "c1"), ("r2", "c2")]
    assert failed[0]["reason"] and failed[1]["reason"] == "an earlier step could not run again"
    assert node["change"]["runs"] == {} and node["touched"]["steps"] == []
    assert thread_of(session, found["id"])["outcome"] == "joined"
    assert rerun.last_answer_runs(session.conn, session.conversation) == [1, 2]
    (joined,) = events(session, "you.joined")
    assert len(joined["failed"]) == 2
    assert problems(state, strict=True) == []


def test_yes_is_refused_while_a_decision_waits_and_works_once_it_is_answered(routed):
    session = routed(side=[propose(), reply(ACK)],
                     main=MAIN + [ask("j1", "Is 30 enough?", OPTIONS, runs=[1]), reply("Noted.")])
    thread = proposed(session)
    state = say(session, "Decide for me: is it enough?")
    assert state["waiting"]["kind"] == "decision"
    assert refused(session, "accept_proposal", proposal="p1")
    assert proposal_of(session, thread)["status"] == "pending" and runs_count(session) == 2
    state = session.state()
    decision = next(m for m in state["chat"] if m["kind"] == "decision")["decision"]
    act(session, "choose", decision=decision["id"], option=1)
    assert thread_of(session, thread)["outcome"] == "open"               # a pending proposal keeps its branch open
    state = act(session, "accept_proposal", proposal="p1")
    assert thread_of(session, thread)["outcome"] == "joined" and runs_count(session) > 2


def test_a_joined_branch_stays_joined_and_a_later_accepted_proposal_records_another_node(routed):
    session = routed(side=[propose(), reply(ACK), reply("Of course."),
                           propose(value="60", words="at most 60"), reply(ACK)])
    thread = proposed(session, INPUT)
    state, first, _ = join_value(session, thread)
    state = act(session, "side", text="Why did that change?", thread=thread)
    assert thread_of(session, thread)["outcome"] == "joined" and thread_of(session, thread)["node"] == first["id"]
    state = act(session, "side", text="Actually A will be at most 60.", thread=thread)
    assert proposal_of(session, thread)["id"] == "p2" and proposal_of(session, thread)["change"]["from"] == "50"
    state, second, new = join_value(session, thread, "p2")
    assert second["id"] != first["id"] and second["branch"] == thread
    assert [(node["kind"], node["branch"]) for node in trunk(state)] == [
        ("plan_accepted", None), ("value", thread), ("value", thread)]
    found = thread_of(session, thread)
    assert (found["outcome"], found["node"]) == ("joined", second["id"])
    assert [(each["module"], each["inputs"]) for each in new] == [("total", {"a": "60", "b": "20"}),
                                                                  ("double", {"total": "80"})]
    assert state["inputs"]["in:a"]["value"] == "60" and step_of(state, "c1")["changed_by"] == second["id"]


# --- No, close, and the death rule (12.5) ---

def test_no_declines_the_proposal_and_the_branch_is_dead_with_nothing_changed(routed):
    from harness.answers import agent

    session = routed(side=[propose(), reply(ACK)])
    thread = proposed(session)
    state = act(session, "decline_proposal", proposal="p1")
    found = thread_of(session, thread)
    assert found["proposal"]["status"] == "declined" and found["proposal"]["node"] is None
    assert (found["outcome"], found["node"]) == ("dead", None)
    assert len(trunk(state)) == 1 and state["history"]["latest"] == "n1"
    assert runs_count(session) == 2 and agent.saved_inputs(session.conn) == {}
    assert [each["reason"] for each in events(session, "you.branch_dead")] == ["declined"]
    assert events(session, "you.proposal_declined")[0]["proposal"] == "p1"
    assert refused(session, "decline_proposal", proposal="p1") and refused(session, "accept_proposal", proposal="p1")
    assert refused(session, "accept_proposal", proposal="p99")
    with pytest.raises(BadAction):
        session.act("decline_proposal", {"proposal": "nonsense"})
    assert problems(state, strict=True) == []


def test_closing_a_branch_makes_it_dead_and_declines_a_pending_proposal_in_it(routed):
    session = routed(side=[reply("A short answer."), propose(), reply(ACK)])
    plain, _ = branch(session, "What does cash flow forecast mean here?", {"kind": "step", "step": "c3"})
    state = act(session, "close_branch", thread=plain["id"])
    assert thread_of(session, plain["id"])["outcome"] == "dead" and len(trunk(state)) == 1
    assert refused(session, "close_branch", thread=plain["id"])         # only a branch that is open
    pending = proposed(session)
    act(session, "close_branch", thread=pending)
    assert thread_of(session, pending)["outcome"] == "dead" and proposal_of(session, pending)["status"] == "declined"
    assert [each["reason"] for each in events(session, "you.branch_dead")] == ["closed", "closed"]
    assert refused(session, "close_branch", thread="t99")
    with pytest.raises(BadAction):
        session.act("close_branch", {"thread": "nonsense"})
    review = add_thread(session.conn, session.conversation, kind="review", title="A challenge", step="c1",
                        origin="reviewer", subject={"kind": "step", "step": "c1"})
    assert refused(session, "close_branch", thread=review)               # a review branch dies only by dismiss


def test_a_joined_branch_cannot_be_closed(routed):
    session = routed(side=[propose(), reply(ACK)])
    thread = proposed(session)
    join_value(session, thread)
    assert refused(session, "close_branch", thread=thread)
    assert thread_of(session, thread)["outcome"] == "joined"


def test_opening_another_branch_ends_an_answered_one_without_a_pending_proposal(routed):
    session = routed(side=[reply("First answer."), propose(), reply(ACK), reply("Third answer.")])
    first, _ = branch(session, "What is this?", {"kind": "step", "step": "c1"})
    second = proposed(session)
    assert thread_of(session, first["id"])["outcome"] == "dead"
    third, state = branch(session, "And this?", {"kind": "step", "step": "c2"})
    assert thread_of(session, second)["outcome"] == "open"               # it has a pending proposal
    assert thread_of(session, third["id"])["outcome"] == "open"
    assert [(each["thread"], each["reason"]) for each in events(session, "you.branch_dead")] == [
        (first["id"], "new_branch")]
    assert len(trunk(state)) == 1


def test_going_on_in_the_main_chat_ends_an_answered_branch_but_not_one_with_a_pending_proposal(routed):
    session = routed(side=[propose(), reply(ACK), reply("An answer.")], main=MAIN + [reply("Fine.")])
    pending = proposed(session)
    answered, _ = branch(session, "What does this step do?", {"kind": "step", "step": "c2"})
    assert thread_of(session, pending)["outcome"] == "open" and answered["outcome"] == "open"
    state = say(session, "And what about the rest?")
    assert thread_of(session, answered["id"])["outcome"] == "dead"
    assert thread_of(session, pending)["outcome"] == "open"
    assert [(each["thread"], each["reason"]) for each in events(session, "you.branch_dead")] == [
        (answered["id"], "moved_on")]
    assert len(trunk(state)) == 1


def test_a_message_in_a_dead_branch_opens_it_again(routed):
    session = routed(side=[reply("First."), reply("Second.")])
    found, _ = branch(session, "What is this?", {"kind": "step", "step": "c1"})
    act(session, "close_branch", thread=found["id"])
    assert thread_of(session, found["id"])["outcome"] == "dead"
    state = act(session, "side", text="One more thing.", thread=found["id"])
    assert thread_of(session, found["id"])["outcome"] == "open"
    assert [each["thread"] for each in events(session, "you.branch_reopened")] == [found["id"]]
    assert [m["who"] for m in state["threads"][0]["messages"]] == ["you", "assistant", "you", "assistant"]


def test_a_branch_with_no_consequence_never_makes_a_trunk_node_and_the_plan_stays(routed):
    session = routed(side=[reply("It is a forecast of money in and out."), reply("Another answer."),
                           reply("A third answer.")])
    before = session.state()
    first, _ = branch(session, "What does cash flow forecast mean here?", {"kind": "step", "step": "c3"})
    act(session, "close_branch", thread=first["id"])
    second, _ = branch(session, "What does this value mean?", VALUE)
    third, _ = branch(session, "And this one?", {"kind": "plan"})          # the second dies: another branch
    state = session.state()
    assert [thread_of(session, each)["outcome"] for each in (first["id"], second["id"], third["id"])] == [
        "dead", "dead", "open"]
    assert state["history"] == before["history"] and trunk(state) == trunk(before)
    assert state["steps"] == before["steps"] and state["inputs"] == before["inputs"]
    assert runs_count(session) == 2 and session.conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 0
    assert all(each["node"] is None for each in state["threads"])


# --- Chips (12.7) ---

def test_an_assumption_chip_carries_its_status_and_id_from_the_assumptions_table(routed):
    sentence = "B stays at 20."
    session = routed(main=[run("total", {"a": 10, "b": 20}, [sentence]), reply("The total is 30.")], side=[],
                     ask_first=False)
    state = say(session, "A is 10 and B is 20, what is the total?")
    (chip,) = [chip for chip in state["chat"][-1]["chips"] if chip["kind"] == "assumption"]
    assumption = step_of(state, "c1")["unconfirmed"][0]["id"]
    assert (chip["text"], chip["status"], chip["subject"]["assumption"]) == (sentence, "unconfirmed", assumption)
    state = act(session, "confirm_assumptions", message=notices(state)[0]["id"])
    (chip,) = [chip for chip in state["chat"][-1]["chips"] if chip["kind"] == "assumption"]
    assert (chip["status"], chip["subject"]["assumption"]) == ("confirmed", assumption)
    assert problems(state, strict=True) == []


# --- The layer pin and the expectation (6.5, 6.6) ---

def test_these_tests_run_the_harness_up_to_layer_4(routed):
    session = routed(side=[])
    assert session.state()["layers"] == [0, 1, 2, 3, 4]


def test_the_branches_expectation_counts_side_branches_by_outcome_and_the_kinds_of_their_nodes(routed):
    from harness.needs_you.layer import LAYER

    expect = LAYER.expects["branches"]
    assert expect.validate({"joined": 1, "dead": 0, "nodes": ["value"]}) is None
    session = routed(side=[propose(), reply(ACK), reply("Fine.")])
    thread = proposed(session)
    assert not expect.check({"joined": 1}, session)["passed"]
    join_value(session, thread)
    assert expect.check({"joined": 1, "dead": 0, "nodes": ["value"]}, session)["passed"]
    assert not expect.check({"joined": 0}, session)["passed"]
    assert not expect.check({"nodes": ["plan_revised"]}, session)["passed"]
    other, _ = branch(session, "What is this?", {"kind": "step", "step": "c1"})
    act(session, "close_branch", thread=other["id"])
    assert expect.check({"joined": 1, "dead": 1, "nodes": ["value"]}, session)["passed"]
    assert not expect.check({"dead": 0}, session)["passed"]
