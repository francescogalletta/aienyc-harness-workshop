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


QUESTION = "What does a sinking fund do for me?"          # no figures in it, so nothing else looks at it first


def ask_command(write_script, script, *lines, question=QUESTION):
    write_script(script)
    return run_cli(["ask", *question.split()], typed(*lines))


def prompted(text, prompt="> "):
    return f"\n{text}\n\n{prompt}"


def test_a_marked_question_is_read_after_the_aside_prompt(ready, write_script):
    result = ask_command(write_script, [h.say_text("Hello."), side("It is a thing."), h.say_text("Hello again.")],
                         "/aside What is it?", "/back", "no", "/quit")
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert prompted(marked("It is a thing."), "aside> ") in out
    assert prompted(marked(ASIDE_CARRY), "aside> ") in out
    assert out.count(prompted("Hello.")) == 2


def test_in_a_plain_build_the_command_is_an_ordinary_answer(save_confirmed_brief, write_script):
    save_confirmed_brief(h.only_step("s1"))
    write_script([h.propose_spec(), h.propose_spec()])
    result = run_cli(["build"], typed("/aside what is this?", "/quit"))
    assert ASIDE_OPEN not in result.stdout and "aside>" not in result.stdout and "aside |" not in result.stdout
    [row] = database().execute("SELECT payload FROM events WHERE kind = 'calc.plan_decision' ORDER BY id").fetchall()[:1]
    assert '"decision": "feedback"' in row[0] and "/aside what is this?" in row[0]
    assert database().execute("SELECT COUNT(*) FROM events WHERE kind LIKE 'aside.%'").fetchone()[0] == 0
