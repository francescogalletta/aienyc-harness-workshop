"""SPEC 7.4: `GET /api/work/module?name=X`, one registered module: files, examples, tests, runs and history."""

import pytest

from step3_evidence_helpers import (FILES, MODULE_KEYS, SURPLUS, TEST_RUN_KEYS, add_session, last_test_row, shown_test_run_with_report)


def get(api, name):
    return api.get(f"/api/work/module?name={name}")


def body_of(api, name):
    status, body = get(api, name)
    assert status == 200, body
    return body


def ids(events):
    return [e["id"] for e in events]


# ---- the shape and the registered facts ------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", [SURPLUS])
def test_the_keys_of_a_module(api, name):
    assert set(MODULE_KEYS) <= set(body_of(api, name))


# ---- the files -------------------------------------------------------------------------------------------------------------------

def test_the_files_are_their_text_on_disk(api, world):
    body = body_of(api, SURPLUS)
    assert list(body["files"]) == list(FILES)
    assert body["files"] == {name: world.module_text(SURPLUS, name) for name in FILES}
    assert body["file_status"] == "unchanged"


# ---- the examples ------------------------------------------------------------------------------------------------------------------


# ---- adoption --------------------------------------------------------------------------------------------------------------------------


def adopt_again(world, module, fingerprint, how, session):
    from harness import db
    conn = db.connect()
    try:
        add_session(conn, session, ("calc.module_adopted", {
            "module": module, "step": "s3", "fingerprint": fingerprint, "test_run_id": 2, "how": how}))
    finally:
        conn.close()


# ---- the tests -----------------------------------------------------------------------------------------------------------------------------


def test_the_last_test_is_the_latest_run_of_the_module_with_its_report(api, world):
    body = body_of(api, SURPLUS)
    assert body["last_test"] == shown_test_run_with_report(last_test_row(world, SURPLUS))
    assert list(body["last_test"]) == [*TEST_RUN_KEYS, "report"]
    assert body["last_test"]["id"] == 7 and body["last_test"]["reason"] == "gate"
    assert body["last_test"]["report"]["passed"] is True and isinstance(body["last_test"]["report"]["tests"], list)


# ---- runs -------------------------------------------------------------------------------------------------------------------------------------


# ---- history -----------------------------------------------------------------------------------------------------------------------------------


# ---- errors ----------------------------------------------------------------------------------------------------------------------------------------
