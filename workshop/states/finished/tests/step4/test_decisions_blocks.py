"""SPEC 8.1 to 8.3: `one_line`, `assumption_set`, `gate_block`, `decision_block` and `read_choice`, as functions."""
import pytest

import step4_helpers as s4
from step4_helpers import ACCEPT_WORDS, SURPLUS, h

# ---- one_line ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("plain", "plain"), ("  trimmed  ", "trimmed"), ("a   b", "a b"), ("a\nb\tc", "a b c"), ("\n\n  x \n y \n", "x y"),
    ("", ""), ("   \n\t ", ""), ("one two", "one two"), ("keep, punctuation. as-is", "keep, punctuation. as-is")])
def test_one_line_trims_and_makes_every_run_of_white_space_one_space(decisions, text, expected):
    assert decisions.one_line(text) == expected


# ---- assumption_set --------------------------------------------------------------------------------------

def test_an_assumption_set_is_a_frozenset_of_trimmed_case_folded_sentences(decisions):
    result = decisions.assumption_set(["  Spending   stays\nthe SAME. ", "Income is steady."])
    assert isinstance(result, frozenset)
    assert result == frozenset({"spending stays the same.", "income is steady."})


def test_empty_sentences_are_left_out(decisions):
    assert decisions.assumption_set(["", "   ", "\n"]) == frozenset()
    assert decisions.assumption_set([]) == frozenset()
    assert decisions.assumption_set(["", "Rent is fixed."]) == frozenset({"rent is fixed."})


def test_order_and_repeats_do_not_matter(decisions):
    a, b = "Rent is fixed.", "Bonus is paid."
    assert decisions.assumption_set([a, b]) == decisions.assumption_set([b, a, "  RENT is   fixed. "])


def test_case_folding_is_used_not_lower_casing(decisions):
    assert decisions.assumption_set(["Straße"]) == decisions.assumption_set(["STRASSE"]) == frozenset({"strasse"})


def test_sets_match_only_when_they_are_equal(decisions):
    one = decisions.assumption_set(["Rent is fixed."])
    both = decisions.assumption_set(["Rent is fixed.", "Bonus is paid."])
    assert one != both and one < both
    assert decisions.assumption_set(["Rent is fixed"]) != one            # punctuation counts


# ---- gate_block ---------------------------------------------------------------------------------------------

def test_a_gate_block_for_one_item_byte_for_byte(decisions):
    block = decisions.gate_block([(SURPLUS, ["Spending stays the same each month."], "what comes in less what goes out")])
    assert block == (
        "Before working this out, the assistant would take some things as given that you have not confirmed:\n"
        "  1. The money left over each month after spending.\n"
        "     Taking as given:\n"
        "       - Spending stays the same each month.\n"
        "     Expecting: what comes in less what goes out")


def test_the_indents_are_2_5_7_and_5_spaces(decisions):
    lines = decisions.gate_block([("Works out a thing.", ["A sentence."], "a result")]).split("\n")
    assert [len(line) - len(line.lstrip(" ")) for line in lines] == [0, 2, 5, 7, 5]


def test_several_items_are_numbered_from_1_in_order(decisions):
    block = decisions.gate_block([("First thing.", ["One."], "x"), ("Second thing.", ["Two.", "Three."], "y"),
                                  ("Third thing.", ["Four."], "z")])
    assert block == s4.gate_block(("First thing.", ["One."], "x"), ("Second thing.", ["Two.", "Three."], "y"),
                                  ("Third thing.", ["Four."], "z"))
    assert [line for line in block.split("\n") if line.startswith("  ") and line[2].isdigit()] == [
        "  1. First thing.", "  2. Second thing.", "  3. Third thing."]


def test_each_text_is_made_one_line(decisions):
    block = decisions.gate_block([("  Works   out\na thing. ", ["  Rent   stays\nthe same. "], " about\n  two  lines ")])
    assert block.split("\n")[1:] == ["  1. Works out a thing.", "     Taking as given:", "       - Rent stays the same.",
                                     "     Expecting: about two lines"]


def test_a_sentence_is_shown_once_at_its_first_place_in_the_list_sent(decisions):
    block = decisions.gate_block([("A thing.", ["Rent  stays the same.", "Bonus is paid.", "RENT STAYS THE SAME.", "",
                                                "bonus is  PAID."], "x")])
    bullets = [line for line in block.split("\n") if line.startswith("       - ")]
    assert bullets == ["       - Rent stays the same.", "       - Bonus is paid."]


# ---- decision_block -----------------------------------------------------------------------------------------

def test_a_decision_block_without_a_step_or_a_recommendation(decisions):
    block = decisions.decision_block(question="Should the date stay or move?", options=["Keep the date", "Move the date"],
                                     recommendation=None, why="", step=None)
    assert block == ("Only you can decide this:\n"
                     "  Should the date stay or move?\n"
                     "    1. Keep the date\n"
                     "    2. Move the date")


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


def test_the_step_of_the_process_may_be_an_added_one(decisions):
    step = h.added_step(1)
    block = decisions.decision_block(question="Which way?", options=["A", "B"], recommendation=None, why="", step=step)
    assert block.split("\n")[0] == (
        "Only you can decide this. It is step added_1 (not in the brief) of the plan: the cost over a whole year.")


def test_every_text_of_a_decision_block_is_made_one_line(decisions):
    step = {"id": "s2", "name": "  Decide   how much\nto set aside "}
    block = decisions.decision_block(question="  Which\n way?  ", options=["  A   one ", "B\ntwo"], recommendation=1,
                                     why="  Because   it\nis safer. ", step=step)
    assert block.split("\n") == [
        "Only you can decide this. It is step s2 of the plan: Decide how much to set aside.",
        "  Which way?", "    1. A one", "    2. B two", "  The assistant suggests 1: Because it is safer."]


def test_the_indents_of_a_decision_block_are_0_2_4_and_2(decisions):
    block = decisions.decision_block(question="Q?", options=["A", "B"], recommendation=1, why="w", step=None)
    assert [len(line) - len(line.lstrip(" ")) for line in block.split("\n")] == [0, 2, 4, 4, 2]


def test_the_helper_of_these_tests_agrees(decisions):
    args = dict(question="Q?", options=["A", "B"], recommendation=2, why="w", step={"id": "s2", "name": "N"})
    assert decisions.decision_block(**args) == s4.decision_block("Q?", ["A", "B"], 2, "w", {"id": "s2", "name": "N"})


# ---- read_choice ---------------------------------------------------------------------------------------------

OPTIONS = ["Keep the date", "Move the date", "Ask the landlord"]


@pytest.mark.parametrize("answer, expected", [
    ("1", "1"), ("2", "2"), ("3", "3"), ("2.", "2"), ("2)", "2"), ("option 2", "2"), ("Option 3", "3"),
    ("OPTION  1.", "1"), ("option\t2)", "2"), ("  2  ", "2"), ("\n3\n", "3")])
def test_a_number_picks_its_option(decisions, answer, expected):
    assert decisions.read_choice(answer, OPTIONS, None) == expected


@pytest.mark.parametrize("answer", ["4", "5", "9", "option 4", "0", "10", "2 please", "option", "2,", "1 2", "#2",
                                    "the 2nd", "option two", "2.."])
def test_a_number_that_is_not_an_option_or_not_alone_is_something_else(decisions, answer):
    assert decisions.read_choice(answer, OPTIONS, None) == "something else"


def test_the_number_is_returned_as_text(decisions):
    assert decisions.read_choice("2", OPTIONS, None) == "2" and isinstance(decisions.read_choice("2", OPTIONS, None), str)


@pytest.mark.parametrize("answer, expected", [
    ("Keep the date", "1"), ("move the date", "2"), ("  ASK   the\nlandlord ", "3"), ("MOVE THE DATE", "2")])
def test_an_option_text_picks_it_ignoring_case_and_spacing(decisions, answer, expected):
    assert decisions.read_choice(answer, OPTIONS, None) == expected


def test_an_option_text_with_other_words_does_not(decisions):
    assert decisions.read_choice("Keep the date please", OPTIONS, None) == "something else"
    assert decisions.read_choice("Keep the", OPTIONS, None) == "something else"


def test_the_first_option_with_that_text_wins(decisions):
    assert decisions.read_choice("same", ["same", "other", "SAME"], None) == "1"


@pytest.mark.parametrize("word", sorted(ACCEPT_WORDS) + ["YES", "Yes.", "Ok", "  yes  ", "SÍ".lower(), "Y"])
def test_an_accept_word_takes_the_suggestion(decisions, word):
    assert decisions.read_choice(word, OPTIONS, 2) == "2"
    assert decisions.read_choice(word, OPTIONS, 3) == "3"


def test_an_accept_word_without_a_suggestion_is_something_else(decisions):
    assert decisions.read_choice("yes", OPTIONS, None) == "something else"
    assert decisions.read_choice("/accept", OPTIONS, None) == "something else"


@pytest.mark.parametrize("answer", ["yeah", "yes please", "no", "Neither of those", "I would rather wait", "/quit", "",
                                    "   ", "/skip", "yes, but later"])
def test_anything_else_is_something_else(decisions, answer):
    assert decisions.read_choice(answer, OPTIONS, 1) == "something else"
    assert decisions.read_choice(answer, OPTIONS, None) == "something else"


def test_a_number_beats_an_option_text_that_looks_like_it(decisions):
    assert decisions.read_choice("2", ["2", "x"], None) == "2"
    assert decisions.read_choice("1", ["2", "x"], None) == "1"


def test_a_digit_that_is_no_option_may_still_be_an_option_text(decisions):
    assert decisions.read_choice("3", ["3", "4"], None) == "1"            # rule 1 fails (3 > 2 options), rule 2 holds


def test_an_option_text_beats_the_suggestion(decisions):
    assert decisions.read_choice("yes", ["yes", "no"], 2) == "1"
    assert decisions.read_choice("no", ["yes", "no"], 1) == "2"


def test_a_number_beats_the_suggestion(decisions):
    assert decisions.read_choice("1", OPTIONS, 3) == "1"
