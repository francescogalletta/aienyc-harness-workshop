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


def test_a_judgment_shows_its_step_its_choice_and_its_runs(decisions, conn):
    decision = record(decisions, conn, kind="judgment", step_id="s2", question=BLOCK,
                      options=["Keep the date", "Move the date"], choice="2", words="2", runs=[5, 6])
    lines = run_cli(["decisions"]).stdout.splitlines()
    assert lines[0] == first_line(decision, "s2", "2. Move the date", "5, 6")
    assert lines[1:] == block_lines(BLOCK, "2")


def test_every_session_oldest_first_newest_last(decisions, conn):
    first = record(decisions, conn, session_id="chat-a")
    second = record(decisions, conn, session_id="chat-b", kind="build", step_id="s1", question=h.STEP_BLOCK,
                    choice="yes", words="Yes, please")
    third = record(decisions, conn, session_id="chat-a", choice="no", words="not yet")
    lines = run_cli(["decisions"]).stdout.splitlines()
    heads = [line for line in lines if not line.startswith("  ")]
    assert heads == [first_line(first, "-", "yes", "-"), first_line(second, "s1", "yes", "-"),
                     first_line(third, "-", "no", "-")]
