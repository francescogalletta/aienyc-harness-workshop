"""SPEC 6.4, 6.5 and 9.8: scenarios that verify: the keys `verify` and `data`, the expectations `findings` and `max_findings`
(validation, checks), and a replay with the scripted model and the scripted person."""
from pathlib import Path

import pytest

import step5_helpers as s5
from step5_helpers import MESSAGE, ask_finding, entry, h, report, s3, summary_call

BRIEF = h.make_brief()
FILE = {"file": "bank.csv", "sign": "out_negative"}
FINDING = {"kind": "data"}
ENTRY_DATA = ("data: entry {k} must be an object with file (a file name in the example's data folder), sign (out_negative or "
              "out_positive) and, optionally, account")
ENTRY_FINDINGS = ("expect.findings: entry {k} must be an object with a kind (earlier, data or brief) and, optionally, status "
                  "(open or decided), choice (1, 2 or something else) and count (1 or more)")
BAD_MAX = "expect.max_findings must be a whole number, 0 or more"
NEEDS = '{key} needs "verify": true'
DIFFERENCE = "The loaded files show 3,000.00 going out a month on average over the last three full months."
SESSION = h.SESSION
OTHER = "another-session"


def validate(replay, value, stem="upfront"):
    return replay.validate_scenario(value, stem=stem, brief=BRIEF)


def ask(**changes):
    """A valid ask scenario that verifies (the data and the expectation are changed by the test)."""
    base = {**s3.ask_scenario("upfront"), "verify": True, "data": [dict(FILE)]}
    base["expect"] = {"findings": [dict(FINDING)]}
    base.update(changes)
    return {key: value for key, value in base.items() if value is not s5.s4.DROP}


def expecting(**expect):
    return ask(expect=expect)


# ---- validation: what is fine ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("changes", [{}])
def test_a_scenario_that_verifies_and_loads_data_is_fine(replay, changes):
    assert validate(replay, ask(**changes)) == []










# ---- validation: verify ------------------------------------------------------------------------------------------------------------









# ---- validation: data -------------------------------------------------------------------------------------------------------------------







# ---- validation: expect.findings and max_findings ------------------------------------------------------------------------------











# ---- validation: they need verify -------------------------------------------------------------------------------------------------------





# ---- the checks -----------------------------------------------------------------------------------------------------------------------------

def open_one(findings, conn, session=SESSION, kind="brief"):
    return findings.open_finding(conn, session_id=session, kind=kind, claim="x 1,400", claim_figure="1,400",
                                 reference="y 1,150", reference_figure="1,150", difference="d",
                                 **({"summary_id": None} if kind != "data" else {}))


def decide_row(conn, finding_id, choice, status="decided"):
    conn.execute("UPDATE findings SET status = ?, choice = ? WHERE id = ?", (status, choice, finding_id))
    conn.commit()


def check(replay, conn, session=SESSION, **expect):
    return replay.check_scenario(conn, session, {"expect": expect})






















# ---- a replay with the scripted model and the scripted person ----------------------------------------------------------------------------------------

@pytest.fixture
def scratch(replay_scratch):
    return replay_scratch


def bank_file(months=("2026-06", "2026-07", "2026-08"), spending="3000"):
    rows = []
    for month in months:
        rows += [(day, description, amount) for day, amount, description in s5.month_rows(month, outs=[spending])]
    return s5.csv_text(rows)


def make_example(example, files=None, **scenarios):
    """An example folder with a data/ folder holding `files` (name -> text or bytes)."""
    folder = example(scenarios=scenarios)
    for name, content in (files if files is not None else {"bank.csv": bank_file()}).items():
        s5.write(folder / "data", name, content)
    return folder


SCRIPT = [summary_call(), report(entry(difference=DIFFERENCE)), ask_finding(1), h.say_text("Noted.")]


def run(replay, folder, scenario, script=SCRIPT, **options):
    from harness.model import ScriptedModel
    assert validate(replay, scenario) == []
    return replay.run_scenario(scenario, example_dir=folder, model=ScriptedModel(script), **options)


def kept(result, kind=None):
    return s3.stored_events(Path(result["folder"]) / "harness.db", kind=kind)


def verifying(**changes):
    return ask(lines=[MESSAGE, "2"], expect={"findings": [{"kind": "data", "status": "decided", "choice": "2"}],
                                             "max_findings": 1}, **changes)


def test_a_scenario_that_verifies_runs_the_verifier_and_the_finding_takes_a_line(replay, example, scratch):
    result = run(replay, make_example(example), verifying())
    assert result["error"] is None and result["passed"] is True
    assert {c["what"]: c["seen"] for c in result["checks"]} == {
        "at least 1 data finding with status decided choosing 2": "1 matching of 1 data findings",
        "at most 1 findings": "1 findings"}






















def test_a_finding_expectation_that_fails_fails_the_scenario_with_what_was_seen(replay, example, scratch):
    scenario = ask(lines=[MESSAGE, "2"], expect={"findings": [{"kind": "brief"}], "max_findings": 0})
    result = run(replay, make_example(example), scenario)
    assert result["error"] is None and result["passed"] is False
    assert {c["what"]: (c["passed"], c["seen"]) for c in result["checks"]} == {
        "at least 1 brief finding": (False, "0 matching of 0 brief findings"), "at most 0 findings": (False, "1 findings")}




# ---- a file that is not loaded -----------------------------------------------------------------------------------------------------------------------------------







