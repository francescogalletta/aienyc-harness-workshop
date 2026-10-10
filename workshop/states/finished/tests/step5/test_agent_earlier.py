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
























# ---- the checks of 5.9 come first --------------------------------------------------------------------------------------------------





# ---- rule 1: no row, or the same value ---------------------------------------------------------------------------------------------







# ---- rule 2: the person chose this figure ----------------------------------------------------------------------------------------------

def test_a_chosen_figure_of_a_data_finding_is_saved(talk, conn, example_loaded, stored):
    save = h.save_input(NAME, "4132.31", "from my files")
    model, _ = talk([summary_call(), report(entry()), ask_finding(1), save, h.say_text(OK)], ["2", "/quit"])
    assert tool_result(model, 4)["content"] == SAVED
    assert json.loads(input_row(conn)["value"]) == "4132.31" and len(s5.finding_rows(conn)) == 1








# ---- rule 3: already decided ------------------------------------------------------------------------------------------------------------













# ---- while a finding is open ------------------------------------------------------------------------------------------------------------------

