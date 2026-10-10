"""SPEC 7.4: `GET /api/work/run?id=N`, one calculation run and the test run it relied on."""
import json

import pytest

from step3_evidence_helpers import RUN_KEYS, SURPLUS, TEST_RUN_KEYS, YEARLY, row_of_test_run, shown_test_run


def get(api, run_id):
    return api.get(f"/api/work/run?id={run_id}")


def row_of(world, run_id):
    return world.sql("SELECT * FROM calc_runs WHERE id = ?", (run_id,))[0]


def test_the_keys_of_a_run(api):
    status, body = get(api, 1)
    assert status == 200 and list(body) == RUN_KEYS


@pytest.mark.parametrize("run_id", [1, 2, 3, 4])
def test_a_run_is_its_row_with_json_decoded(api, world, run_id):
    row = row_of(world, run_id)
    _, body = get(api, run_id)
    assert {key: body[key] for key in RUN_KEYS[:-2]} == {
        "id": row["id"], "ts": row["ts"], "session_id": row["session_id"], "module": row["module"],
        "fingerprint": row["fingerprint"], "inputs": json.loads(row["inputs"]),
        "assumptions": json.loads(row["assumptions"]), "expected": row["expected"], "output": json.loads(row["output"])}


def test_the_values_of_the_first_run(api):
    _, body = get(api, 1)
    assert body["module"] == SURPLUS and body["session_id"] == "chat-1" and body["inputs"] == {"income": "5000", "spending": "3000"}
    assert body["output"] == "2000" and body["assumptions"] == [] and isinstance(body["expected"], str)


def test_assumptions_are_a_list_and_expected_is_text(api, world):
    from harness import db
    from harness.calc import gate
    conn = db.connect()
    try:
        done = gate.call(conn, SURPLUS, {"income": "7000", "spending": "1000"}, assumptions=["income is steady", "no tax"],
                         expected="about 6000, because of the rent", session_id="probe")
    finally:
        conn.close()
    _, body = get(api, done["run_id"])
    assert body["assumptions"] == ["income is steady", "no tax"]
    assert body["expected"] == "about 6000, because of the rent" and body["output"] == "6000"
    assert body["inputs"] == {"income": "7000", "spending": "1000"}


def test_the_test_run_is_the_one_the_run_relied_on_without_its_report(api, world):
    for run_id in (1, 3):
        row = row_of(world, run_id)
        _, body = get(api, run_id)
        assert body["test_run"] == shown_test_run(row_of_test_run(world, row["test_run_id"]))
        assert list(body["test_run"]) == TEST_RUN_KEYS and "report" not in body["test_run"]
    assert get(api, 1)[1]["test_run"]["reason"] == "gate" and get(api, 1)[1]["test_run"]["passed"] is True


def test_a_run_of_an_added_step_module(api):
    _, body = get(api, 3)
    assert body["module"] == YEARLY and body["inputs"] == {"monthly": "250"} and body["output"] == "3000"


def test_a_module_registered_with_the_fingerprint_of_the_run_is_registered_now(api):
    assert all(get(api, run_id)[1]["registered_now"] is True for run_id in (1, 2, 3, 4))


def test_changed_files_do_not_unregister_the_module(api, world):
    world.edit(SURPLUS)
    assert get(api, 1)[1]["registered_now"] is True


def test_a_module_registered_with_another_fingerprint_is_not_registered_now(api, world):
    from harness import db
    conn = db.connect()
    try:
        conn.execute("UPDATE modules SET fingerprint = ? WHERE name = ?", ("0" * 64, SURPLUS))
        conn.commit()
    finally:
        conn.close()
    assert get(api, 1)[1]["registered_now"] is False
    assert get(api, 1)[1]["fingerprint"] != "0" * 64
    assert get(api, 3)[1]["registered_now"] is True                           # another module


def test_a_module_that_is_not_registered_any_more_is_not_registered_now(api, world):
    from harness import db
    conn = db.connect()
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM modules WHERE name = ?", (YEARLY,))
        conn.commit()
    finally:
        conn.close()
    assert get(api, 3)[1]["registered_now"] is False


def test_the_function_gives_the_same_body(api, world, evidence):
    from harness import db
    conn = db.connect()
    try:
        assert json.loads(json.dumps(evidence.run(conn, 2))) == get(api, 2)[1]
        assert evidence.run(conn, 99) is None
    finally:
        conn.close()


def test_asking_for_a_run_records_nothing(api, world):
    before = world.counts()
    get(api, 1)
    assert world.counts() == before


# ---- errors ---------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["abc", "1.5", "1e2", "one", "1%202"])
def test_an_id_that_is_not_a_whole_number_is_400(api, value):
    reply = api.sender("GET", f"/api/work/run?id={value}")
    assert reply.status == 400 and reply.json() == {"error": "id must be a whole number"}


def test_a_missing_id_is_400(api):
    assert api.sender("GET", "/api/work/run").status == 400
    assert api.sender("GET", "/api/work/run?id=").status == 400


def test_an_unknown_run_is_404(api):
    reply = api.sender("GET", "/api/work/run?id=99")
    assert reply.status == 404 and reply.json() == {"error": "there is no run 99"}
    reply = api.sender("GET", "/api/work/run?id=0")
    assert reply.status == 404 and reply.json() == {"error": "there is no run 0"}
