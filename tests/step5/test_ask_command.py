"""SPEC 5.10 and 9.7: `python -m harness ask` always verifies; the data commands feed it."""
import json
import sqlite3

import step5_helpers as s5
from step5_helpers import DATA_BLOCK, MESSAGE, RENT_MESSAGE, VERIFY_PROGRESS, ask_finding, brief_entry, entry, h, report, summary_call

OK = "Noted."
EXAMPLE = s5.EXAMPLE_DATA


def typed(*lines):
    return "".join(f"{line}\n" for line in lines)


def database():
    from harness.config import load_config
    connection = sqlite3.connect(load_config().db_path)
    connection.row_factory = sqlite3.Row
    return connection


def rows(query):
    connection = database()
    try:
        return [dict(r) for r in connection.execute(query)]
    finally:
        connection.close()


def ready(conn, save_confirmed_brief):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")
    save_confirmed_brief()


def test_ask_checks_a_figure_before_the_agent_and_puts_the_finding(conn, save_confirmed_brief, write_script):
    ready(conn, save_confirmed_brief)
    write_script([report(brief_entry()), ask_finding(1), h.say_text(OK)])
    result = h.run_cli(["ask", *RENT_MESSAGE.split()], typed("1", "/quit"))
    assert result.returncode == 0, result.stderr
    assert VERIFY_PROGRESS in result.stdout and s5.BRIEF_BLOCK in result.stdout
    assert result.stdout.index(VERIFY_PROGRESS) < result.stdout.index(s5.BRIEF_BLOCK) < result.stdout.index(OK)
    [finding] = rows("SELECT * FROM findings")
    assert (finding["kind"], finding["status"], finding["choice"], finding["chosen"]) == ("brief", "decided", "1", "1400")
    [decision] = rows("SELECT * FROM decisions")
    assert decision["kind"] == "finding" and decision["question"] == s5.BRIEF_BLOCK and decision["words"] == "1"








