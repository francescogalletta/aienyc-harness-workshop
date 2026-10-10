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










# ---- reading the answer ---------------------------------------------------------------------------------------------------







# ---- what is recorded --------------------------------------------------------------------------------------------------------





def test_nothing_is_saved_for_a_data_finding(talk, conn, example_loaded):
    decide(talk, "2")
    assert h.rows(conn, "inputs") == [] and s5.events(conn, "ask.input_saved") == []




# ---- the checks -------------------------------------------------------------------------------------------------------------------







@pytest.mark.parametrize("value", [99])
def test_a_finding_that_is_not_an_open_one_is_refused(talk, conn, example_loaded, value):
    arguments = {"finding": value, "runs": []}
    model, person = talk([*OPEN, h.tool("ask_decision", arguments), ask_finding(1), h.say_text(OK)], ["1", "/quit"])
    assert h.tool_message(model, 3)["content"] == FINDING_NOT_OPEN.format(finding=json.dumps(value))
    assert s5.payloads(conn, "ask.decision_refused") == [{"error": FINDING_NOT_OPEN.format(finding=json.dumps(value)),
                                                          "arguments": arguments}]
    assert asked(person).count(s4.DECISION_QUESTION) == 1 and person.told.count(DATA_BLOCK) == 1














# ---- the limit of decisions ----------------------------------------------------------------------------------------------------------









# ---- a side conversation ---------------------------------------------------------------------------------------------------------------

