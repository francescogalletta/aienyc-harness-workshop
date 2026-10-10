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

@pytest.mark.parametrize("changes", [
    {}, {"verify": False, "data": s5.s4.DROP, "expect": {"runs": [{"module": "monthly_surplus"}]}},
    {"verify": s5.s4.DROP, "data": s5.s4.DROP, "expect": {"shown": ["2,000"]}},
    {"data": [{"file": "bank.csv", "sign": "out_positive"}]},
    {"data": [{"file": "bank.csv", "sign": "out_negative", "account": "main"}]},
    {"data": [{"file": "bank.csv", "sign": "out_negative"}, {"file": "card.csv", "sign": "out_positive", "account": "card_2"}]},
    {"data": []}, {"data": s5.s4.DROP},
    {"data": [{"file": "Bank Statement 2026.CSV", "sign": "out_negative"}]},
    {"data": [{"file": "a.b.c", "sign": "out_negative", "account": "a1_b"}]},
])
def test_a_scenario_that_verifies_and_loads_data_is_fine(replay, changes):
    assert validate(replay, ask(**changes)) == []


@pytest.mark.parametrize("findings", [
    [], [{"kind": "earlier"}], [{"kind": "data"}], [{"kind": "brief"}], [{"kind": "data", "status": "open"}],
    [{"kind": "data", "status": "decided"}], [{"kind": "data", "choice": "1"}], [{"kind": "data", "choice": "2"}],
    [{"kind": "data", "choice": "something else"}], [{"kind": "data", "count": 1}], [{"kind": "data", "count": 30}],
    [{"kind": "earlier", "status": "decided", "choice": "1", "count": 2}],
    [{"kind": "data"}, {"kind": "brief", "status": "open"}]])
def test_findings_that_are_fine(replay, findings):
    assert validate(replay, expecting(findings=findings)) == []


@pytest.mark.parametrize("value", [0, 1, 2, 100])
def test_max_findings_that_is_fine(replay, value):
    assert validate(replay, expecting(max_findings=value)) == []


def test_the_new_expectations_go_with_the_old_ones(replay):
    assert validate(replay, expecting(runs=[{"module": "monthly_surplus"}], shown=["2,000"], max_withheld=0, max_corrections=0,
                                      decisions=[{"kind": "judgment"}], asides={"opened": 0}, findings=[FINDING],
                                      max_findings=2)) == []


def test_a_verify_false_scenario_without_the_new_keys_is_valid_as_before(replay):
    assert validate(replay, s3.ask_scenario("upfront")) == []


# ---- validation: verify ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["true", "yes", 1, 0, [], {}, "false"])
def test_verify_must_be_true_or_false(replay, value):
    assert validate(replay, ask(verify=value, data=s5.s4.DROP, expect={"shown": ["2,000"]})) == ["verify must be true or false"]


def test_verify_and_data_are_only_for_ask_scenarios_one_per_key_verify_first(replay):
    build = {**s3.build_scenario("upfront"), "verify": True, "data": [dict(FILE)]}
    assert validate(replay, build) == ["verify is only for ask scenarios", "data is only for ask scenarios"]


def test_verify_alone_on_a_build_scenario(replay):
    build = {**s3.build_scenario("upfront"), "verify": False}
    assert validate(replay, build) == ["verify is only for ask scenarios"]


def test_a_key_other_than_the_nine_is_unknown(replay):
    assert validate(replay, ask(colour="blue", speed=3)) == ["unknown key: colour", "unknown key: speed"]


# ---- validation: data -------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["bank.csv", {"file": "bank.csv", "sign": "out_negative"}, 5, None])
def test_data_must_be_a_list(replay, value):
    assert validate(replay, ask(data=value)) == ["data must be a list"]


@pytest.mark.parametrize("bad", [
    "bank.csv", 5, None, [], {}, {"sign": "out_negative"}, {"file": "bank.csv"}, {"file": "", "sign": "out_negative"},
    {"file": 5, "sign": "out_negative"}, {"file": None, "sign": "out_negative"}, {"file": "a/b.csv", "sign": "out_negative"},
    {"file": "a\\b.csv", "sign": "out_negative"}, {"file": "/bank.csv", "sign": "out_negative"},
    {"file": ".bank.csv", "sign": "out_negative"}, {"file": "bank.csv", "sign": "negative"},
    {"file": "bank.csv", "sign": "OUT_NEGATIVE"}, {"file": "bank.csv", "sign": None}, {"file": "bank.csv", "sign": 1},
    {"file": "bank.csv", "sign": "out_negative", "account": "all"},
    {"file": "bank.csv", "sign": "out_negative", "account": "Main"},
    {"file": "bank.csv", "sign": "out_negative", "account": "1main"},
    {"file": "bank.csv", "sign": "out_negative", "account": "main account"},
    {"file": "bank.csv", "sign": "out_negative", "account": ""},
    {"file": "bank.csv", "sign": "out_negative", "account": 5},
    {"file": "bank.csv", "sign": "out_negative", "account": None},
    {"file": "bank.csv", "sign": "out_negative", "colour": "blue"}])
def test_a_bad_entry_of_data(replay, bad):
    assert validate(replay, ask(data=[bad])) == [ENTRY_DATA.format(k=1)]


def test_each_bad_entry_is_numbered_from_one(replay):
    data = [dict(FILE), "x", dict(FILE), {"file": "a/b", "sign": "out_negative"}]
    assert validate(replay, ask(data=data)) == [ENTRY_DATA.format(k=2), ENTRY_DATA.format(k=4)]


# ---- validation: expect.findings and max_findings ------------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["data", {"kind": "data"}, 5, None])
def test_findings_must_be_a_list(replay, value):
    assert validate(replay, expecting(findings=value)) == ["expect.findings must be a list"]


@pytest.mark.parametrize("bad", [
    "data", 5, None, [], {}, {"status": "open"}, {"kind": "decision"}, {"kind": "Data"}, {"kind": "judgment"}, {"kind": 1},
    {"kind": "data", "status": "closed"}, {"kind": "data", "status": "decided "}, {"kind": "data", "status": 1},
    {"kind": "data", "choice": "3"}, {"kind": "data", "choice": "yes"}, {"kind": "data", "choice": 1},
    {"kind": "data", "choice": "something"}, {"kind": "data", "count": 0}, {"kind": "data", "count": -1},
    {"kind": "data", "count": True}, {"kind": "data", "count": "1"}, {"kind": "data", "count": 1.5},
    {"kind": "data", "step": "s1"}, {"kind": "data", "colour": "blue"}])
def test_a_bad_entry_of_findings(replay, bad):
    assert validate(replay, expecting(findings=[bad])) == [ENTRY_FINDINGS.format(k=1)]


def test_each_bad_findings_entry_is_numbered_from_one(replay):
    assert validate(replay, expecting(findings=[{"kind": "data"}, "x", {"kind": "brief"}, {"kind": "no"}])) == [
        ENTRY_FINDINGS.format(k=2), ENTRY_FINDINGS.format(k=4)]


@pytest.mark.parametrize("value", [-1, True, False, "1", 1.5, None, [1], {}])
def test_max_findings_must_be_a_whole_number(replay, value):
    assert validate(replay, expecting(max_findings=value)) == [BAD_MAX]


def test_the_new_expectations_are_only_for_ask_scenarios(replay):
    build = s3.build_scenario("upfront")
    build["expect"] = {"findings": [FINDING], "max_findings": 1}
    problems = validate(replay, build)
    assert "expect.findings is only for ask scenarios" in problems and "expect.max_findings is only for ask scenarios" in problems
    assert problems.index("expect.findings is only for ask scenarios") < problems.index(
        "expect.max_findings is only for ask scenarios")


# ---- validation: they need verify -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("verify", [s5.s4.DROP, False])
def test_the_new_keys_need_verify_one_per_key_in_that_order(replay, verify):
    scenario = ask(verify=verify, expect={"findings": [FINDING], "max_findings": 1})
    assert validate(replay, scenario) == [NEEDS.format(key="data"), NEEDS.format(key="expect.findings"),
                                          NEEDS.format(key="expect.max_findings")]


@pytest.mark.parametrize("verify", [s5.s4.DROP, False])
def test_each_key_alone_needs_verify(replay, verify):
    assert validate(replay, ask(verify=verify, expect={"shown": ["2,000"]})) == [NEEDS.format(key="data")]
    assert validate(replay, ask(verify=verify, data=s5.s4.DROP, expect={"findings": [FINDING]})) == [
        NEEDS.format(key="expect.findings")]
    assert validate(replay, ask(verify=verify, data=s5.s4.DROP, expect={"max_findings": 0})) == [
        NEEDS.format(key="expect.max_findings")]


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


@pytest.mark.parametrize("entry_, what", [
    ({"kind": "earlier"}, "at least 1 earlier finding"), ({"kind": "data"}, "at least 1 data finding"),
    ({"kind": "brief", "count": 1}, "at least 1 brief finding"), ({"kind": "brief", "count": 2}, "at least 2 brief findings"),
    ({"kind": "brief", "count": 10}, "at least 10 brief findings"),
    ({"kind": "data", "status": "open"}, "at least 1 data finding with status open"),
    ({"kind": "data", "status": "decided"}, "at least 1 data finding with status decided"),
    ({"kind": "data", "choice": "2"}, "at least 1 data finding choosing 2"),
    ({"kind": "data", "choice": "something else"}, "at least 1 data finding choosing something else"),
    ({"kind": "earlier", "status": "decided", "choice": "1", "count": 3},
     "at least 3 earlier findings with status decided choosing 1")])
def test_what_each_findings_check_says(replay, conn, entry_, what):
    [found] = check(replay, conn, findings=[entry_])
    assert found["what"] == what and list(found) == ["what", "passed", "seen"]


def test_no_finding_fails_with_the_counts_of_the_kind(replay, conn):
    [found] = check(replay, conn, findings=[{"kind": "brief"}])
    assert found == {"what": "at least 1 brief finding", "passed": False, "seen": "0 matching of 0 brief findings"}


def test_a_finding_matches_the_kind_the_status_and_the_choice(replay, findings, conn):
    first, second, third = (open_one(findings, conn), open_one(findings, conn), open_one(findings, conn))
    open_one(findings, conn, kind="earlier")
    decide_row(conn, first["id"], "1")
    decide_row(conn, second["id"], "2")
    found = check(replay, conn, findings=[
        {"kind": "brief"}, {"kind": "brief", "status": "decided"}, {"kind": "brief", "status": "open"},
        {"kind": "brief", "choice": "2"}, {"kind": "brief", "status": "decided", "choice": "1"},
        {"kind": "brief", "status": "open", "choice": "1"}, {"kind": "earlier", "status": "open"}, {"kind": "data"}])
    assert [(c["passed"], c["seen"]) for c in found] == [
        (True, "3 matching of 3 brief findings"), (True, "2 matching of 3 brief findings"),
        (True, "1 matching of 3 brief findings"), (True, "1 matching of 3 brief findings"),
        (True, "1 matching of 3 brief findings"), (False, "0 matching of 3 brief findings"),
        (True, "1 matching of 1 earlier findings"), (False, "0 matching of 0 data findings")]


def test_the_count_is_at_least(replay, findings, conn):
    for _ in range(3):
        open_one(findings, conn)
    found = check(replay, conn, findings=[{"kind": "brief", "count": 2}, {"kind": "brief", "count": 3},
                                          {"kind": "brief", "count": 4}])
    assert [c["passed"] for c in found] == [True, True, False]
    assert found[2]["seen"] == "3 matching of 3 brief findings"


def test_only_the_findings_of_the_session_count(replay, findings, conn):
    open_one(findings, conn, session=OTHER)
    open_one(findings, conn, session=OTHER)
    [found] = check(replay, conn, findings=[{"kind": "brief"}])
    assert found["passed"] is False and found["seen"] == "0 matching of 0 brief findings"
    assert check(replay, conn, session=OTHER, findings=[{"kind": "brief", "count": 2}])[0]["passed"] is True


@pytest.mark.parametrize("count, passed", [(0, False), (1, False), (2, True), (3, True)])
def test_max_findings_is_at_most(replay, findings, conn, count, passed):
    open_one(findings, conn)
    open_one(findings, conn, kind="earlier")
    [found] = check(replay, conn, max_findings=count)
    assert found == {"what": f"at most {count} findings", "passed": passed, "seen": "2 findings"}


def test_max_findings_counts_this_session_only_and_any_kind(replay, findings, conn):
    open_one(findings, conn, session=OTHER)
    assert check(replay, conn, max_findings=0) == [{"what": "at most 0 findings", "passed": True, "seen": "0 findings"}]


def test_checking_records_nothing(replay, findings, conn):
    open_one(findings, conn)
    before = len(h.events(conn))
    check(replay, conn, findings=[{"kind": "brief"}], max_findings=1)
    assert len(h.events(conn)) == before


def test_the_order_of_the_checks(replay, findings, conn):
    open_one(findings, conn)
    s3.record(conn, SESSION, "ask.reply", "agent", text="You have 2,000.")
    found = replay.check_scenario(conn, SESSION, {"expect": {
        "max_findings": 1, "findings": [{"kind": "data"}, {"kind": "brief"}], "asides": {"turns": 0},
        "decisions": [{"kind": "judgment"}], "max_corrections": 1, "max_withheld": 1, "not_shown": ["9,999"],
        "shown": ["2,000"], "runs": [{"module": "monthly_surplus"}]}})
    assert [c["what"] for c in found] == [
        "ran monthly_surplus", "shows 2,000", "does not show 9,999", "at most 1 replies withheld", "at most 1 corrections",
        "at least 1 judgment decision", "0 side conversation turns", "at least 1 data finding", "at least 1 brief finding",
        "at most 1 findings"]


def test_the_steps_of_a_build_come_after_the_findings(replay, findings, conn):
    open_one(findings, conn)
    found = replay.check_scenario(conn, SESSION, {"expect": {"steps": {"s1": "built"}, "max_findings": 1}},
                                  [{"step": "s1", "outcome": "built", "module": "monthly_surplus", "reason": ""}])
    assert [c["what"] for c in found] == ["at most 1 findings", "step s1 built"]


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


def test_the_data_is_loaded_before_the_conversation_with_sign_from_scenario(replay, example, scratch):
    result = run(replay, make_example(example), verifying(), keep=True)
    kinds = [e["kind"] for e in kept(result)]
    assert kinds.count("data.imported") == 1
    assert kinds.index("calc.module_adopted") < kinds.index("data.imported") < kinds.index("ask.started")
    [imported] = kept(result, "data.imported")
    payload = imported["payload"]
    assert (payload["account"], payload["sign"], payload["sign_from"], payload["transactions"]) == (
        "bank", "out_negative", "scenario", 3 * 3)
    assert list(payload)[:3] == ["id", "ts", "session_id"] and payload["file"].endswith("bank.csv")


def test_every_event_of_the_scenario_carries_one_session(replay, example, scratch):
    result = run(replay, make_example(example), verifying(), keep=True)
    sessions = {e["session_id"] for e in kept(result)}
    assert len(sessions) == 1


def test_an_account_given_names_the_account(replay, example, scratch):
    result = run(replay, make_example(example), verifying(data=[{**FILE, "account": "main"}]), keep=True)
    assert kept(result, "data.imported")[0]["payload"]["account"] == "main"


def test_the_files_are_loaded_in_order(replay, example, scratch):
    files = {"bank.csv": bank_file(), "card.csv": bank_file(spending="10")}
    scenario = verifying(data=[{"file": "card.csv", "sign": "out_positive"}, dict(FILE)])
    result = run(replay, make_example(example, files), scenario, keep=True)
    accounts = [e["payload"]["account"] for e in kept(result, "data.imported")]
    assert accounts == ["card", "bank"]


def test_the_data_is_read_where_it_is_and_not_copied(replay, example, scratch):
    result = run(replay, make_example(example), verifying(), keep=True)
    assert sorted(p.name for p in Path(result["folder"]).iterdir()) == ["brief", "harness.db", "modules"]


def test_the_scenario_event_keeps_its_payload(replay, example, scratch):
    scenario = verifying()
    result = run(replay, make_example(example), scenario, keep=True)
    [first] = kept(result, "replay.scenario")
    assert list(first["payload"]) == ["example", "scenario", "kind", "lines", "expect", "without"]
    assert first["payload"]["expect"] == scenario["expect"] and first["payload"]["lines"] == scenario["lines"]


def test_a_scenario_without_verify_does_not_call_the_verifier(replay, example, scratch):
    scenario = {**s3.ask_scenario("upfront"), "lines": [MESSAGE], "expect": {"max_withheld": 0}}
    result = run(replay, example(scenarios={}), scenario, script=[h.say_text("Noted.")], keep=True)
    assert result["error"] is None and result["passed"] is True
    assert kept(result, "verify.report") == [] and kept(result, "data.imported") == []


def test_verify_false_is_the_same(replay, example, scratch):
    scenario = {**s3.ask_scenario("upfront"), "verify": False, "lines": [MESSAGE], "expect": {"max_withheld": 0}}
    result = run(replay, example(scenarios={}), scenario, script=[h.say_text("Noted.")])
    assert result["error"] is None and result["passed"] is True


def test_when_the_lines_run_out_a_finding_is_something_else(replay, example, scratch):
    scenario = ask(lines=[MESSAGE], expect={"findings": [{"kind": "data", "status": "decided", "choice": "something else"}]})
    result = run(replay, make_example(example), scenario)
    assert result["error"] is None and result["passed"] is True


@pytest.mark.parametrize("line, choice", [("1", "1"), ("2", "2"), ("neither", "something else")])
def test_the_line_after_the_message_answers_the_finding(replay, example, scratch, line, choice):
    scenario = ask(lines=[MESSAGE, line], expect={"findings": [{"kind": "data", "status": "decided", "choice": choice}]})
    assert run(replay, make_example(example), scenario)["passed"] is True


def test_a_finding_expectation_that_fails_fails_the_scenario_with_what_was_seen(replay, example, scratch):
    scenario = ask(lines=[MESSAGE, "2"], expect={"findings": [{"kind": "brief"}], "max_findings": 0})
    result = run(replay, make_example(example), scenario)
    assert result["error"] is None and result["passed"] is False
    assert {c["what"]: (c["passed"], c["seen"]) for c in result["checks"]} == {
        "at least 1 brief finding": (False, "0 matching of 0 brief findings"), "at most 0 findings": (False, "1 findings")}


def test_a_message_that_does_not_differ_leaves_no_finding(replay, example, scratch):
    scenario = ask(lines=[MESSAGE], expect={"max_findings": 0})
    result = run(replay, make_example(example), scenario, script=[summary_call(), report(), h.say_text("Noted.")])
    assert result["passed"] is True


# ---- a file that is not loaded -----------------------------------------------------------------------------------------------------------------------------------

def test_a_file_that_cannot_be_read_stops_the_scenario_before_the_conversation(replay, example, scratch):
    files = {"empty.csv": b""}
    result = run(replay, make_example(example, files), verifying(data=[{"file": "empty.csv", "sign": "out_negative"}]),
                 keep=True)
    assert result["error"] == "empty.csv was not loaded: the file is empty"
    assert result["passed"] is False and result["checks"] == []
    kinds = [e["kind"] for e in kept(result)]
    assert "ask.started" not in kinds and "ask.message" not in kinds and kinds.count("data.refused") == 1
    assert kinds[-1] == "replay.checked"


def test_a_file_that_is_not_there_stops_the_scenario(replay, example, scratch):
    result = run(replay, make_example(example), verifying(data=[{"file": "missing.csv", "sign": "out_negative"}]))
    assert result["passed"] is False and result["checks"] == []
    assert result["error"].startswith("missing.csv was not loaded: ")


def test_the_first_file_refused_stops_the_rest(replay, example, scratch):
    files = {"bank.csv": bank_file(), "empty.csv": b"", "card.csv": bank_file(spending="10")}
    data = [dict(FILE), {"file": "empty.csv", "sign": "out_negative"}, {"file": "card.csv", "sign": "out_positive"}]
    result = run(replay, make_example(example, files), verifying(data=data), keep=True)
    assert result["error"] == "empty.csv was not loaded: the file is empty"
    assert [e["payload"]["account"] for e in kept(result, "data.imported")] == ["bank"]


def test_a_file_loaded_twice_is_refused_the_second_time(replay, example, scratch):
    result = run(replay, make_example(example), verifying(data=[dict(FILE), {**FILE, "account": "again"}]))
    assert result["error"] == "bank.csv was not loaded: this file is already loaded, into account 'bank'"
