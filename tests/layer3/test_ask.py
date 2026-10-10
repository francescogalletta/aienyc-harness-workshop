"""SPEC 5.3: the `ask` command and the replay expectations; the layer on a seeded plan."""
import shutil
from pathlib import Path

from harness.__main__ import parser_for
from harness.answers.layer import EXPECTS, run_ask
from harness.config import load_config
from harness.layers import enabled
from layer3_helpers import assistant, reply, run, say, step_of
from state_shape import problems

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


class Lines:
    """Typed lines for the terminal driver; the end of the list is the end of input."""
    def __init__(self, *lines):
        self.lines = list(lines)

    def __call__(self, prompt=""):
        if not self.lines:
            raise EOFError
        return self.lines.pop(0)


def test_ask_is_a_command_that_takes_the_question_as_words():
    args = parser_for(enabled(load_config())).parse_args(["ask", "Can", "I", "cover", "it?"])
    assert args.command == "ask" and args.question == ["Can", "I", "cover", "it?"]


def test_ask_sends_the_question_and_then_reads_lines_until_the_end(open_session):
    session = open_session([reply("What is amount A?"), reply("Thank you.")])
    written = []
    code = run_ask(session, "What is the total?", read=Lines("100"), write=written.append)
    assert code == 0
    assert "you: What is the total?" in written and "assistant: What is amount A?" in written
    assert "assistant: Thank you." in written


def test_ask_without_an_agreed_plan_says_so_and_fails(open_session, monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "no_plan_here"))
    session = open_session([])
    written = []
    assert run_ask(session, "Hello", read=Lines(), write=written.append) == 1
    assert len(written) == 1 and not session.script.calls


def test_the_expectations_check_runs_numbers_shown_and_counts(open_session):
    session = open_session([run("total", {"a": 100, "b": 250}), reply("The total is 350."),
                            reply("That one is 999."), reply("Still 999.")])
    say(session, "A is 100 and B is 250")
    say(session, "And another?")
    context = session

    def check(key, value):
        assert EXPECTS[key].validate(value) is None
        return EXPECTS[key].check(value, context)["passed"]

    assert check("runs", [{"module": "total", "inputs": {"a": "100"}}])
    assert not check("runs", [{"module": "double"}])
    assert check("shown", ["350"]) and not check("shown", ["999"])
    assert check("not_shown", ["999"]) and not check("not_shown", ["350"])
    assert check("max_withheld", 1) and not check("max_withheld", 0)
    assert check("max_corrections", 1) and not check("max_corrections", 0)


def test_the_expectations_reject_what_they_cannot_check():
    assert EXPECTS["runs"].validate("total") and EXPECTS["runs"].validate([{"inputs": {}}])
    assert EXPECTS["shown"].validate(["2026-10-10"]) and EXPECTS["shown"].validate(["7"]) and EXPECTS["shown"].validate("350")
    assert EXPECTS["max_withheld"].validate(-1) and EXPECTS["max_corrections"].validate(True)


def test_on_the_seeded_plan_the_totals_come_from_the_module_and_lead_to_its_step(monkeypatch, tmp_path, open_session):
    for part in ("brief", "modules"):
        shutil.copytree(EXAMPLES / "wedding" / part, tmp_path / "wedding" / part)
        monkeypatch.setenv("HARNESS_BRIEF_DIR" if part == "brief" else "HARNESS_MODULES_DIR",
                           str(tmp_path / "wedding" / part))
    extras = [{"name": "Extras", "amount": "5000"}, {"name": "DJ", "amount": "2000"}, {"name": "Bar", "amount": "1500"}]
    low = {"guest_count": "150", "dinner_cost_per_guest": "230", "extra_costs": extras}
    high = {**low, "guest_count": "200"}
    session = open_session([
        {"tool_calls": [{"name": "run_module", "arguments": {"module": "wedding_total_cost", "inputs": inputs,
                                                              "assumptions": [], "expected": case}}
                        for inputs, case in ((low, "the low case"), (high, "the high case"))]},
        reply("For 150 guests the total cost (step 1) is 43,000 and for 200 guests it is 54,500.")])
    state = say(session, "Between 150 and 200 guests at 230 each for dinner; extras 5,000, DJ 2,000 and bar 1,500.")
    assert state["error"] is None, [m["content"] for m in session.script.calls[-1]["messages"] if m["role"] == "tool"]
    assert problems(state) == []
    message = assistant(state)[-1]
    by_text = {each["text"]: each for each in message["figures"]}
    assert by_text["43,000"]["step"] == "s1" and by_text["54,500"]["step"] == "s1"
    assert by_text["43,000"]["run"] != by_text["54,500"]["run"] and not session.conn.execute(
        "SELECT * FROM events WHERE kind = 'ask.correction'").fetchall()
    assert step_of(state, "s1")["last_run"]["in_last_answer"] and step_of(state, "s1")["line"]["kind"] == "result"
    assert state["inputs"]["in:guest_count"]["used"]
