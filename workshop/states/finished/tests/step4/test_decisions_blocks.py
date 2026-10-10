"""SPEC 8.1 to 8.3: `one_line`, `assumption_set`, `gate_block`, `decision_block` and `read_choice`, as functions."""
import pytest

import step4_helpers as s4
from step4_helpers import ACCEPT_WORDS, SURPLUS, h


def test_a_gate_block_for_one_item_byte_for_byte(decisions):
    block = decisions.gate_block([(SURPLUS, ["Spending stays the same each month."], "what comes in less what goes out")])
    assert block == (
        "Before working this out, the assistant would take some things as given that you have not confirmed:\n"
        "  1. The money left over each month after spending.\n"
        "     Taking as given:\n"
        "       - Spending stays the same each month.\n"
        "     Expecting: what comes in less what goes out")


def test_a_decision_block_with_a_step_and_a_recommendation(decisions):
    step = {"id": "s2", "name": "Decide how much to set aside"}
    block = decisions.decision_block(question="Which way?", options=["A", "B", "C"], recommendation=2,
                                     why="It is the safer one.", step=step)
    assert block == ("Only you can decide this. It is step s2 of the plan: Decide how much to set aside.\n"
                     "  Which way?\n"
                     "    1. A\n"
                     "    2. B\n"
                     "    3. C\n"
                     "  The assistant suggests 2: It is the safer one.")


OPTIONS = ["Keep the date", "Move the date", "Ask the landlord"]
