"""SPEC 7.4 and 7.8: `POST /api/work/test`, the one write: a fresh, recorded test run (reason `status`)."""
import json
import re

import pytest

import step3_helpers as s3
from step3_evidence_helpers import MONTHS, NO_MODULE, SURPLUS, TEST_RUN_KEYS, YEARLY, events_where, row_of_test_run, shown_test_run_with_report
from step3_helpers import h

ANSWER_KEYS = ["module", "file_status", "test_run"]
BODY_PROBLEM = "the body must be a JSON object"
EMPTY_MODULE = "module must not be empty"


def run_now(api, module=SURPLUS):
    status, body = api.post("/api/work/test", {"module": module})
    assert status == 200, body
    return body


def session_of_the_server(api):
    return api.server.work_session_id


# ---- a run that passes ----------------------------------------------------------------------------------------------------

def test_the_answer_has_the_module_the_file_status_and_the_test_run(api):
    body = run_now(api)
    assert list(body) == ANSWER_KEYS and body["module"] == SURPLUS and body["file_status"] == "unchanged"
    assert list(body["test_run"]) == [*TEST_RUN_KEYS, "report"]


def test_the_test_run_is_fresh_recorded_and_for_the_status_reason(api, world):
    before = world.counts()["test_runs"]
    body = run_now(api)
    assert world.counts()["test_runs"] == before + 1
    run = body["test_run"]
    assert run["id"] == 8 and run["reason"] == "status" and run["passed"] is True
    assert run == shown_test_run_with_report(row_of_test_run(world, run["id"]))
    assert run["fingerprint"] == world.sql("SELECT fingerprint FROM modules WHERE name = ?", (SURPLUS,))[0]["fingerprint"]
    assert run["report"]["passed"] is True and run["report"]["tests"] and len(run["report"]["golden"]) == 3


def test_the_run_is_recorded_as_calc_tests_run_with_the_evidence_session_of_the_server(api, world):
    before = len(world.events())
    body = run_now(api)
    events = world.events()
    assert len(events) == before + 1
    event = events[-1]
    assert event["kind"] == "calc.tests_run" and event["actor"] == "harness"
    assert event["session_id"] == session_of_the_server(api)
    assert event["payload"] == {"module": SURPLUS, "test_run_id": body["test_run"]["id"], "reason": "status", "passed": True,
                                "fingerprint": body["test_run"]["fingerprint"]}


def test_the_evidence_session_id_is_a_uuid4_hex_and_stays_the_same_for_the_server(api, world):
    session = session_of_the_server(api)
    assert re.fullmatch(r"[0-9a-f]{32}", session)
    run_now(api)
    run_now(api, MONTHS)
    assert {e["session_id"] for e in world.events(kind="calc.tests_run") if e["payload"]["reason"] == "status"} == {session}


def test_each_post_makes_a_new_test_run(api, world):
    first, second = run_now(api), run_now(api)
    assert second["test_run"]["id"] == first["test_run"]["id"] + 1
    assert world.counts()["test_runs"] == 9


@pytest.mark.parametrize("module", [SURPLUS, MONTHS, YEARLY])
def test_every_registered_module_can_be_tested(api, module):
    body = run_now(api, module)
    assert body["module"] == module and body["test_run"]["passed"] is True and body["file_status"] == "unchanged"


def test_nothing_else_is_written(api, world):
    before = world.counts()
    run_now(api)
    after = world.counts()
    assert {k: after[k] - before[k] for k in before} == {"events": 1, "test_runs": 1, "calc_runs": 0, "modules": 0, "notes": 0,
                                                         "added_steps": 0}


def test_the_module_registration_does_not_change(api, world):
    row = world.sql("SELECT * FROM modules WHERE name = ?", (SURPLUS,))[0]
    run_now(api)
    assert world.sql("SELECT * FROM modules WHERE name = ?", (SURPLUS,))[0] == row


def test_the_new_run_is_then_the_last_test_of_the_module(api):
    body = run_now(api)
    _, module = api.get(f"/api/work/module?name={SURPLUS}")
    assert module["last_test"]["id"] == body["test_run"]["id"] and module["last_test"]["reason"] == "status"
    assert module["registered_test"]["id"] == 1                                  # the registration stays what it was
    _, summary = api.get("/api/work/summary")
    assert {m["name"]: m["last_test"]["id"] for m in summary["modules"]}[SURPLUS] == body["test_run"]["id"]
    assert "report" not in {m["name"]: m["last_test"] for m in summary["modules"]}[SURPLUS]


def test_the_run_is_done_when_the_answer_comes(api):
    body = run_now(api)
    _, module = api.get(f"/api/work/module?name={SURPLUS}")
    assert module["last_test"] == body["test_run"]


# ---- files that changed ---------------------------------------------------------------------------------------------------------

def test_changed_files_are_tested_as_they_are_and_reported_changed(api, world):
    path = world.modules_dir / SURPLUS / "module.py"
    path.write_text(path.read_text(encoding="utf-8").replace("income - spending", "income + spending"), encoding="utf-8")
    body = run_now(api)
    assert body["file_status"] == "changed" and body["test_run"]["passed"] is False
    assert body["test_run"]["fingerprint"] == h.expected_fingerprint(world.modules_dir / SURPLUS)
    assert body["test_run"]["fingerprint"] != world.sql("SELECT fingerprint FROM modules WHERE name = ?", (SURPLUS,))[0]["fingerprint"]
    assert body["test_run"]["report"]["passed"] is False


def test_a_failing_example_is_in_the_report_by_index(api, world):
    path = world.modules_dir / SURPLUS / "golden.json"
    examples = json.loads(path.read_text(encoding="utf-8"))
    examples[1]["expected"] = "1"
    path.write_text(json.dumps(examples), encoding="utf-8")
    body = run_now(api)
    golden = {entry["index"]: entry for entry in body["test_run"]["report"]["golden"]}
    assert body["file_status"] == "changed" and body["test_run"]["passed"] is False
    assert golden[2]["passed"] is False and golden[1]["passed"] is True and golden[3]["passed"] is True


def test_a_change_that_leaves_the_tests_passing_is_still_changed(api, world):
    world.edit(SURPLUS, "module.py", prefix="# just a comment\n")
    body = run_now(api)
    assert body["file_status"] == "changed" and body["test_run"]["passed"] is True


def test_missing_files_give_a_failed_run_with_no_fingerprint(api, world):
    (world.modules_dir / SURPLUS / "tests.py").unlink()
    body = run_now(api)
    assert body["file_status"] == "missing" and body["test_run"]["passed"] is False
    assert body["test_run"]["fingerprint"] == ""
    assert body["test_run"]["report"] == {"tests": [], "golden": [], "passed": False, "error": "files missing"}
    assert world.events()[-1]["payload"]["passed"] is False


def test_a_run_that_fails_is_recorded_like_any_other(api, world):
    path = world.modules_dir / SURPLUS / "module.py"
    path.write_text(path.read_text(encoding="utf-8").replace("income - spending", "0"), encoding="utf-8")
    body = run_now(api)
    row = row_of_test_run(world, body["test_run"]["id"])
    assert row["passed"] == 0 and row["reason"] == "status" and row["module"] == SURPLUS
    assert world.events()[-1]["payload"]["test_run_id"] == row["id"]


def test_files_that_are_back_to_what_they_were_are_unchanged_again(api, world):
    original = (world.modules_dir / SURPLUS / "module.py").read_text(encoding="utf-8")
    world.edit(SURPLUS)
    assert run_now(api)["file_status"] == "changed"
    (world.modules_dir / SURPLUS / "module.py").write_text(original, encoding="utf-8")
    assert run_now(api)["file_status"] == "unchanged"


# ---- what is refused --------------------------------------------------------------------------------------------------------------

def refused_and_nothing_recorded(api, world, body=None, raw=None, **options):
    before = world.counts()
    reply = api.sender("POST", "/api/work/test", body, raw=raw, **options)
    assert world.counts() == before
    return reply


@pytest.mark.parametrize("raw", [b"not json", b"[]", b"[\"monthly_surplus\"]", b"null", b"42", b"\"monthly_surplus\"", b"{"])
def test_a_body_that_is_not_a_json_object_is_400(api, world, raw):
    reply = refused_and_nothing_recorded(api, world, raw=raw)
    assert reply.status == 400 and reply.json() == {"error": BODY_PROBLEM}


def test_an_empty_module_is_400(api, world):
    reply = refused_and_nothing_recorded(api, world, {"module": ""})
    assert reply.status == 400 and reply.json() == {"error": EMPTY_MODULE}


def test_a_missing_module_is_400(api, world):
    assert refused_and_nothing_recorded(api, world, {}).status == 400
    assert refused_and_nothing_recorded(api, world, {"name": SURPLUS}).status == 400


def test_an_unknown_module_is_404_with_the_gates_message(api, world):
    reply = refused_and_nothing_recorded(api, world, {"module": "nope"})
    assert reply.status == 404 and reply.json() == {"error": NO_MODULE.format(name="nope")}
    assert reply.json()["error"] == h.NOT_REGISTERED.format(name="nope")


def test_a_folder_that_is_not_registered_is_unknown(api, world):
    s3.put_module(world.modules_dir, s3.renamed_files(h.surplus_files("s1"), "stray_module"))
    reply = refused_and_nothing_recorded(api, world, {"module": "stray_module"})
    assert reply.status == 404 and reply.json() == {"error": NO_MODULE.format(name="stray_module")}


def test_without_the_token_nothing_runs(api, world):
    reply = refused_and_nothing_recorded(api, world, {"module": SURPLUS}, token=None)
    assert reply.status == 403


def test_with_the_wrong_token_nothing_runs(api, world):
    reply = refused_and_nothing_recorded(api, world, {"module": SURPLUS}, token="not-the-token")
    assert reply.status == 403


def test_a_get_to_the_post_path_is_404(api):
    assert api.sender("GET", "/api/work/test").status == 404
    assert api.sender("GET", f"/api/work/test?module={SURPLUS}").status == 404


@pytest.mark.parametrize("path", ["/api/work/summary", "/api/work/conversation?session=chat-1", "/api/work/run?id=1",
                                  f"/api/work/module?name={SURPLUS}", "/api/work/events"])
def test_a_post_to_a_get_path_is_404_and_runs_nothing(api, world, path):
    before = world.counts()
    reply = api.sender("POST", path, {"module": SURPLUS})
    assert reply.status == 404 and world.counts() == before


# ---- the function --------------------------------------------------------------------------------------------------------------------

def test_the_function_runs_and_records_under_the_session_it_is_given(world, evidence):
    from harness import db
    conn = db.connect()
    try:
        body = evidence.test_now(conn, SURPLUS, session_id="my-session")
        assert list(body) == ANSWER_KEYS and body["test_run"]["reason"] == "status"
        assert evidence.test_now(conn, "nope", session_id="my-session") is None
    finally:
        conn.close()
    assert world.events()[-1]["session_id"] == "my-session" and world.events()[-1]["kind"] == "calc.tests_run"
    assert world.counts()["test_runs"] == 8
