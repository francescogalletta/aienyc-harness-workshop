"""SPEC 7.4: `GET /api/work/summary`, what the page needs to start, over the recorded story."""
import json
import shutil

import pytest

import step3_helpers as s3
from step3_evidence_helpers import *            # noqa: F401,F403  (the key lists and row builders)
from step3_helpers import BUILD, ADOPT, CHAT1, CHAT2, REPLAY, h


@pytest.fixture
def summary(api):
    def get():
        status, body = api.get("/api/work/summary")
        assert status == 200
        return body
    return get


def first_ids(world):
    """session id -> id of its first event"""
    return {r["session_id"]: r["first"] for r in world.sql("SELECT session_id, MIN(id) AS first FROM events GROUP BY session_id")}


# ---- the whole -----------------------------------------------------------------------------------------------------

def test_the_keys_and_their_order(summary):
    assert list(summary()) == SUMMARY_KEYS


def test_nothing_is_run_or_recorded_by_asking(api, summary, world):
    before = world.counts()
    summary()
    assert world.counts() == before


def test_the_summary_is_what_the_function_gives(api, world, evidence):
    from harness import db
    conn = db.connect()
    try:
        assert json.loads(json.dumps(evidence.summary(conn, interview=False))) == api.get("/api/work/summary")[1]
    finally:
        conn.close()


# ---- interview, database, brief ------------------------------------------------------------------------------------

def test_without_an_interview_session_the_flag_is_false(summary):
    assert summary()["interview"] is False


def test_the_database_is_the_configured_path_as_text(summary, world):
    from harness.config import load_config
    body = summary()
    assert body["database"] == str(load_config().db_path) == str(world.db_path)


def test_the_brief_is_its_goal_and_status(summary):
    assert summary()["brief"] == {"goal": h.GOAL, "status": "confirmed"}
    assert list(summary()["brief"]) == ["goal", "status"]


def test_a_draft_brief_is_shown_too(summary, world):
    s3.save_the_brief(world.brief_dir, status="draft")
    assert summary()["brief"] == {"goal": h.GOAL, "status": "draft"}


def test_the_status_is_null_without_a_meta_status(summary, world):
    path = world.brief_dir / "domain_brief.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["meta"]["status"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert summary()["brief"] == {"goal": h.GOAL, "status": None}


def test_a_brief_without_meta_at_all_still_has_its_goal(summary, world):
    path = world.brief_dir / "domain_brief.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["meta"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert summary()["brief"] == {"goal": h.GOAL, "status": None}


@pytest.mark.parametrize("how", ["missing", "unreadable", "empty"])
def test_no_brief_file_or_one_that_cannot_be_read_is_no_brief(summary, world, how):
    path = world.brief_dir / "domain_brief.json"
    if how == "missing":
        path.unlink()
    else:
        path.write_text("{ not json" if how == "unreadable" else "", encoding="utf-8")
    body = summary()
    assert body["brief"] is None
    assert [step["id"] for step in body["process"]] == ["added_1"]           # the process then holds the added steps only


def test_the_brief_folder_is_read_at_the_time_of_the_call(summary, world):
    first = summary()["brief"]
    shutil.rmtree(world.brief_dir)
    assert first is not None and summary()["brief"] is None


# ---- the process ---------------------------------------------------------------------------------------------------------

def test_the_process_is_the_brief_then_the_added_steps(summary):
    process = summary()["process"]
    assert [step["id"] for step in process] == ["s1", "s2", "s3", "added_1"]
    assert all(list(step) == PROCESS_KEYS for step in process)


def test_each_step_has_its_label_name_kind_and_module(summary):
    process = {step["id"]: step for step in summary()["process"]}
    brief = {step["id"]: step for step in h.make_brief()["process"]}
    for step_id in ("s1", "s2", "s3"):
        assert process[step_id]["name"] == brief[step_id]["name"] and process[step_id]["kind"] == brief[step_id]["kind"]
        assert process[step_id]["label"] == step_id and process[step_id]["in_brief"] is True
    added = process["added_1"]
    assert added["label"] == "added_1 (not in the brief)" and added["in_brief"] is False
    assert added["kind"] == "calculation" and added["name"] == "the cost over a whole year"


def test_the_module_of_a_step_is_the_one_mapped_to_it_or_null(summary):
    assert {step["id"]: step["module"] for step in summary()["process"]} == {
        "s1": SURPLUS, "s2": None, "s3": MONTHS, "added_1": YEARLY}


def test_a_step_with_no_module_has_null(summary, world):
    from harness import db
    conn = db.connect()
    try:
        conn.execute("DELETE FROM step_modules WHERE step_id = 's3'")
        conn.commit()
    finally:
        conn.close()
    assert {step["id"]: step["module"] for step in summary()["process"]}["s3"] is None


# ---- the modules -----------------------------------------------------------------------------------------------------------

def test_every_registered_module_by_name(summary):
    modules = summary()["modules"]
    assert [m["name"] for m in modules] == [SURPLUS, MONTHS, YEARLY]
    assert all(list(m) == MODULE_ROW_KEYS for m in modules)


def test_a_module_row_holds_its_steps_fingerprint_and_registration_time(summary, world):
    for module in summary()["modules"]:
        row = module_row(world, module["name"])
        assert module["fingerprint"] == row["fingerprint"] and module["registered_at"] == row["registered_at"]
        assert module["steps"] == steps_of(world, module["name"])


def test_the_steps_of_an_added_module_are_marked_as_not_in_the_brief(summary):
    yearly = {m["name"]: m for m in summary()["modules"]}[YEARLY]
    assert yearly["steps"] == [{"id": "added_1", "label": "added_1 (not in the brief)", "in_brief": False}]
    assert list(yearly["steps"][0]) == ["id", "label", "in_brief"]


def test_the_last_test_is_the_latest_test_run_of_the_module_without_its_report(summary, world):
    last = {m["name"]: m["last_test"] for m in summary()["modules"]}
    assert last == {SURPLUS: shown_test_run(last_test_row(world, SURPLUS)), MONTHS: shown_test_run(last_test_row(world, MONTHS)),
                    YEARLY: shown_test_run(last_test_row(world, YEARLY))}
    assert last[SURPLUS]["id"] == 7 and last[SURPLUS]["reason"] == "gate" and last[MONTHS]["reason"] == "adopt"
    assert all(list(test) == TEST_RUN_KEYS and test["passed"] is True for test in last.values())


def test_the_latest_test_run_is_the_one_with_the_highest_id(summary, world):
    from harness import db
    conn = db.connect()
    try:
        conn.execute("INSERT INTO test_runs (id, ts, module, fingerprint, reason, passed, report) VALUES "
                     "(?, '2000-01-01T00:00:00+00:00', ?, ?, 'status', 0, ?)",
                     (500, MONTHS, "f" * 64, json.dumps({"tests": [], "golden": [], "passed": False, "error": "x"})))
        conn.commit()
    finally:
        conn.close()
    last = {m["name"]: m["last_test"] for m in summary()["modules"]}[MONTHS]
    assert last == {"id": 500, "ts": "2000-01-01T00:00:00+00:00", "reason": "status", "passed": False,
                    "fingerprint": "f" * 64}


@pytest.mark.parametrize("edit, status", [
    ("none", "unchanged"), ("module.py", "changed"), ("tests.py", "changed"), ("golden.json", "changed"),
    ("spec.json", "changed"), ("delete_file", "missing"), ("delete_folder", "missing")])
def test_the_file_status_of_a_module(summary, world, edit, status):
    if edit in FILES:
        world.edit(SURPLUS, edit, prefix="\n" if edit.endswith(".json") else "# edited\n")
    elif edit == "delete_file":
        (world.modules_dir / SURPLUS / "tests.py").unlink()
    elif edit == "delete_folder":
        shutil.rmtree(world.modules_dir / SURPLUS)
    by_name = {m["name"]: m for m in summary()["modules"]}
    assert by_name[SURPLUS]["file_status"] == status
    assert by_name[MONTHS]["file_status"] == "unchanged"


def test_the_summary_does_not_run_the_tests(summary, world):
    world.edit(SURPLUS)
    before = world.counts()["test_runs"]
    summary()
    assert world.counts()["test_runs"] == before


# ---- the conversations -------------------------------------------------------------------------------------------------------

def test_the_conversations_are_those_with_a_message_newest_first(summary):
    assert [c["session_id"] for c in summary()["conversations"]] == [REPLAY, CHAT2, CHAT1]


def test_a_conversation_row_has_these_keys(summary):
    assert all(list(c) == CONVERSATION_ROW_KEYS for c in summary()["conversations"])


def test_a_conversation_row_holds_the_times_and_the_first_message(summary, world):
    for row in summary()["conversations"]:
        events = world.sql("SELECT * FROM events WHERE session_id = ? ORDER BY id", (row["session_id"],))
        assert row["started"] == events[0]["ts"] and row["ended"] == events[-1]["ts"]
        first = next(e for e in events if e["kind"] == "ask.message")
        assert row["first_message"] == json.loads(first["payload"])["text"]


def test_the_counts_of_a_conversation(summary):
    by_session = {c["session_id"]: c for c in summary()["conversations"]}
    counts = lambda c: (c["messages"], c["replies"], c["withheld"], c["corrections"], c["runs"])    # noqa: E731
    assert counts(by_session[CHAT1]) == (2, 1, 1, 1, 2)
    assert counts(by_session[CHAT2]) == (1, 1, 0, 0, 1)
    assert counts(by_session[REPLAY]) == (1, 1, 0, 0, 1)


def test_the_first_messages(summary):
    assert {c["session_id"]: c["first_message"] for c in summary()["conversations"]} == {
        CHAT1: s3.Q1, CHAT2: s3.Q2, REPLAY: s3.Q3}


def test_a_replay_conversation_names_its_example_and_scenario(summary):
    by_session = {c["session_id"]: c for c in summary()["conversations"]}
    assert by_session[REPLAY]["replay"] == {"example": "savings", "scenario": "first_look"}
    assert list(by_session[REPLAY]["replay"]) == ["example", "scenario"]
    assert by_session[CHAT1]["replay"] is None and by_session[CHAT2]["replay"] is None


def test_every_kind_of_correction_is_counted(api, world, summary):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, "probe", ("ask.message", {"text": "Hello 1"}, "person"),
                    ("ask.correction", {"reason": "reply", "numbers": ["9,999"], "text": "x 9,999"}, "harness"),
                    ("ask.correction", {"reason": "other", "numbers": []}, "harness"),
                    ("ask.withheld", {"numbers": ["9,999"], "text": "y"}, "harness"))
    finally:
        conn.close()
    probe = next(c for c in summary()["conversations"] if c["session_id"] == "probe")
    assert (probe["messages"], probe["replies"], probe["withheld"], probe["corrections"], probe["runs"]) == (1, 0, 1, 2, 0)
    assert summary()["conversations"][0]["session_id"] == "probe"             # newest first


def test_a_session_with_no_message_is_not_a_conversation(summary):
    ids = [c["session_id"] for c in summary()["conversations"]]
    assert BUILD not in ids and ADOPT not in ids


def test_conversations_are_ordered_by_the_first_event_of_the_session(api, world, summary):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, "early", ("ask.message", {"text": "first"}, "person"))
        add_session(conn, "late", ("ask.message", {"text": "second"}, "person"))
        add_session(conn, "early", ("ask.message", {"text": "again"}, "person"))      # more events, but not a newer session
    finally:
        conn.close()
    assert [c["session_id"] for c in summary()["conversations"]][:2] == ["late", "early"]


# ---- the runs ------------------------------------------------------------------------------------------------------------------

def test_the_runs_are_every_calculation_newest_first(summary, world):
    runs = summary()["runs"]
    assert [r["id"] for r in runs] == [4, 3, 2, 1] and all(list(r) == RUN_ROW_KEYS for r in runs)
    for run in runs:
        row = world.sql("SELECT * FROM calc_runs WHERE id = ?", (run["id"],))[0]
        assert run == {"id": row["id"], "ts": row["ts"], "session_id": row["session_id"], "module": row["module"],
                       "output": json.loads(row["output"])}


def test_the_output_of_a_run_is_json(summary):
    assert {r["id"]: r["output"] for r in summary()["runs"]} == {1: "2000", 2: "2000", 3: "3000", 4: "500"}


# ---- the sessions and the kinds ---------------------------------------------------------------------------------------------

def test_every_session_newest_first_by_its_first_event(summary, world):
    sessions = summary()["sessions"]
    assert [s["session_id"] for s in sessions] == [REPLAY, CHAT2, CHAT1, ADOPT, BUILD]
    assert all(list(s) == SESSION_ROW_KEYS for s in sessions)


def test_a_session_row_holds_its_times_event_count_and_first_kind(summary, world):
    for session in summary()["sessions"]:
        events = world.sql("SELECT * FROM events WHERE session_id = ? ORDER BY id", (session["session_id"],))
        assert session["started"] == events[0]["ts"] and session["ended"] == events[-1]["ts"]
        assert session["events"] == len(events) and session["first_kind"] == events[0]["kind"]
    assert {s["session_id"]: (s["events"], s["first_kind"]) for s in summary()["sessions"]} == {
        BUILD: (10, "calc.note_saved"), ADOPT: (4, "calc.adopt_decision"), CHAT1: (11, "ask.started"),
        CHAT2: (19, "ask.started"), REPLAY: (6, "replay.scenario")}


def test_the_kinds_are_the_distinct_kinds_sorted(summary, world):
    kinds = summary()["kinds"]
    assert kinds == sorted({r["kind"] for r in world.sql("SELECT kind FROM events")}) and len(set(kinds)) == len(kinds)
    assert "ask.started" in kinds and "replay.scenario" in kinds and "calc.module_adopted" in kinds


# ---- an empty database ----------------------------------------------------------------------------------------------------------

@pytest.fixture
def empty(tmp_path, monkeypatch, served):
    """A server over a migrated database with nothing in it, and no brief."""
    from harness import db
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "empty" / "harness.db"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "empty" / "brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "empty" / "modules"))
    conn = db.connect()
    db.migrate(conn)
    conn.close()
    return served()


def test_an_empty_database_has_empty_lists(empty):
    body = empty("GET", "/api/work/summary").json()
    assert body["brief"] is None and body["process"] == [] and body["modules"] == []
    assert body["conversations"] == [] and body["runs"] == [] and body["sessions"] == [] and body["kinds"] == []
    assert list(body) == SUMMARY_KEYS and body["interview"] is False
