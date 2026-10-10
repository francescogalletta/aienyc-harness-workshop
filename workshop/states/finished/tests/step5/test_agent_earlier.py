"""SPEC 9.7: `save_input` over a different saved value: the four rules, the finding of kind `earlier`, and how it is decided."""
import json

import pytest

import step5_helpers as s5
from step5_helpers import (EARLIER_BEFORE, EARLIER_HERE, FINDING_DECIDED, FINDING_KEEP_EARLIER, FINDING_RAISED, FINDING_USE_NEW,
                           RENT_MESSAGE, ask_finding, brief_entry, entry, finding_block, h, report, s4, summary_call)

OK = "Noted."
SAVED = h.SAVED
HOLDS = [h.say_text(f"Hold {k}.") for k in range(9)]       # the 9 replies after a save_input that the finding holds back
NAME = "monthly_spending"
MESSAGE_45 = "My monthly spending is 4,500"
SAVE = h.save_input(NAME, "4,500", "said now")
BLOCK = finding_block("earlier", claim="4,500", reference="4,000", name=NAME, when=EARLIER_BEFORE)
OPTIONS = [FINDING_USE_NEW.format(value="4,500"), FINDING_KEEP_EARLIER.format(value="4,000")]
EARLIER_ROW = {"value": "4,000", "note": "said last week", "ts": "2026-03-01T09:00:00+00:00",
               "session_id": "an-earlier-session"}


@pytest.fixture
def stored(conn):
    s5.put_input(conn, NAME, "4,000", note="said last week")


def tool_result(model, call_index, position=-1):
    return h.tool_message(model, call_index, position)


def talks(talk, script, answers=("/quit",), **options):
    """The first reply of the verifier says there is nothing to report."""
    return talk([report(), *script], list(answers), question=options.pop("question", MESSAGE_45), **options)


def input_row(conn):
    return s5.saved_input(conn, NAME)


# ---- rule 4: a different value opens a finding --------------------------------------------------------------------------------

def test_a_different_value_is_not_saved_and_opens_a_finding(talk, conn, stored):
    model, _ = talks(talk, [SAVE, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    result = tool_result(model, 2)
    assert result["content"] == FINDING_RAISED.format(name=NAME, id=1) and result["is_error"] is True


def test_the_finding_of_kind_earlier(talk, conn, stored, findings):
    talk([report(), SAVE, *HOLDS], ["/quit"], question=MESSAGE_45)
    [finding] = findings.list_findings(conn, session_id=s5.SESSION)
    assert list(finding) == s5.FINDING_KEYS
    assert (finding["kind"], finding["status"], finding["session_id"]) == ("earlier", "open", s5.SESSION)
    assert (finding["claim"], finding["claim_figure"]) == ("4,500", "4,500")
    assert (finding["reference"], finding["reference_figure"]) == ("4,000", "4,000")
    assert finding["input"] == NAME and finding["earlier"] == EARLIER_ROW and finding["pending_note"] == "said now"
    assert finding["summary"] is None and finding["block"] == BLOCK and finding["options"] == OPTIONS
    assert (finding["decision"], finding["choice"], finding["chosen"]) == (None, None, None)


def test_nothing_is_saved_or_recorded_but_the_finding(talk, conn, stored):
    talk([report(), SAVE, *HOLDS], ["/quit"], question=MESSAGE_45)
    assert input_row(conn)["value"] == json.dumps("4,000") and input_row(conn)["note"] == "said last week"
    assert s5.events(conn, "ask.input_saved") == [] and s5.payloads(conn, "ask.correction")[0]["reason"] == "finding"
    kinds = s5.kinds_after_start(conn)
    assert kinds[:4] == ["ask.message", "verify.report", "finding.opened", "ask.correction"]


def test_the_saved_value_of_this_conversation_is_said_to_be_from_it(talk, conn, findings):
    s5.put_input(conn, NAME, "4,000", note="said last week", session_id=s5.SESSION)
    talk([report(), SAVE, *HOLDS], ["/quit"], question=MESSAGE_45)
    [finding] = findings.list_findings(conn, session_id=s5.SESSION)
    assert finding["block"] == finding_block("earlier", claim="4,500", reference="4,000", name=NAME, when=EARLIER_HERE)
    assert finding["earlier"]["session_id"] == s5.SESSION


def test_a_saved_value_that_is_not_text_is_written_with_json_dumps(talk, conn, findings):
    s5.put_input(conn, NAME, 4000)
    talk([report(), SAVE, *HOLDS], ["/quit"], question=MESSAGE_45)
    [finding] = findings.list_findings(conn, session_id=s5.SESSION)
    assert finding["reference"] == "4000" and finding["reference_figure"] == "4000" and finding["earlier"]["value"] == "4000"


def test_the_finding_is_put_to_the_person_with_its_block(talk, conn, stored):
    model, person = talks(talk, [SAVE, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    k = person.log.index(("say", BLOCK))
    assert person.log[k + 1] == ("ask", s4.DECISION_QUESTION)
    assert s5.payloads(conn, "ask.decision_asked") == [{"arguments": {"finding": 1, "runs": []}, "block": BLOCK}]


@pytest.mark.parametrize("answer, choice, option, use, saved", [
    ("1", "1", OPTIONS[0], "4,500", True), ("2", "2", OPTIONS[1], "4,000", False),
    ("neither, 4,200", "something else", None, None, False)])
def test_the_result_for_the_agent(talk, conn, stored, answer, choice, option, use, saved):
    model, _ = talks(talk, [SAVE, ask_finding(1), h.say_text(OK)], [answer, "/quit"])
    result = json.loads(tool_result(model, 3)["content"])
    assert list(result) == ["outcome", "decision", "finding", "choice", "option", "use", "said", "saved"]
    assert result == {"outcome": "decided", "decision": 1, "finding": 1, "choice": choice, "option": option, "use": use,
                      "said": answer, "saved": saved}


def test_choice_one_saves_the_new_value_with_the_pending_note(talk, conn, stored):
    talks(talk, [SAVE, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    row = input_row(conn)
    assert json.loads(row["value"]) == "4,500" and row["note"] == "said now" and row["session_id"] == s5.SESSION
    assert s5.payloads(conn, "ask.input_saved") == [{"name": NAME, "value": "4,500", "note": "said now"}]
    [finding] = s5.finding_rows(conn)
    assert (finding["status"], finding["choice"], finding["chosen"]) == ("decided", "1", "4,500")
    assert s5.payloads(conn, "finding.closed") == [{"finding": 1, "decision": 1, "choice": "1", "chosen": "4,500",
                                                    "saved": True}]


def test_the_events_of_choice_one_in_order(talk, conn, stored):
    talks(talk, [SAVE, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    kinds = s5.kinds_after_start(conn)
    start = kinds.index("ask.decision_asked")
    assert kinds[start:start + 4] == ["ask.decision_asked", "ask.decision", "ask.input_saved", "finding.closed"]


@pytest.mark.parametrize("answer, choice, chosen", [("2", "2", "4,000"), ("something else", "something else", None)])
def test_the_other_choices_save_nothing(talk, conn, stored, answer, choice, chosen):
    talks(talk, [SAVE, ask_finding(1), h.say_text(OK)], [answer, "/quit"])
    assert input_row(conn)["value"] == json.dumps("4,000") and s5.events(conn, "ask.input_saved") == []
    [finding] = s5.finding_rows(conn)
    assert (finding["choice"], finding["chosen"]) == (choice, chosen)
    assert s5.payloads(conn, "finding.closed")[0]["saved"] is False


def test_the_decision_is_recorded_like_any_finding(talk, conn, stored):
    talks(talk, [SAVE, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    [decision] = h.rows(conn, "decisions")
    assert (decision["kind"], decision["step_id"], decision["question"], decision["choice"]) == ("finding", None, BLOCK, "1")
    assert json.loads(decision["options"]) == OPTIONS


def test_the_example_of_the_spec_three_agent_calls_and_no_verifier_when_there_is_no_figure(talk, conn):
    s5.put_input(conn, "monthly_rent", "1,000", note="said last week")
    save = h.save_input("monthly_rent", "1,150", "from the brief")
    model, _ = talk([save, ask_finding(1), h.say_text(OK)], ["1", "/quit"], question="Please keep my rent up to date")
    assert model.roles() == ["analyst", "analyst", "analyst"]
    assert tool_result(model, 0 + 1)["content"] == FINDING_RAISED.format(name="monthly_rent", id=1)
    assert json.loads(s5.saved_input(conn, "monthly_rent")["value"]) == "1,150"
    assert s5.events(conn, "verify.report") == []


# ---- the checks of 5.9 come first --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("call, error", [
    (h.save_input("Not Snake", "4,500"), h.BAD_NAME),
    (h.save_input(NAME, ""), h.EMPTY_VALUE),
])
def test_a_bad_name_or_an_empty_value_is_refused_as_before(talk, conn, stored, call, error):
    model, _ = talks(talk, [call, h.say_text(OK)])
    assert tool_result(model, 2)["content"] == error and s5.finding_rows(conn) == []


def test_an_unbacked_value_is_refused_by_the_number_check_and_opens_no_finding(talk, conn, stored):
    model, _ = talks(talk, [h.save_input(NAME, "9,999", "n"), h.say_text(OK)])
    assert tool_result(model, 2)["content"].startswith("These numbers did not come from the person")
    assert s5.finding_rows(conn) == [] and s5.payloads(conn, "ask.correction")[0]["reason"] == "save_input"


# ---- rule 1: no row, or the same value ---------------------------------------------------------------------------------------------

def test_a_name_with_no_row_is_saved(talk, conn):
    model, _ = talks(talk, [SAVE, h.say_text(OK)])
    assert tool_result(model, 2)["content"] == SAVED and json.loads(input_row(conn)["value"]) == "4,500"
    assert s5.finding_rows(conn) == []


@pytest.mark.parametrize("stored_value", ["4,500", "4500", "4500.00", "  4,500 ", 4500])
def test_the_same_value_is_saved_again_without_a_finding(talk, conn, stored_value):
    s5.put_input(conn, NAME, stored_value, note="said last week")
    model, _ = talks(talk, [SAVE, h.say_text(OK)])
    assert tool_result(model, 2)["content"] == SAVED and s5.finding_rows(conn) == []
    assert input_row(conn)["note"] == "said now" and json.loads(input_row(conn)["value"]) == "4,500"


def test_a_value_that_differs_only_a_little_is_still_a_different_value(talk, conn):
    s5.put_input(conn, NAME, "4,500")
    model, _ = talks(talk, [h.save_input(NAME, "4,500.50", "n"), ask_finding(1), h.say_text(OK)], ["2", "/quit"],
                     question="My spending is 4,500.50")
    assert "opened finding 1" in tool_result(model, 2)["content"]


# ---- rule 2: the person chose this figure ----------------------------------------------------------------------------------------------

def test_a_chosen_figure_of_a_data_finding_is_saved(talk, conn, example_loaded, stored):
    save = h.save_input(NAME, "4132.31", "from my files")
    model, _ = talk([summary_call(), report(entry()), ask_finding(1), save, h.say_text(OK)], ["2", "/quit"])
    assert tool_result(model, 4)["content"] == SAVED
    assert json.loads(input_row(conn)["value"]) == "4132.31" and len(s5.finding_rows(conn)) == 1


def test_a_chosen_figure_of_a_brief_finding_is_saved(talk, conn):
    s5.put_input(conn, "monthly_rent", "1,000")
    save = h.save_input("monthly_rent", "1150", "from the brief")
    model, _ = talk([report(brief_entry()), ask_finding(1), save, h.say_text(OK)], ["2", "/quit"], question=RENT_MESSAGE)
    assert tool_result(model, 3)["content"] == SAVED and len(s5.finding_rows(conn)) == 1


def test_a_figure_that_was_not_chosen_is_not_saved(talk, conn, example_loaded, stored):
    """The person kept what they said (5k = 5000): the data figure is not chosen, so it opens a finding."""
    save = h.save_input(NAME, "4132.31", "from my files")
    script = [summary_call(), report(entry()), ask_finding(1), save, ask_finding(2), h.say_text(OK)]
    model, _ = talk(script, ["1", "2", "/quit"])
    assert tool_result(model, 4)["content"] == FINDING_RAISED.format(name=NAME, id=2)


def test_something_else_chooses_no_figure(talk, conn, example_loaded, stored):
    save = h.save_input(NAME, "4132.31", "from my files")
    script = [summary_call(), report(entry()), ask_finding(1), save, ask_finding(2), h.say_text(OK)]
    model, _ = talk(script, ["neither", "2", "/quit"])
    assert tool_result(model, 4)["content"] == FINDING_RAISED.format(name=NAME, id=2)


# ---- rule 3: already decided ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("answer", ["2", "something else"])
def test_a_value_the_person_already_decided_about_is_not_asked_again(talk, conn, stored, answer):
    model, _ = talks(talk, [SAVE, ask_finding(1), SAVE, h.say_text(OK)], [answer, "/quit"])
    result = tool_result(model, 4)
    assert result["content"] == FINDING_DECIDED.format(name=NAME, id=1) and result["is_error"] is True
    assert len(s5.finding_rows(conn)) == 1 and len(s5.events(conn, "finding.opened")) == 1
    assert input_row(conn)["value"] == json.dumps("4,000")


def test_a_refusal_for_a_decided_value_records_nothing(talk, conn, stored):
    talks(talk, [SAVE, ask_finding(1), SAVE, h.say_text(OK)], ["2", "/quit"])
    kinds = s5.kinds_after_start(conn)
    assert kinds[kinds.index("finding.closed") + 1:] == ["ask.reply"]


def test_a_value_that_is_the_same_as_the_decided_claim_in_another_form(talk, conn, stored):
    again = h.save_input(NAME, "4500", "said now")
    model, _ = talks(talk, [SAVE, ask_finding(1), again, h.say_text(OK)], ["2", "/quit"], question="My spending is 4,500, I mean 4500")
    assert tool_result(model, 4)["content"] == FINDING_DECIDED.format(name=NAME, id=1)


def test_another_value_for_the_same_name_is_a_new_finding(talk, conn, stored):
    other = h.save_input(NAME, "4,600", "said now")
    model, _ = talks(talk, [SAVE, ask_finding(1), other, ask_finding(2), h.say_text(OK)], ["2", "2", "/quit"],
                     question="My monthly spending is 4,500, or maybe 4,600")
    assert tool_result(model, 4)["content"] == FINDING_RAISED.format(name=NAME, id=2)
    assert [f["kind"] for f in s5.finding_rows(conn)] == ["earlier", "earlier"]


def test_the_same_value_for_another_name_is_a_new_finding(talk, conn, stored):
    s5.put_input(conn, "monthly_income", "4,000")
    other = h.save_input("monthly_income", "4,500", "said now")
    model, _ = talks(talk, [SAVE, ask_finding(1), other, ask_finding(2), h.say_text(OK)], ["2", "2", "/quit"])
    assert tool_result(model, 4)["content"] == FINDING_RAISED.format(name="monthly_income", id=2)


def test_a_finding_of_another_conversation_does_not_decide_it(talk, conn, stored, findings):
    findings.open_finding(conn, session_id="another", kind="earlier", claim="4,500", claim_figure="4,500", reference="4,000",
                          reference_figure="4,000", input_name=NAME, earlier=EARLIER_ROW, pending_note="n")
    conn.execute("UPDATE findings SET status = 'decided', choice = '2', chosen = '4,000' WHERE id = 1")
    conn.commit()
    model, _ = talks(talk, [SAVE, ask_finding(2), h.say_text(OK)], ["2", "/quit"])
    assert tool_result(model, 2)["content"] == FINDING_RAISED.format(name=NAME, id=2)


# ---- while a finding is open ------------------------------------------------------------------------------------------------------------------

def test_while_the_finding_is_open_the_save_is_refused_as_open(talk, conn, stored):
    model, _ = talks(talk, [SAVE, SAVE, ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert tool_result(model, 3)["content"] == s5.FINDING_OPEN.format(id=1)
    assert [p["tool"] for p in s5.payloads(conn, "finding.refused")] == ["save_input"]
