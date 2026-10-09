"""SPEC 7.4: `GET /api/work/module?name=X`, one registered module: files, examples, tests, runs and history."""
import json
import shutil

import pytest

import step3_helpers as s3
from step3_evidence_helpers import (EVENT_KEYS, FILES, MODULE_KEYS, MONTHS, NO_MODULE, SURPLUS, TEST_RUN_KEYS, YEARLY,
                                    add_session, events_where, last_test_row, module_row, row_of_test_run,
                                    shown_test_run, shown_test_run_with_report, steps_of)
from step3_helpers import ADOPT, BUILD, CHAT2, h


def get(api, name):
    return api.get(f"/api/work/module?name={name}")


def body_of(api, name):
    status, body = get(api, name)
    assert status == 200, body
    return body


def ids(events):
    return [e["id"] for e in events]


# ---- the shape and the registered facts ------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", [SURPLUS, MONTHS, YEARLY])
def test_the_keys_of_a_module(api, name):
    assert list(body_of(api, name)) == MODULE_KEYS


@pytest.mark.parametrize("name", [SURPLUS, MONTHS, YEARLY])
def test_the_registered_facts(api, world, name):
    body, row = body_of(api, name), module_row(world, name)
    assert (body["name"], body["fingerprint"], body["registered_at"], body["session_id"]) == (
        name, row["fingerprint"], row["registered_at"], row["session_id"])
    assert body["spec"] == json.loads(row["spec"])
    assert body["steps"] == steps_of(world, name)


def test_the_sessions_that_registered_the_modules(api):
    assert [body_of(api, name)["session_id"] for name in (SURPLUS, MONTHS, YEARLY)] == [BUILD, ADOPT, CHAT2]


def test_the_plan_is_the_builders_plan_words_of_the_spec(api):
    for name in (SURPLUS, MONTHS, YEARLY):
        body = body_of(api, name)
        assert body["plan"] == s3.plan_text(body["spec"])
    assert body_of(api, SURPLUS)["plan"].startswith("To work this out: ")


def test_the_steps_of_a_module(api):
    assert body_of(api, SURPLUS)["steps"] == [s3.step_ref("s1", True)]
    assert body_of(api, YEARLY)["steps"] == [{"id": "added_1", "label": "added_1 (not in the brief)", "in_brief": False}]


def test_the_spec_is_the_registered_one_not_the_file_on_disk(api, world):
    path = world.modules_dir / SURPLUS / "spec.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    registered = body_of(api, SURPLUS)["spec"]
    spec["description"] = "Something else entirely."
    path.write_text(json.dumps(spec), encoding="utf-8")
    body = body_of(api, SURPLUS)
    assert body["spec"] == registered and registered["description"] != "Something else entirely."
    assert json.loads(body["files"]["spec.json"])["description"] == "Something else entirely."
    assert body["plan"] == s3.plan_text(registered)


# ---- the files -------------------------------------------------------------------------------------------------------------------

def test_the_files_are_their_text_on_disk(api, world):
    body = body_of(api, SURPLUS)
    assert list(body["files"]) == list(FILES)
    assert body["files"] == {name: world.module_text(SURPLUS, name) for name in FILES}
    assert body["file_status"] == "unchanged"


def test_a_changed_file_shows_as_it_is_now(api, world):
    world.edit(SURPLUS, "module.py", prefix="# edited by hand\n")
    body = body_of(api, SURPLUS)
    assert body["files"]["module.py"].startswith("# edited by hand\n") and body["file_status"] == "changed"
    assert body["fingerprint"] == module_row(world, SURPLUS)["fingerprint"]


@pytest.mark.parametrize("name", FILES)
def test_a_missing_file_is_null_and_the_status_is_missing(api, world, name):
    (world.modules_dir / SURPLUS / name).unlink()
    body = body_of(api, SURPLUS)
    assert body["files"][name] is None and body["file_status"] == "missing"
    assert all(body["files"][other] is not None for other in FILES if other != name)


def test_a_module_whose_folder_is_gone_has_four_nulls(api, world):
    shutil.rmtree(world.modules_dir / SURPLUS)
    body = body_of(api, SURPLUS)
    assert body["files"] == {name: None for name in FILES} and body["file_status"] == "missing"
    assert body["examples"] is None and body["spec"]["name"] == SURPLUS


def test_the_text_is_utf8(api, world):
    path = world.modules_dir / SURPLUS / "module.py"
    path.write_text("# café, déjà vu, 日本語\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
    assert body_of(api, SURPLUS)["files"]["module.py"].startswith("# café, déjà vu, 日本語\n")


# ---- the examples ------------------------------------------------------------------------------------------------------------------

def test_the_examples_are_golden_json_as_written(api, world):
    body = body_of(api, SURPLUS)
    assert body["examples"] == json.loads(world.module_text(SURPLUS, "golden.json"))
    assert len(body["examples"]) == 3 and all(list(e) == ["inputs", "expected", "working", "decision"] for e in body["examples"])
    assert {e["decision"] for e in body["examples"]} == {"accepted"}


def test_a_corrected_decision_shows_as_written(api, world):
    path = world.modules_dir / SURPLUS / "golden.json"
    examples = json.loads(path.read_text(encoding="utf-8"))
    examples[0]["decision"] = "corrected"
    path.write_text(json.dumps(examples), encoding="utf-8")
    assert [e["decision"] for e in body_of(api, SURPLUS)["examples"]] == ["corrected", "accepted", "accepted"]


@pytest.mark.parametrize("text", ["{}", "{ not json", "\"text\"", "null", "42"])
def test_golden_json_that_is_not_a_list_gives_null(api, world, text):
    (world.modules_dir / SURPLUS / "golden.json").write_text(text, encoding="utf-8")
    body = body_of(api, SURPLUS)
    assert body["examples"] is None and body["files"]["golden.json"] == text


def test_an_empty_list_of_examples_is_a_list(api, world):
    (world.modules_dir / SURPLUS / "golden.json").write_text("[]", encoding="utf-8")
    assert body_of(api, SURPLUS)["examples"] == []


# ---- adoption --------------------------------------------------------------------------------------------------------------------------

def test_a_built_module_is_not_adopted(api):
    assert body_of(api, SURPLUS)["adopted"] is None and body_of(api, YEARLY)["adopted"] is None


def test_an_adopted_module_says_when_how_and_in_which_session(api, world):
    adopted = events_where(world, "kind = 'calc.module_adopted'")[0]
    body = body_of(api, MONTHS)
    assert body["adopted"] == {"ts": adopted["ts"], "how": "asked", "session_id": ADOPT}
    assert list(body["adopted"]) == ["ts", "how", "session_id"]


def adopt_again(world, module, fingerprint, how, session):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, session, ("calc.module_adopted", {
            "module": module, "step": "s3", "fingerprint": fingerprint, "test_run_id": 2, "how": how}))
    finally:
        conn.close()


def test_the_latest_adoption_of_the_registered_fingerprint_is_the_one_shown(api, world):
    adopt_again(world, MONTHS, module_row(world, MONTHS)["fingerprint"], "replay", "replay-2")
    adopted = body_of(api, MONTHS)["adopted"]
    assert adopted["how"] == "replay" and adopted["session_id"] == "replay-2"
    last = events_where(world, "kind = 'calc.module_adopted'", newest_first=True)[0]
    assert adopted["ts"] == last["ts"]


def test_an_adoption_of_another_fingerprint_does_not_count(api, world):
    adopt_again(world, MONTHS, "f" * 64, "replay", "replay-2")
    assert body_of(api, MONTHS)["adopted"]["session_id"] == ADOPT


def test_an_adoption_of_another_module_does_not_count(api, world):
    adopt_again(world, SURPLUS, module_row(world, SURPLUS)["fingerprint"], "replay", "replay-2")
    adopted = body_of(api, SURPLUS)["adopted"]
    assert adopted == {"ts": adopted["ts"], "how": "replay", "session_id": "replay-2"}
    assert body_of(api, MONTHS)["adopted"]["session_id"] == ADOPT


def test_a_module_registered_with_another_fingerprint_than_its_adoption_is_not_adopted(api, world):
    from harness import db
    conn = db.connect()
    try:
        conn.execute("UPDATE modules SET fingerprint = ? WHERE name = ?", ("e" * 64, MONTHS))
        conn.commit()
    finally:
        conn.close()
    assert body_of(api, MONTHS)["adopted"] is None


# ---- the tests -----------------------------------------------------------------------------------------------------------------------------

def test_the_registered_test_is_the_run_the_module_names_without_a_report(api, world):
    for name in (SURPLUS, MONTHS, YEARLY):
        row = module_row(world, name)
        body = body_of(api, name)
        assert body["registered_test"] == shown_test_run(row_of_test_run(world, row["test_run_id"]))
        assert list(body["registered_test"]) == TEST_RUN_KEYS
    assert body_of(api, SURPLUS)["registered_test"]["reason"] == "build"
    assert body_of(api, MONTHS)["registered_test"]["reason"] == "adopt"


def test_the_last_test_is_the_latest_run_of_the_module_with_its_report(api, world):
    body = body_of(api, SURPLUS)
    assert body["last_test"] == shown_test_run_with_report(last_test_row(world, SURPLUS))
    assert list(body["last_test"]) == [*TEST_RUN_KEYS, "report"]
    assert body["last_test"]["id"] == 7 and body["last_test"]["reason"] == "gate"
    assert body["last_test"]["report"]["passed"] is True and isinstance(body["last_test"]["report"]["tests"], list)


def test_a_module_tested_only_once_has_the_same_registered_and_last_test(api):
    body = body_of(api, MONTHS)
    assert body["registered_test"]["id"] == body["last_test"]["id"] == 2
    assert "report" not in body["registered_test"] and "report" in body["last_test"]


def test_a_newer_failing_run_is_the_last_test(api, world):
    from harness import db
    report = {"tests": [{"name": "test_a", "passed": False, "error": "boom"}], "golden": [], "passed": False}
    conn = db.connect()
    try:
        conn.execute("INSERT INTO test_runs (ts, module, fingerprint, reason, passed, report) VALUES "
                     "('2030-01-01T00:00:00+00:00', ?, ?, 'status', 0, ?)", (SURPLUS, "d" * 64, json.dumps(report)))
        conn.commit()
    finally:
        conn.close()
    body = body_of(api, SURPLUS)
    assert body["last_test"]["passed"] is False and body["last_test"]["report"] == report
    assert body["last_test"]["reason"] == "status" and body["registered_test"]["id"] == 1


# ---- runs -------------------------------------------------------------------------------------------------------------------------------------

def test_the_runs_of_the_module_newest_first(api, world):
    runs = body_of(api, SURPLUS)["runs"]
    assert [r["id"] for r in runs] == [4, 2, 1] and all(list(r) == ["id", "ts", "session_id", "inputs", "output"] for r in runs)
    for run in runs:
        row = world.sql("SELECT * FROM calc_runs WHERE id = ?", (run["id"],))[0]
        assert run == {"id": row["id"], "ts": row["ts"], "session_id": row["session_id"],
                       "inputs": json.loads(row["inputs"]), "output": json.loads(row["output"])}


def test_a_module_that_never_ran_has_no_runs(api):
    assert body_of(api, MONTHS)["runs"] == []
    assert [r["id"] for r in body_of(api, YEARLY)["runs"]] == [3]


# ---- history -----------------------------------------------------------------------------------------------------------------------------------

def test_the_history_of_a_built_module_is_its_build_up_to_the_registration(api, world):
    history = body_of(api, SURPLUS)["history"]
    assert ids(history) == list(range(1, 11)) and all(list(e) == EVENT_KEYS for e in history)
    assert [e["kind"] for e in history][-1] == "calc.module_registered"
    stored = {e["id"]: e for e in events_where(world, "session_id = ?", (BUILD,))}
    assert all(e == stored[e["id"]] for e in history)


def test_the_history_of_an_adopted_module_is_the_adoption_not_the_build_elsewhere(api):
    history = body_of(api, MONTHS)["history"]
    assert ids(history) == [11, 12, 13]
    assert [e["kind"] for e in history] == ["calc.adopt_decision", "calc.tests_run", "calc.module_registered"]


def test_the_adoption_event_itself_comes_after_the_registration_and_is_not_in_it(api):
    assert "calc.module_adopted" not in [e["kind"] for e in body_of(api, MONTHS)["history"]]


def test_the_history_of_a_module_built_in_a_conversation_holds_the_added_step(api):
    history = body_of(api, YEARLY)["history"]
    assert ids(history) == list(range(30, 40))
    assert history[0]["kind"] == "calc.step_added" and history[0]["payload"]["step"]["id"] == "added_1"
    assert history[-1]["kind"] == "calc.module_registered"
    kinds = {e["kind"] for e in history}
    assert "ask.message" not in kinds and "ask.module_requested" not in kinds and "ask.reply" not in kinds


def test_events_of_other_modules_and_steps_in_the_same_session_are_left_out(api, world):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, "mixed",
                    ("calc.spec_proposed", {"step": "s9", "spec": {}}, "agent"),                    # 1: another step
                    ("calc.examples_proposed", {"module": "other_module", "examples": []}, "agent"),   # 2: another module
                    ("calc.spec_proposed", {"step": "s1", "spec": {}}, "agent"),                    # 3: its step
                    ("calc.tests_run", {"module": SURPLUS, "test_run_id": 1, "reason": "build", "passed": True, "fingerprint": "x"}),  # 4
                    ("calc.step_added", {"step": {"id": "added_9", "name": "x"}}),                    # 5: another added step
                    ("calc.note_saved", {"id": 3, "step": "s1", "text": "kept"}, "person"),         # 6: its step
                    ("calc.adopt_decision", {"modules": ["other_module", SURPLUS], "decision": "accepted", "text": "yes", "how": "asked"}, "person"),  # 7
                    ("calc.adopt_decision", {"modules": ["other_module"], "decision": "accepted", "text": "yes", "how": "asked"}, "person"),    # 8
                    ("calc.module_registered", {"module": SURPLUS, "step": "s1", "fingerprint": "x", "test_run_id": 1}),      # 9: the registration
                    ("calc.spec_proposed", {"step": "s1", "spec": {}}, "agent"))                    # 10: after it
    finally:
        conn.close()
    history = body_of(api, SURPLUS)["history"]
    assert [e["session_id"] for e in history] == ["mixed"] * 5
    assert [e["kind"] for e in history] == ["calc.spec_proposed", "calc.tests_run", "calc.note_saved", "calc.adopt_decision",
                                            "calc.module_registered"]
    assert [e["payload"].get("modules") for e in history if e["kind"] == "calc.adopt_decision"] == [["other_module", SURPLUS]]


def test_a_step_added_event_counts_when_its_step_id_is_the_registered_step(api, world):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, "again", ("calc.step_added", {"step": {"id": "added_1", "name": "x"}}),
                    ("calc.module_registered", {"module": YEARLY, "step": "added_1", "fingerprint": "x", "test_run_id": 5}))
    finally:
        conn.close()
    assert [e["kind"] for e in body_of(api, YEARLY)["history"]] == ["calc.step_added", "calc.module_registered"]


def test_the_latest_registration_decides_the_build_shown(api, world):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, "rebuild", ("calc.spec_proposed", {"step": "s1", "spec": {}}, "agent"),
                    ("calc.module_registered", {"module": SURPLUS, "step": "s1", "fingerprint": "x", "test_run_id": 1}))
    finally:
        conn.close()
    history = body_of(api, SURPLUS)["history"]
    assert [e["session_id"] for e in history] == ["rebuild", "rebuild"]


def test_the_function_gives_the_same_body(api, world, evidence):
    from harness import db
    conn = db.connect()
    try:
        assert json.loads(json.dumps(evidence.module(conn, MONTHS))) == body_of(api, MONTHS)
        assert evidence.module(conn, "nope") is None
    finally:
        conn.close()


def test_asking_for_a_module_runs_nothing(api, world):
    world.edit(SURPLUS)
    before = world.counts()
    body_of(api, SURPLUS)
    assert world.counts() == before


# ---- errors ----------------------------------------------------------------------------------------------------------------------------------------

def test_a_name_is_required(api):
    for path in ("/api/work/module", "/api/work/module?name="):
        reply = api.sender("GET", path)
        assert reply.status == 400 and reply.json() == {"error": "name is required"}


def test_an_unknown_module_is_404_with_the_gates_message(api):
    reply = api.sender("GET", "/api/work/module?name=nope")
    assert reply.status == 404 and reply.json() == {"error": NO_MODULE.format(name="nope")}
    assert reply.json()["error"] == h.NOT_REGISTERED.format(name="nope")


def test_a_folder_that_is_not_registered_is_not_a_module(api, world):
    s3.put_module(world.modules_dir, s3.renamed_files(h.surplus_files("s1"), "stray_module"))
    reply = api.sender("GET", "/api/work/module?name=stray_module")
    assert reply.status == 404 and reply.json() == {"error": NO_MODULE.format(name="stray_module")}
