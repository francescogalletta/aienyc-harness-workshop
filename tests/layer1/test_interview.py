"""SPEC 3.2 and 3.5: the interview on the core, the plan as a state document, corrections, acceptance."""
import json
from pathlib import Path

import pytest
from layer1_helpers import PLAN, SETTLE, asks, item, looks_up, say, small_brief, write_brief

from harness import db
from harness.config import load_config
from harness.core import BadAction
from harness.grounding.interview import (LIMIT_REACHED, NOT_CONFIRMED, ONE_QUESTION, PLAN_ACCEPTED,
                                         PLAN_PROPOSED, WRAP_UP)
from harness.grounding.layer import run_ground

OPENING = "I want to save for a move next spring"


def events(session, kind) -> list[dict]:
    return [json.loads(row["payload"]) for row in db.list_events(session.conn, kind=kind)]


def kinds(session) -> set[str]:
    return {row["kind"] for row in db.list_events(session.conn)}


def texts(state):
    return [(message["who"], message["text"]) for message in state["chat"]]


def contents(session):
    """What the interviewer was sent in its latest call, as plain strings."""
    return [message["content"] for message in session.script.calls[-1]["messages"]]


def proposed_session(open_session, script=None):
    """A session whose interview has proposed the small brief and waits for acceptance."""
    session = open_session([PLAN, asks("What is the goal?"), *(script or [write_brief()])])
    say(session, OPENING)
    state = say(session, "Have enough saved for it")
    assert state["waiting"] == {"kind": "plan"}
    return session


def test_an_empty_state_has_no_plan(open_session):
    state = open_session().state()
    assert state["layers"] == [0, 1] and state["phase"] == "empty"
    assert (state["goal"], state["context"], state["inputs"], state["steps"], state["edges"]) == (
        None, None, {}, [], [])


def test_a_first_message_starts_the_interview_which_asks_one_question_and_waits(open_session, researcher):
    session = open_session([PLAN, asks("What is the goal?")])
    state = say(session, OPENING)
    assert state["phase"] == "interview" and state["waiting"] == {"kind": "message"}
    assert texts(state) == [("you", OPENING), ("assistant", "What is the goal?")]
    assert researcher.asked == ["sinking fund"]                      # the research plan, before the question
    assert {"plan.research_plan", "plan.question"} <= kinds(session)
    assert "Already read up on" in contents(session)[0]


def test_the_start_action_starts_it_too_and_only_once(open_session):
    session = open_session([PLAN, asks("What is the goal?")])
    assert session.act("start", {"text": OPENING}) == (True, "")
    state = session.settle(SETTLE)
    assert texts(state)[0] == ("you", OPENING) and state["waiting"] == {"kind": "message"}
    applied, reason = session.act("start", {"text": "again"})
    assert not applied and reason
    with pytest.raises(BadAction):
        session.act("start", {"text": " "})


def test_a_valid_brief_is_proposed_as_a_plan_the_page_can_draw(open_session):
    session = proposed_session(open_session)
    state = session.state()
    assert state["phase"] == "proposed" and state["waiting"] == {"kind": "plan"}
    assert state["chat"][-1]["kind"] == "plan" and state["chat"][-1]["text"] == PLAN_PROPOSED
    assert state["goal"] == {"text": "Have enough saved for the move", "mode": "one_off",
                             "origin": {"kind": "person", "quote": "save for a move"}}
    assert [step["id"] for step in state["steps"]] == ["a1", "a2"]
    assert state["steps"][0]["kind"] == "calculation" and state["steps"][1]["kind"] == "your_call"
    assert state["edges"] == [{"from": "a1", "to": "a2"}]
    assert state["inputs"]["in:van_hire"]["steps"] == ["a1"]
    assert state["steps"][1]["open_questions"][0]["text"] == "Is the date fixed?"
    assert state["steps"][1]["marks"][0]["symbol"] == "●"           # the core's mark for an open question
    assert state["steps"][0]["origin"]["source"]["title"] == "Sinking fund (Example)"
    assert "plan.proposed" in kinds(session)
    assert not (Path(load_config().brief_dir) / "domain_brief.json").exists()     # nothing saved yet
    json.dumps(state)


def test_accepting_saves_the_brief_as_confirmed_and_calls_the_hook(open_session):
    session = proposed_session(open_session)
    seen = []
    layer = session.layers[1]
    session.layers[1] = type(layer)(**{**layer.__dict__, "hooks": {**layer.hooks, "plan_accepted": seen.append}})
    assert session.act("accept_plan", {}) == (True, "")
    state = session.settle(SETTLE)
    assert state["phase"] == "accepted" and state["waiting"] is None
    assert state["chat"][-1]["text"] == PLAN_ACCEPTED and len(seen) == 1
    saved = json.loads((Path(load_config().brief_dir) / "domain_brief.json").read_text(encoding="utf-8"))
    assert saved["meta"]["status"] == "confirmed" and saved["meta"]["lookups"]
    assert [step["id"] for step in state["steps"]] == ["a1", "a2"]      # now drawn from the saved brief
    assert {"plan.accepted", "core.action"} <= kinds(session)
    assert not (Path(load_config().db_path).parent / "grounding_state.json").exists()
    assert session.act("accept_plan", {})[0] is False                   # nothing to accept now


def test_a_brief_with_open_questions_can_be_accepted(open_session):
    session = proposed_session(open_session)
    assert session.state()["steps"][1]["open_questions"]
    assert session.act("accept_plan", {})[0] is True


def test_a_correction_with_a_step_reaches_the_interviewer_and_the_plan_is_redrawn(open_session):
    changed = small_brief()
    changed["process"][0]["formula"] = "van hire + rent + deposit"
    session = proposed_session(open_session, [write_brief(), write_brief(changed)])
    before = session.state()["steps"][0]["formula"]
    state = say(session, "the formula should include the deposit", step="a1")
    sent = contents(session)[-1]
    assert sent.startswith(NOT_CONFIRMED) and "About step a1 (Move cost)" in sent
    assert "the formula should include the deposit" in sent
    assert state["phase"] == "proposed" and state["waiting"] == {"kind": "plan"}
    assert state["steps"][0]["formula"] == "van hire + rent + deposit" != before
    assert [message["kind"] for message in state["chat"]].count("plan") == 2
    assert state["chat"][-2]["step"] == "a1"                             # the chip stays on the person's message
    assert {"plan.changes"} <= kinds(session)


def test_the_plan_stays_drawn_while_a_correction_is_worked_on(open_session):
    session = proposed_session(open_session, [write_brief(), asks("Which deposit do you mean?")])
    state = say(session, "add the deposit", step="a1")
    assert state["phase"] == "proposed" and state["waiting"] == {"kind": "message"}
    assert [step["id"] for step in state["steps"]] == ["a1", "a2"]
    assert session.act("accept_plan", {})[0] is False                   # the interviewer asked something first


def test_a_brief_that_fails_its_checks_goes_back_to_the_interviewer_not_the_person(open_session):
    bad = small_brief(goal=item("A goal", {"kind": "person", "quote": "words I never wrote"}))
    session = open_session([PLAN, asks("What is the goal?"), write_brief(bad), write_brief()])
    say(session, OPENING)
    state = say(session, "Have enough saved for it")
    assert state["waiting"] == {"kind": "plan"} and state["phase"] == "proposed"
    assert events(session, "plan.brief_rejected")[0]["errors"]
    assert any(message.get("is_error") for message in session.script.calls[-1]["messages"])    # told to the model
    assert "words I never wrote" not in json.dumps(texts(state))


def test_three_rejections_save_a_draft_and_the_interviewer_asks_the_person(open_session):
    bad = small_brief(goal=item("A goal", {"kind": "person", "quote": "words I never wrote"}))
    session = open_session([PLAN, asks("What is the goal?"), write_brief(bad), write_brief(bad), write_brief(bad),
                            asks("Which of your words should I use?")])
    say(session, OPENING)
    state = say(session, "Have enough saved for it")
    draft = json.loads((Path(load_config().brief_dir) / "domain_brief.json").read_text(encoding="utf-8"))
    assert draft["meta"]["status"] == "draft"
    assert state["phase"] == "interview" and state["waiting"] == {"kind": "message"}
    assert state["chat"][-1]["text"] == "Which of your words should I use?"
    assert [event["draft"] for event in events(session, "plan.brief_rejected")] == [False, False, True]


def test_two_questions_in_one_reply_are_sent_back_and_the_person_sees_one(open_session):
    session = open_session([PLAN, asks("What is it? And when?"), asks("What is it?")])
    state = say(session, OPENING)
    assert [text for who, text in texts(state) if who == "assistant"] == ["What is it?"]
    assert contents(session)[-1] == ONE_QUESTION
    assert events(session, "plan.correction")


def test_wrap_asks_the_interviewer_to_propose_now_and_only_while_it_waits(open_session):
    session = open_session([PLAN, asks("What is the goal?"), write_brief()])
    assert session.act("wrap", {})[0] is False                           # no interview yet
    say(session, OPENING)
    assert session.act("wrap", {}) == (True, "")
    state = session.settle(SETTLE)
    assert contents(session)[-1] == WRAP_UP and state["waiting"] == {"kind": "plan"}
    assert session.act("wrap", {})[0] is False                           # a plan waits, not an answer


def test_the_question_limit_is_told_to_the_interviewer(open_session, monkeypatch):
    import harness.grounding.interview as interview
    original = interview.run_interview
    monkeypatch.setattr("harness.grounding.layer.run_interview",
                        lambda *a, **k: original(*a, **{**k, "max_questions": 1}))
    session = open_session([PLAN, asks("What is the goal?"), asks("Anything else?")])
    say(session, OPENING)
    say(session, "Have enough saved for it")
    assert LIMIT_REACHED in contents(session)[-1]


def test_look_ups_go_through_the_desk_once_per_term_and_their_sources_can_be_cited(open_session, researcher):
    session = open_session([{"tool_calls": [{"name": "plan_research", "arguments": {"terms": []}}]},
                            asks("What is the goal?"), looks_up("sinking fund", "Opening Balance"),
                            looks_up("sinking fund"), write_brief()])
    say(session, OPENING)
    state = say(session, "Have enough saved for it")
    assert researcher.asked == ["sinking fund", "Opening Balance"]       # the repeat was not asked again
    assert state["waiting"] == {"kind": "plan"}
    assert [event["query"] for event in events(session, "plan.lookup")] == ["sinking fund", "Opening Balance"]


def test_a_source_nothing_looked_up_is_not_accepted(open_session):
    session = open_session([{"tool_calls": [{"name": "plan_research", "arguments": {"terms": []}}]},
                            asks("What is the goal?"), write_brief(), asks("Which term?")])
    say(session, OPENING)
    state = say(session, "Have enough saved for it")
    assert state["phase"] == "interview" and events(session, "plan.brief_rejected")


def test_a_message_typed_while_the_model_works_is_kept_for_the_next_answer(open_session):
    session = open_session([PLAN, asks("What is the goal?"), asks("And the date?")])
    session.act("say", {"text": OPENING})
    session.act("say", {"text": "Have enough saved for it"})            # may arrive before the question does
    state = session.settle(SETTLE)
    assert [text for who, text in texts(state) if who == "assistant"] == ["What is the goal?", "And the date?"]
    assert not any(message["queued"] for message in state["chat"])


def test_a_failed_model_call_sets_the_error_and_the_next_message_picks_the_interview_up(open_session):
    session = open_session([PLAN, asks("What is the goal?")])           # then the script runs out
    say(session, OPENING)
    state = say(session, "Have enough saved for it")
    assert state["error"] and state["phase"] == "interview" and state["waiting"] is None
    session.script.script.append(asks("And the date?"))
    state = say(session, "By spring")
    assert state["error"] is None and state["chat"][-1]["text"] == "And the date?"
    assert "By spring" in contents(session)[-1] and "Have enough saved for it" in contents(session)[-1]


def test_an_unfinished_interview_is_resumed_by_a_new_session_from_its_state_file(open_session):
    first = open_session([PLAN, asks("What is the goal?")])
    say(first, OPENING)
    first.close()
    second = open_session([write_brief()])
    state = second.settle(SETTLE)
    assert state["phase"] == "interview" and state["waiting"] == {"kind": "message"}
    assert state["chat"][-1]["text"] == "What is the goal?"              # not asked again
    state = say(second, "Have enough saved for it")
    assert state["waiting"] == {"kind": "plan"}


def test_a_proposed_plan_survives_a_restart_and_can_still_be_accepted(open_session):
    first = proposed_session(open_session)
    first.close()
    second = open_session()
    state = second.settle(SETTLE)
    assert state["phase"] == "proposed" and state["waiting"] == {"kind": "plan"}
    assert [step["id"] for step in state["steps"]] == ["a1", "a2"]
    assert second.act("accept_plan", {})[0] is True
    assert second.settle(SETTLE)["phase"] == "accepted"


def test_an_example_brief_in_the_brief_folder_is_an_accepted_plan(open_session, moving_brief, monkeypatch, tmp_path):
    folder = tmp_path / "example"
    folder.mkdir()
    (folder / "domain_brief.json").write_text(json.dumps(moving_brief), encoding="utf-8")
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(folder))
    state = open_session().state()
    assert state["phase"] == "accepted" and [step["id"] for step in state["steps"]] == ["m1", "m2", "m3", "m4"]
    assert state["context"]["glossary"] and state["goal"]["mode"] == "ongoing"


def test_a_new_interview_after_an_older_conversation_starts_a_new_conversation(open_session):
    session = open_session([PLAN, asks("What is the goal?")])
    first = session.conversation
    session.post("a stray note", who="harness")
    state = say(session, OPENING)
    assert session.conversation != first
    assert texts(state)[0] == ("you", OPENING)


def test_ground_runs_the_interview_in_the_terminal_and_stops_when_the_plan_is_accepted(open_session):
    session = open_session([PLAN, asks("What is the goal?"), write_brief()])
    lines = iter([OPENING, "Have enough saved for it", "/accept"])
    out = []
    code = run_ground(session, read=lambda prompt: next(lines), write=out.append)
    assert code == 0 and session.state()["phase"] == "accepted"
    assert any("a1" in line and "Move cost" in line for line in out)    # the plan was printed to read


def test_ground_exits_1_when_input_ends_before_the_plan_is_accepted(open_session):
    session = open_session([PLAN, asks("What is the goal?")])
    lines = iter([OPENING])

    def read(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    assert run_ground(session, read=read, write=lambda text: None) == 1
