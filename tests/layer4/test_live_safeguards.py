"""SPEC 6.1 "Unlisted assumptions" and 6.2 "A call left in prose": the two checks layer 4 makes inside an analyst
turn, so that a run on a value the person did not give always carries a mark, and a call that is the person's
does not end the turn as a question in plain text."""
import json

from harness.needs_you import marks
from layer4_helpers import (ask, assistant, events, notices, problems, reply, run, say, step_of, until)

QUESTION = "Which do you want to change first: amount A, amount B or neither?"
OPTIONS = ["Amount A", "Amount B", "Neither"]


def change_plan(world_dir, change):
    """Rewrite the small plan before the session opens."""
    path = world_dir / "brief" / "domain_brief.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    change(plan)
    path.write_text(json.dumps(plan), encoding="utf-8")


def plan_proposes_b(plan):
    plan["particulars"].append({"what": "Amount B is usually 20, and the share kept is 0.5",
                                "handling": "Use it", "step": None, "origin": {"kind": "proposed"}})


def judgment_needs_c2(plan):
    next(step for step in plan["process"] if step["id"] == "j1")["needs"] = ["c2"]


def sent_back(session):
    """The user messages the harness sent to the model inside a turn (corrections and send-backs)."""
    found = []
    for each in session.script.calls:
        last = each["messages"][-1]
        if last["role"] == "user" and str(last["content"]).startswith("[harness]"):
            found.append(last["content"])
    return found


def tool_errors(session):
    """The refused tool calls of the model's conversation so far."""
    last = session.script.calls[-1]["messages"] if session.script.calls else []
    return [message for message in last if message.get("role") == "tool" and message.get("is_error")]


# --- A call left in prose ---

def test_a_choice_asked_in_prose_after_a_run_is_sent_back_and_the_decision_then_waits(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}), reply(f"The total is 30. {QUESTION}"),
                            ask("j1", QUESTION, OPTIONS, runs=[1]), reply("Noted.")])
    state = say(session, "A is 10 and B is 20. What is the total? Then help me decide what to change.")
    assert state["waiting"] is not None and state["waiting"]["kind"] == "decision"
    assert step_of(state, "j1")["needs_you"]
    assert all(QUESTION not in message["text"] or message["kind"] == "decision" for message in assistant(state))
    (prompted,) = events(session, "you.decision_prompted")
    assert prompted["reason"] == "alternatives"
    kinds = [(message["kind"], message["text"]) for message in assistant(state)]
    assert kinds[-2:] == [("text", "The total is 30."), ("decision", QUESTION)]   # the results are kept, first
    assert problems(state, strict=True) == []


def test_the_second_prose_reply_is_shown_and_nothing_waits(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}), reply(f"The total is 30. {QUESTION}"),
                            reply(f"The total is 30. {QUESTION}")])
    state = say(session, "A is 10 and B is 20. What is the total? Help me choose what to change.")
    assert state["waiting"] is None and state["lanes"]["main"] == "idle"
    assert assistant(state)[-1]["text"] == f"The total is 30. {QUESTION}"
    assert len(session.script.calls) == 3 and len(events(session, "you.decision_prompted")) == 1


def test_a_question_listing_options_is_sent_back(open_session):
    text = "The total is 30. What would you like to change first?\n\n- Amount A\n- Amount B"
    session = open_session([run("total", {"a": 10, "b": 20}), reply(text), reply(text)])
    say(session, "A is 10 and B is 20. What is the total? Help me decide what to change.")
    assert len(events(session, "you.decision_prompted")) == 1


def test_a_question_for_a_missing_figure_before_any_run_is_shown_as_it_is(open_session):
    session = open_session([reply("What is amount B, or do you not know it yet?")])
    state = say(session, "A is 10. What is the total? Then help me decide what to change.")
    assert assistant(state)[-1]["text"] == "What is amount B, or do you not know it yet?"
    assert len(session.script.calls) == 1 and events(session, "you.decision_prompted") == []


def test_a_question_with_alternatives_is_shown_when_the_person_did_not_ask_to_decide(open_session, tmp_path):
    change_plan(tmp_path, judgment_needs_c2)                  # even after a run that the call rests on
    text = "Twice the total is 60. Do you want to see it with B at 30, or keep it as it is?"
    session = open_session([run("double", {"total": 30}), reply(text)])
    state = say(session, "The total is 30. What is twice that?")
    assert assistant(state)[-1]["text"] == text and events(session, "you.decision_prompted") == []
    assert state["waiting"] is None


def test_a_question_after_a_run_that_feeds_an_undecided_call_names_the_call(open_session, tmp_path):
    change_plan(tmp_path, judgment_needs_c2)
    text = "Twice the total is 60. What would you like to change first?"
    session = open_session([run("double", {"total": 30}), reply(text), reply(text)])
    say(session, "The total is 30. What is twice that? Help me decide what to change.")
    (prompted,) = events(session, "you.decision_prompted")
    assert (prompted["reason"], prompted["steps"]) == ("your call", ["j1"])
    assert "j1" in sent_back(session)[-1]


def test_a_message_attached_to_the_call_counts_as_asking_to_decide(open_session, tmp_path):
    change_plan(tmp_path, judgment_needs_c2)
    text = "Twice the total is 60."
    session = open_session([run("double", {"total": 30}), reply(text), reply(text)])
    state = say(session, "The total is 30. Where does that leave me?", step="j1")
    assert len(events(session, "you.decision_prompted")) == 1
    assert assistant(state)[-1]["text"] == text and state["waiting"] is None      # declined twice: shown


def test_an_answer_that_leaves_the_call_for_later_is_sent_back_when_the_person_asked_to_decide(open_session,
                                                                                                tmp_path):
    change_plan(tmp_path, judgment_needs_c2)
    text = "Twice the total is 60. Next I will ask you what to change."
    session = open_session([run("double", {"total": 30}), reply(text), ask("j1", QUESTION, OPTIONS, runs=[1])])
    state = say(session, "The total is 30. What is twice that? Then help me decide what to change.")
    assert events(session, "you.decision_prompted")[0]["reason"] == "your call"
    assert [message["kind"] for message in assistant(state)][-2:] == ["text", "decision"]
    assert assistant(state)[-2]["text"] == text and state["waiting"]["kind"] == "decision"


def test_an_answer_with_no_question_is_shown_when_the_person_did_not_ask_to_decide(open_session, tmp_path):
    change_plan(tmp_path, judgment_needs_c2)
    session = open_session([run("double", {"total": 30}), reply("Twice the total is 60.")])
    state = say(session, "The total is 30. What is twice that?")
    assert assistant(state)[-1]["text"] == "Twice the total is 60."
    assert events(session, "you.decision_prompted") == []


def test_no_send_back_once_the_turn_asked_a_decision(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}), ask("j1", QUESTION, OPTIONS, runs=[1]),
                            reply("Then A. Do you want to look at B now, or later?")])
    state = say(session, "A is 10 and B is 20. Help me decide what to change.")
    decision = next(each for each in state["chat"] if each["kind"] == "decision")["decision"]["id"]
    applied, why = session.act("choose", {"decision": decision, "option": 1})
    assert applied, why
    state = until(session, lambda state: state["lanes"]["main"] == "idle" and state["waiting"] is None)
    assert assistant(state)[-1]["text"] == "Then A. Do you want to look at B now, or later?"
    assert events(session, "you.decision_prompted") == []


# --- Unlisted assumptions ---

def test_a_run_on_a_value_only_the_plan_proposes_is_refused_until_it_is_listed(open_session, tmp_path):
    change_plan(tmp_path, plan_proposes_b)
    listed = "Amount B is 20, as the plan says."
    session = open_session([run("total", {"a": 10, "b": 20}), run("total", {"a": 10, "b": 20}, [listed]),
                            reply("The total is 30, if B is 20.")])
    state = say(session, "A is 10. What is the total?")
    assert len(tool_errors(session)) == 1
    assert session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0] == 1
    (message,) = notices(state)
    assert [each["text"] for each in message["notice"]["assumptions"]] == [listed]
    assert [each["outcome"] for each in events(session, "you.assumption_unlisted")] == ["refused"]
    assert step_of(state, "c1")["unconfirmed"]
    assert problems(state, strict=True) == []


def test_a_later_run_in_the_turn_goes_ahead_with_a_mark_the_harness_writes(open_session, tmp_path):
    change_plan(tmp_path, plan_proposes_b)
    session = open_session([run("total", {"a": 10, "b": 20}), run("total", {"a": 10, "b": 20}),
                            reply("The total is 30.")])
    state = say(session, "A is 10. What is the total?")
    assert len(tool_errors(session)) == 1                              # refused once, then let through
    (message,) = notices(state)
    (assumption,) = message["notice"]["assumptions"]
    assert "20" in assumption["text"]
    assert [each["outcome"] for each in events(session, "you.assumption_unlisted")] == ["refused", "marked"]


def test_values_the_person_gave_are_not_assumptions(open_session):
    session = open_session([run("total", {"a": 10, "b": 20}), run("double", {"total": 30}),
                            reply("The total is 30 and twice that is 60.")])
    state = say(session, "A is 10 and B is 20. What is twice the total?")
    assert tool_errors(session) == [] and notices(state) == []
    assert events(session, "you.assumption_unlisted") == []


def test_a_share_the_person_said_in_words_is_theirs(open_session, tmp_path):
    change_plan(tmp_path, plan_proposes_b)
    session = open_session([run("total", {"a": 0.5, "b": 30}), reply("The total is 30.5.")])
    state = say(session, "A is half and B is 30. What is the total?")
    assert tool_errors(session) == [] and notices(state) == []


def test_a_confirmed_assumption_is_the_persons_from_then_on(open_session, tmp_path):
    change_plan(tmp_path, plan_proposes_b)
    listed = "Amount B is 20, as the plan says."
    session = open_session([run("total", {"a": 10, "b": 20}, [listed]), reply("The total is 30, if B is 20."),
                            run("total", {"a": 10, "b": 20}), reply("Still 30.")])
    state = say(session, "A is 10. What is the total?")
    applied, why = session.act("confirm_assumptions", {"message": notices(state)[0]["id"]})
    assert applied, why
    say(session, "And again?")
    assert tool_errors(session) == [] and events(session, "you.assumption_unlisted") == []


def test_which_values_are_unlisted():
    sources = marks.given_texts(["The wedding is on 12 June 2027, the second payment is half of what is left."])
    found = marks.unlisted({"wedding_date": "2027-06-12", "share": "0.5", "due": "2027-05-29", "days": "7",
                            "name": "payment 1", "counts": True, "rows": [{"amount": "430"}]}, [], sources)
    assert [name for name, _ in found] == ["due", "amount"]
    assert marks.unlisted({"due": "2027-05-29", "amount": "430"},
                          ["The contribution comes on 2027-05-29.", "The amount is 430."], sources) == []
    assert marks.unlisted({"second_payment_share": "0.4"}, ["The second payment share is a guess."], sources) == []
