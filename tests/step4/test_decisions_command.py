"""SPEC 8.7: `python -m harness decisions` prints every decision of every session, oldest first."""
import step4_helpers as s4
from step4_helpers import NO_DECISIONS, h

run_cli = h.run_cli

GATE = s4.gate_block(s4.surplus_item())
BLOCK = s4.decision_block("Should the date stay or move?", ["Keep the date", "Move the date"], 2, "It leaves room.",
                          {"id": "s2", "name": "Decide how much to set aside"})


def record(decisions, conn, **changes):
    arguments = {"session_id": "chat-a", "kind": "assumptions", "step_id": None, "question": GATE, "options": [],
                 "choice": "yes", "words": "yes", "runs": []}
    arguments.update(changes)
    return decisions.record_decision(conn, **arguments)


def first_line(decision, step, chose, runs):
    return f"{decision['id']}  {decision['ts']}  {decision['kind']}  step: {step}  chose: {chose}  runs: {runs}"


def block_lines(question, words):
    return ["  " + line for line in question.split("\n")] + [f"  in their words: {words}"]


def test_with_no_decision_it_says_so_and_exits_0():
    result = run_cli(["decisions"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == NO_DECISIONS and result.stderr == ""


def test_it_runs_migrate_first_and_needs_no_brief_and_no_model(write_script):
    write_script([])                                     # a model call would run out of script and fail
    result = run_cli(["decisions"])
    assert result.returncode == 0 and result.stdout.strip() == NO_DECISIONS


def test_an_assumptions_decision_is_four_lines_for_its_block_and_its_words(decisions, conn):
    decision = record(decisions, conn)
    result = run_cli(["decisions"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [first_line(decision, "-", "yes", "-"), *block_lines(GATE, "yes")]


def test_a_judgment_shows_its_step_its_choice_and_its_runs(decisions, conn):
    decision = record(decisions, conn, kind="judgment", step_id="s2", question=BLOCK,
                      options=["Keep the date", "Move the date"], choice="2", words="2", runs=[5, 6])
    lines = run_cli(["decisions"]).stdout.splitlines()
    assert lines[0] == first_line(decision, "s2", "2. Move the date", "5, 6")
    assert lines[1:] == block_lines(BLOCK, "2")


def test_something_else_is_shown_with_the_words_the_person_typed(decisions, conn):
    decision = record(decisions, conn, kind="judgment", step_id="s2", question=BLOCK,
                      options=["Keep the date", "Move the date"], choice="something else",
                      words="Neither, I will ask my landlord", runs=[1])
    lines = run_cli(["decisions"]).stdout.splitlines()
    assert lines[0] == first_line(decision, "s2", "something else", "1")
    assert lines[-1] == "  in their words: Neither, I will ask my landlord"


def test_a_build_decision_for_a_step_not_in_the_brief_shows_the_label(decisions, conn):
    decision = record(decisions, conn, kind="build", step_id="added_1", question=h.NEW_BLOCK, choice="no", words="not now")
    lines = run_cli(["decisions"]).stdout.splitlines()
    assert lines[0] == first_line(decision, "added_1 (not in the brief)", "no", "-")
    assert lines[1:] == block_lines(h.NEW_BLOCK, "not now")


def test_every_session_oldest_first_newest_last(decisions, conn):
    first = record(decisions, conn, session_id="chat-a")
    second = record(decisions, conn, session_id="chat-b", kind="build", step_id="s1", question=h.STEP_BLOCK,
                    choice="yes", words="Yes, please")
    third = record(decisions, conn, session_id="chat-a", choice="no", words="not yet")
    lines = run_cli(["decisions"]).stdout.splitlines()
    heads = [line for line in lines if not line.startswith("  ")]
    assert heads == [first_line(first, "-", "yes", "-"), first_line(second, "s1", "yes", "-"),
                     first_line(third, "-", "no", "-")]


def test_the_lines_follow_each_other_without_blank_lines_between(decisions, conn):
    record(decisions, conn, session_id="a")
    record(decisions, conn, session_id="b", choice="no", words="no")
    lines = run_cli(["decisions"]).stdout.splitlines()
    assert "" not in lines and len(lines) == 2 * (1 + len(GATE.split("\n")) + 1)


def test_each_line_of_the_question_has_two_spaces_before_it_whatever_it_starts_with(decisions, conn):
    record(decisions, conn, question="first line\n  indented line\n    deeper")
    lines = run_cli(["decisions"]).stdout.splitlines()
    assert lines[1:4] == ["  first line", "    indented line", "      deeper"]


def test_the_runs_are_joined_by_a_comma_and_a_space(decisions, conn):
    decision = record(decisions, conn, kind="judgment", step_id=None, question=BLOCK, options=["A", "B"],
                      choice="1", words="1", runs=[3, 10, 4])
    assert run_cli(["decisions"]).stdout.splitlines()[0] == first_line(decision, "-", "1. A", "3, 10, 4")
