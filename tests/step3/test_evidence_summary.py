"""SPEC 7.4: `GET /api/work/summary`, what the page needs to start, over the recorded story."""

import pytest

from step3_evidence_helpers import *            # noqa: F401,F403  (the key lists and row builders)
from step3_helpers import h


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
    assert set(SUMMARY_KEYS) <= set(summary())


# ---- interview, database, brief ------------------------------------------------------------------------------------


# ---- the process ---------------------------------------------------------------------------------------------------------


def test_each_step_has_its_label_name_kind_and_module(summary):
    process = {step["id"]: step for step in summary()["process"]}
    brief = {step["id"]: step for step in h.make_brief()["process"]}
    for step_id in ("s1", "s2", "s3"):
        assert process[step_id]["name"] == brief[step_id]["name"] and process[step_id]["kind"] == brief[step_id]["kind"]
        assert process[step_id]["label"] == step_id and process[step_id]["in_brief"] is True
    added = process["added_1"]
    assert added["label"] == "added_1 (not in the brief)" and added["in_brief"] is False
    assert added["kind"] == "calculation" and added["name"] == "the cost over a whole year"


# ---- the modules -----------------------------------------------------------------------------------------------------------


# ---- the conversations -------------------------------------------------------------------------------------------------------


# ---- the runs ------------------------------------------------------------------------------------------------------------------


# ---- the sessions and the kinds ---------------------------------------------------------------------------------------------


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
