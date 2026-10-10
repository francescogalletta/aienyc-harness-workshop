"""SPEC 8.7 and 8.5: side conversations as a person meets them in `python -m harness ask`: the terminal reads after
`aside> ` when the question is marked. `build`, `adopt` and the interview never offer `/aside`."""
import os
import sqlite3

import pytest

import step4_helpers as s4
from step4_helpers import (ASIDE_CARRY, ASIDE_CLOSE, ASIDE_OPEN, ASIDE_THINKING, GATE_QUESTION, h, marked, side)

OK = "Done."
GATE = s4.gate_block(s4.surplus_item())
run_cli = h.run_cli


def typed(*answers):
    return "".join(answer + "\n" for answer in answers)


def database():
    return sqlite3.connect(os.environ["HARNESS_DB"])


@pytest.fixture
def ready(conn, save_confirmed_brief):
    save_confirmed_brief(h.make_brief())
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")


def ask_command(write_script, script, *lines, question=h.QUESTION):
    write_script([h.no_findings(), *script])               # (step 5) the verifier checks the figures of the question first
    return run_cli(["ask", *question.split()], typed(*lines))


def prompted(text, prompt="> "):
    return f"\n{text}\n\n{prompt}"


# ---- the prompt -------------------------------------------------------------------------------------------------------------------

def test_a_marked_question_is_read_after_the_aside_prompt(ready, write_script):
    result = ask_command(write_script, [h.say_text("Hello."), side("It is a thing."), h.say_text("Hello again.")],
                         "/aside What is it?", "/back", "no", "/quit")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert prompted(marked("It is a thing."), "aside> ") in out
    assert prompted(marked(ASIDE_CARRY), "aside> ") in out
    assert out.count(prompted("Hello.")) == 2


def test_the_prompt_returns_to_the_ordinary_one_after_the_banner(ready, write_script):
    result = ask_command(write_script, [h.say_text("Hello."), side("It is a thing.")], "/aside What is it?", "/back", "no", "/quit")
    after = result.stdout.split(ASIDE_CLOSE)[1]
    assert after.startswith("\n") and after.endswith("\n\n> ")
    assert "aside>" not in after


def test_the_banners_the_marks_and_the_progress_lines(ready, write_script):
    result = ask_command(write_script, [h.say_text("Hello."), side("It is a thing.\nIt has two lines.")],
                         "/aside What is it?", "/back", "no", "/quit")
    out = result.stdout
    assert ASIDE_OPEN + "\n" in out and ASIDE_CLOSE + "\n" in out
    assert marked(ASIDE_THINKING) + "\n" in out
    assert "aside | It is a thing.\naside | It has two lines.\n" in out
    assert out.index(ASIDE_OPEN) < out.index(marked(ASIDE_THINKING)) < out.index(ASIDE_CLOSE)


def test_the_gate_with_a_side_conversation_at_a_terminal(ready, write_script):
    script = [s4.run(), side("Steady means it does not change."), h.say_text(OK)]
    result = ask_command(write_script, script, "/aside What does steady mean?", "/back", "no", "yes", "/quit")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert out.count(GATE) == 2 and out.count(prompted(GATE_QUESTION)) == 2
    first = out.index(prompted(GATE_QUESTION))
    assert first < out.index(ASIDE_OPEN) < out.index(ASIDE_CLOSE) < out.index(GATE, out.index(ASIDE_CLOSE))
    assert prompted(OK) in out
    assert database().execute("SELECT module, output FROM calc_runs").fetchall() == [("monthly_surplus", '"2000"')]


def test_the_end_of_input_inside_a_side_conversation_ends_it_and_the_conversation(ready, write_script):
    result = ask_command(write_script, [h.say_text("Hello."), side("It is a thing.")], "/aside What is it?")
    assert result.returncode == 0, result.stderr
    assert prompted(marked("It is a thing."), "aside> ") in result.stdout
    assert result.stdout.rstrip().endswith(ASIDE_CLOSE)
    row = database().execute("SELECT payload FROM events WHERE kind = 'aside.closed'").fetchone()
    assert '"how": "quit"' in row[0]


def test_quit_inside_a_side_conversation_exits_0(ready, write_script):
    result = ask_command(write_script, [h.say_text("Hello."), side("It is a thing.")], "/aside What is it?", "/quit")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_the_command_alone_asks_what_to_talk_through(ready, write_script):
    result = ask_command(write_script, [h.say_text("Hello."), side("It is a thing.")], "/aside", "What is it?", "/back", "no", "/quit")
    assert prompted(marked(s4.ASIDE_FIRST), "aside> ") in result.stdout


def test_a_side_conversation_at_the_opening_question(ready, write_script):
    write_script([side("It is a thing."), h.no_findings(), h.say_text("Hello.")])      # (step 5) the verifier after the question
    result = run_cli(["ask"], typed("/aside What is a sinking fund?", "/back", "no", h.QUESTION, "/quit"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.count(prompted(h.OPENING)) == 2
    assert prompted("Hello.") in result.stdout


def test_the_greeting_line_is_unchanged(ready, write_script):
    result = ask_command(write_script, [h.say_text("Hello.")], "/quit")
    assert result.stdout.splitlines()[0] == "Ask about your plan. Type /quit to stop."


def test_a_side_conversation_is_recorded_in_the_database_of_the_command(ready, write_script):
    ask_command(write_script, [h.say_text("Hello."), side("It is a thing.")], "/aside What is it?", "/back", "Pass this on", "/quit")
    kinds = [r[0] for r in database().execute("SELECT kind FROM events WHERE kind LIKE 'aside.%' ORDER BY id")]
    assert kinds == ["aside.opened", "aside.message", "aside.reply", "aside.closed"]


# ---- the commands that never offer it --------------------------------------------------------------------------------------------------

def test_in_a_plain_build_the_command_is_an_ordinary_answer(save_confirmed_brief, write_script):
    save_confirmed_brief(h.only_step("s1"))
    write_script([h.propose_spec(), h.propose_spec()])
    result = run_cli(["build"], typed("/aside what is this?", "/quit"))
    assert ASIDE_OPEN not in result.stdout and "aside>" not in result.stdout and "aside |" not in result.stdout
    [row] = database().execute("SELECT payload FROM events WHERE kind = 'calc.plan_decision' ORDER BY id").fetchall()[:1]
    assert '"decision": "feedback"' in row[0] and "/aside what is this?" in row[0]
    assert database().execute("SELECT COUNT(*) FROM events WHERE kind LIKE 'aside.%'").fetchone()[0] == 0


def test_in_a_plain_build_no_decision_is_written(save_confirmed_brief, write_script):
    save_confirmed_brief(h.only_step("s1"))
    write_script([h.propose_spec()])
    run_cli(["build"], typed("/quit"))
    assert database().execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


# ---- the decisions command after a conversation --------------------------------------------------------------------------------------------------

def test_the_decisions_of_a_conversation_are_listed_by_the_command(ready, write_script):
    script = [s4.run(), h.say_text(OK)]
    ask_command(write_script, script, "yes", "/quit")
    result = run_cli(["decisions"])
    lines = result.stdout.splitlines()
    assert result.returncode == 0 and lines[0].split("  ")[2:4] == ["assumptions", "step: -"]
    assert lines[1:-1] == ["  " + line for line in GATE.split("\n")] and lines[-1] == "  in their words: yes"
