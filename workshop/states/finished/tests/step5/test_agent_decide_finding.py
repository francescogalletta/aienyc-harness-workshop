"""SPEC 9.7: `ask_decision` with `finding`: the checks, what is shown, how the answer is read, what is recorded and what
the agent gets."""
import json

import pytest

import step5_helpers as s5
from step5_helpers import (BRIEF_BLOCK, DATA_BLOCK, FINDING_NOT_OPEN, OPTIONS_BRIEF, OPTIONS_DATA, RENT_MESSAGE, WIDE_BRIEF,
                           WIDE_MESSAGE, ask_finding, brief_entry, entry, h, report, s4, summary_call, wide_block,
                           wide_entry)

OK = "Noted."
OPEN = [summary_call(), report(entry())]
RESULT_KEYS = ["outcome", "decision", "finding", "choice", "option", "use", "said", "saved"]


def decide(talk, answer, *, extra=("/quit",), reply=OK):
    """One data finding answered with `answer`. Returns (result dict, model, person)."""
    model, person = talk([*OPEN, ask_finding(1), h.say_text(reply)], [answer, *extra])
    return json.loads(h.tool_message(model, 3)["content"]), model, person


def asked(person):
    return [text for kind, text in person.log if kind == "ask"]


# ---- what is shown ------------------------------------------------------------------------------------------------------

def test_the_block_is_said_and_then_the_plain_question_is_asked(talk, example_loaded):
    _, _, person = decide(talk, "1")
    k = person.log.index(("say", DATA_BLOCK))
    assert person.log[k + 1] == ("ask", s4.DECISION_QUESTION)


def test_ask_decision_asked_holds_the_arguments_and_the_block(talk, conn, example_loaded):
    decide(talk, "1")
    [(kind, actor, payload)] = h.events(conn, "ask.decision_asked")
    assert actor == "agent" and list(payload) == ["arguments", "block"]
    assert payload == {"arguments": {"finding": 1, "runs": []}, "block": DATA_BLOCK}


def test_the_events_of_a_finding_decided(talk, conn, example_loaded):
    decide(talk, "2")
    kinds = s5.kinds_after_start(conn)
    start = kinds.index("ask.decision_asked")
    assert kinds[start:start + 3] == ["ask.decision_asked", "ask.decision", "finding.closed"]
    assert s5.actors(conn, "ask.decision") == ["person"] and s5.actors(conn, "finding.closed") == ["harness"]


def test_an_empty_answer_asks_again_and_records_nothing(talk, conn, example_loaded):
    result, _, person = decide(talk, "", extra=("   ", "2", "/quit"))
    assert asked(person).count(s4.DECISION_QUESTION) == 3 and result["choice"] == "2"
    assert len(h.rows(conn, "decisions")) == 1 and len(s5.events(conn, "ask.decision_asked")) == 1


def test_a_recommendation_in_the_call_is_ignored(talk, example_loaded):
    model, person = talk([*OPEN, ask_finding(1, recommendation=2, why="It is safer."), h.say_text(OK)], ["yes", "/quit"])
    assert asked(person).count(s4.DECISION_QUESTION) == 1 and s4.DECISION_QUESTION_SUGGESTED not in asked(person)
    assert ("say", DATA_BLOCK) in person.log
    assert json.loads(h.tool_message(model, 3)["content"])["choice"] == "something else"


# ---- reading the answer ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("answer, choice, option, use", [
    ("1", "1", OPTIONS_DATA[0], "5000"), ("2", "2", OPTIONS_DATA[1], "4132.31"),
    ("Option 2", "2", OPTIONS_DATA[1], "4132.31"), ("option 1.", "1", OPTIONS_DATA[0], "5000"),
    ("2)", "2", OPTIONS_DATA[1], "4132.31"),
    ("use the figure  from my files: 4132.31", "2", OPTIONS_DATA[1], "4132.31"),
    ("KEEP WHAT I SAID: 5K", "1", OPTIONS_DATA[0], "5000"),
    ("yes", "something else", None, None), ("3", "something else", None, None), ("0", "something else", None, None),
    ("use the files", "something else", None, None), ("/quit", "something else", None, None),
    ("make it 4,500 then", "something else", None, None),
])
def test_the_answer_is_read_as_at_a_judgment(talk, example_loaded, answer, choice, option, use):
    result, _, _ = decide(talk, answer)
    assert list(result) == RESULT_KEYS
    assert result == {"outcome": "decided", "decision": 1, "finding": 1, "choice": choice, "option": option, "use": use,
                      "said": answer, "saved": False}


def test_the_answer_is_stripped(talk, example_loaded):
    result, _, _ = decide(talk, "  2  ")
    assert result["said"] == "2" and result["choice"] == "2"


@pytest.mark.parametrize("answer, choice, option, use", [("1", "1", OPTIONS_BRIEF[0], "1400"),
                                                         ("2", "2", OPTIONS_BRIEF[1], "1150")])
def test_a_brief_finding_uses_the_figures_of_the_brief(talk, conn, answer, choice, option, use):
    model, _ = talk([report(brief_entry()), ask_finding(1), h.say_text(OK)], [answer, "/quit"], question=RENT_MESSAGE)
    result = json.loads(h.tool_message(model, 2)["content"])
    assert (result["choice"], result["option"], result["use"]) == (choice, option, use)
    assert h.rows(conn, "decisions")[0]["question"] == BRIEF_BLOCK


# ---- what is recorded --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("answer, choice, chosen", [("1", "1", "5000"), ("2", "2", "4132.31"),
                                                    ("something odd", "something else", None)])
def test_the_decision_is_a_record_of_kind_finding(talk, conn, example_loaded, answer, choice, chosen):
    decide(talk, answer)
    [decision] = h.rows(conn, "decisions")
    assert decision["kind"] == "finding" and decision["step_id"] is None and decision["question"] == DATA_BLOCK
    assert json.loads(decision["options"]) == OPTIONS_DATA and decision["choice"] == choice
    assert decision["words"] == answer and json.loads(decision["runs"]) == [] and decision["session_id"] == s5.SESSION
    [payload] = s5.payloads(conn, "ask.decision")
    assert payload == {"id": 1, "kind": "finding", "step": None, "question": DATA_BLOCK, "options": OPTIONS_DATA,
                       "choice": choice, "words": answer, "runs": []}


@pytest.mark.parametrize("answer, choice, chosen", [("1", "1", "5000"), ("2", "2", "4132.31"),
                                                    ("something odd", "something else", None)])
def test_the_finding_is_closed(talk, conn, example_loaded, findings, answer, choice, chosen):
    decide(talk, answer)
    [row] = findings.list_findings(conn, session_id=s5.SESSION)
    assert (row["status"], row["decision"], row["choice"], row["chosen"]) == ("decided", 1, choice, chosen)
    assert s5.payloads(conn, "finding.closed") == [{"finding": 1, "decision": 1, "choice": choice, "chosen": chosen,
                                                    "saved": False}]
    assert findings.open_findings(conn, session_id=s5.SESSION) == []


def test_nothing_is_saved_for_a_data_finding(talk, conn, example_loaded):
    decide(talk, "2")
    assert h.rows(conn, "inputs") == [] and s5.events(conn, "ask.input_saved") == []


def test_a_finding_does_not_make_a_judgment_step_decided(talk, conn, example_loaded):
    model, _ = talk([*OPEN, ask_finding(1), s4.ask_decision(), h.say_text(OK)], ["1", "1", "/quit"])
    result = json.loads(h.tool_message(model, 4)["content"])
    assert result["judgment_steps"] == [{"id": "s2", "name": "Decide how much to set aside", "decided": False}]


# ---- the checks -------------------------------------------------------------------------------------------------------------------

def test_the_second_ask_decision_of_a_reply_is_refused(talk, conn, example_loaded):
    both = h.tools(("ask_decision", {"finding": 1, "runs": []}), ("ask_decision", {"finding": 1, "runs": []}))
    model, person = talk([*OPEN, both, h.say_text(OK)], ["1", "/quit"])
    contents = [m["content"] for m in model.calls[3]["messages"] if m["role"] == "tool"]
    assert json.loads(contents[0])["outcome"] == "decided" and contents[1] == s4.ONE_DECISION
    assert s5.payloads(conn, "ask.decision_refused") == [{"error": s4.ONE_DECISION, "arguments": {"finding": 1, "runs": []}}]
    assert asked(person).count(s4.DECISION_QUESTION) == 1


def test_a_finding_after_a_judgment_in_one_reply_is_refused(talk, conn, example_loaded):
    both = h.tools(("ask_decision", s4.ask_decision_arguments()), ("ask_decision", {"finding": 1, "runs": []}))
    model, person = talk([*OPEN, both, ask_finding(1), h.say_text(OK)], ["1", "2", "/quit"])
    contents = [m["content"] for m in model.calls[3]["messages"] if m["role"] == "tool"]
    assert contents[1] == s4.ONE_DECISION
    assert [d["kind"] for d in h.rows(conn, "decisions")] == ["judgment", "finding"]


def test_a_finding_after_a_refused_judgment_in_one_reply_is_also_refused(talk, conn, example_loaded):
    both = h.tools(("ask_decision", {"runs": []}), ("ask_decision", {"finding": 1, "runs": []}))
    model, _ = talk([*OPEN, both, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    contents = [m["content"] for m in model.calls[3]["messages"] if m["role"] == "tool"]
    assert contents == [s4.DECISION_NO_QUESTION, s4.ONE_DECISION]


@pytest.mark.parametrize("value", [99, 0, -1, 2, True, False, "1", 1.5, [1], {"id": 1}])
def test_a_finding_that_is_not_an_open_one_is_refused(talk, conn, example_loaded, value):
    arguments = {"finding": value, "runs": []}
    model, person = talk([*OPEN, h.tool("ask_decision", arguments), ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert h.tool_message(model, 3)["content"] == FINDING_NOT_OPEN.format(finding=json.dumps(value))
    assert s5.payloads(conn, "ask.decision_refused") == [{"error": FINDING_NOT_OPEN.format(finding=json.dumps(value)),
                                                          "arguments": arguments}]
    assert asked(person).count(s4.DECISION_QUESTION) == 1 and person.told.count(DATA_BLOCK) == 1


def test_a_finding_already_decided_is_not_open(talk, conn, example_loaded):
    model, _ = talk([*OPEN, ask_finding(1), ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert h.tool_message(model, 4)["content"] == FINDING_NOT_OPEN.format(finding="1")


def test_a_finding_of_another_conversation_is_not_open(talk, conn, findings, example_loaded):
    findings.open_finding(conn, session_id="another", kind="brief", claim="x 1,400", claim_figure="1,400",
                          reference="y 1,150", reference_figure="1,150", difference="d")
    model, _ = talk([report(), ask_finding(1), h.say_text(OK)], ["/quit"])
    assert h.tool_message(model, 2)["content"] == FINDING_NOT_OPEN.format(finding="1")
    assert [f["status"] for f in findings.list_findings(conn)] == ["open"]


def test_every_other_argument_is_ignored(talk, conn, example_loaded):
    arguments = {"finding": 1, "runs": [7, "x"], "question": "", "options": [], "step": "s9", "recommendation": 9,
                 "why": ""}
    model, person = talk([*OPEN, h.tool("ask_decision", arguments), h.say_text(OK)], ["2", "/quit"])
    assert json.loads(h.tool_message(model, 3)["content"])["choice"] == "2"
    assert ("say", DATA_BLOCK) in person.log and s5.events(conn, "ask.decision_refused") == []
    [decision] = h.rows(conn, "decisions")
    assert decision["step_id"] is None and json.loads(decision["runs"]) == []
    assert s5.payloads(conn, "ask.decision_asked")[0]["arguments"] == arguments


def test_a_call_with_only_the_finding_is_enough(talk, example_loaded):
    model, _ = talk([*OPEN, h.tool("ask_decision", {"finding": 1}), h.say_text(OK)], ["1", "/quit"])
    assert json.loads(h.tool_message(model, 3)["content"])["outcome"] == "decided"


@pytest.mark.parametrize("arguments", [{"finding": None, "runs": []}, {"runs": []}])
def test_without_a_finding_the_call_is_a_judgment_as_before(talk, conn, example_loaded, arguments):
    model, _ = talk([*OPEN, h.tool("ask_decision", arguments), ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert h.tool_message(model, 3)["content"] == s4.DECISION_NO_QUESTION


def test_a_null_finding_with_a_question_is_a_judgment(talk, conn, example_loaded):
    arguments = s4.ask_decision_arguments(finding=None)
    model, person = talk([*OPEN, h.tool("ask_decision", arguments), ask_finding(1), h.say_text(OK)], ["1", "1", "/quit"])
    assert [d["kind"] for d in h.rows(conn, "decisions")] == ["judgment", "finding"]
    assert s4.decision_block("Should the date stay or move?", ["Keep the date", "Move the date"]) in person.told


# ---- the limit of decisions ----------------------------------------------------------------------------------------------------------

def test_a_finding_does_not_use_up_the_judgments_of_a_message(talk, conn, example_loaded):
    script = [*OPEN, ask_finding(1), s4.ask_decision(), s4.ask_decision(), s4.ask_decision(), h.say_text(OK)]
    model, _ = talk(script, ["1", "1", "1", "/quit"])
    assert [d["kind"] for d in h.rows(conn, "decisions")] == ["finding", "judgment", "judgment"]
    assert h.tool_message(model, 6)["content"] == s4.TOO_MANY_DECISIONS


def test_a_finding_is_allowed_after_two_judgments(talk, conn, example_loaded):
    script = [*OPEN, s4.ask_decision(), s4.ask_decision(), ask_finding(1), h.say_text(OK)]
    model, _ = talk(script, ["1", "1", "2", "/quit"])
    assert [d["kind"] for d in h.rows(conn, "decisions")] == ["judgment", "judgment", "finding"]
    assert json.loads(h.tool_message(model, 5)["content"])["outcome"] == "decided"


def test_two_findings_and_two_judgments_in_one_message(talk, conn):
    script = [report(wide_entry("rent"), wide_entry("gym")), ask_finding(1), ask_finding(2), s4.ask_decision(),
              s4.ask_decision(), h.say_text(OK)]
    talk(script, ["1", "2", "1", "1", "/quit"], question=WIDE_MESSAGE, brief=WIDE_BRIEF)
    assert [d["kind"] for d in h.rows(conn, "decisions")] == ["finding", "finding", "judgment", "judgment"]


def test_the_second_finding_is_put_after_the_first_is_decided(talk, conn):
    script = [report(wide_entry("rent"), wide_entry("gym")), ask_finding(2), ask_finding(1), h.say_text(OK)]
    _, person = talk(script, ["2", "1", "/quit"], question=WIDE_MESSAGE, brief=WIDE_BRIEF)
    assert person.told.index(wide_block("gym")) < person.told.index(wide_block("rent"))
    assert [(f["id"], f["choice"]) for f in s5.finding_rows(conn)] == [(1, "1"), (2, "2")]


# ---- a side conversation ---------------------------------------------------------------------------------------------------------------

def test_aside_works_at_a_finding(talk, conn, example_loaded):
    script = [*OPEN, ask_finding(1), s4.side("Averages are over full months."), h.say_text(OK)]
    model, person = talk(script, ["/aside what does that mean?", "/back", "no", "2", "/quit"])
    assert model.roles() == ["verifier", "verifier", "analyst", "aside", "analyst"]
    kinds = s5.kinds_after_start(conn)
    first, last = kinds.index("ask.decision_asked"), kinds.index("ask.decision")
    assert "aside.opened" in kinds[first:last] and kinds.index("finding.closed") == last + 1
    assert [d["choice"] for d in h.rows(conn, "decisions")] == ["2"]
    assert asked(person).count(s4.DECISION_QUESTION) == 2
