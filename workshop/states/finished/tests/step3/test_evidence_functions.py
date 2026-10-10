"""SPEC 7.3: the six functions of `harness/ui/evidence.py`, called with an open connection."""
import inspect
import json

import pytest

from step3_evidence_helpers import MONTHS, SUMMARY_KEYS, SURPLUS
from step3_helpers import CHAT1


@pytest.fixture
def open_conn(world):
    from harness import db
    conn = db.connect()
    yield conn
    conn.close()


def names(evidence):
    return {name for name in ("summary", "conversation", "run", "module", "events_page", "test_now") if hasattr(evidence, name)}


def test_the_six_functions_are_there(evidence):
    assert names(evidence) == {"summary", "conversation", "run", "module", "events_page", "test_now"}


def test_summary_takes_interview_by_keyword(evidence):
    parameters = inspect.signature(evidence.summary).parameters
    assert parameters["interview"].kind is inspect.Parameter.KEYWORD_ONLY


def test_events_page_has_these_defaults(evidence):
    parameters = inspect.signature(evidence.events_page).parameters
    assert [p for p in parameters][1:] == ["kind", "session", "before", "limit"]
    assert parameters["limit"].default == 200 and parameters["kind"].default is None
    assert parameters["session"].default is None and parameters["before"].default is None
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for name, p in parameters.items() if name != "conn")


def test_test_now_takes_the_session_id_by_keyword(evidence):
    assert inspect.signature(evidence.test_now).parameters["session_id"].kind is inspect.Parameter.KEYWORD_ONLY


def test_the_answers_are_plain_json(evidence, open_conn):
    answers = [evidence.summary(open_conn, interview=False), evidence.conversation(open_conn, CHAT1), evidence.run(open_conn, 1),
               evidence.module(open_conn, SURPLUS), evidence.events_page(open_conn)]
    for answer in answers:
        assert json.loads(json.dumps(answer)) == answer


def test_the_interview_flag_is_passed_through(evidence, open_conn):
    assert evidence.summary(open_conn, interview=True)["interview"] is True
    assert evidence.summary(open_conn, interview=False)["interview"] is False
    assert list(evidence.summary(open_conn, interview=True)) == SUMMARY_KEYS


def test_five_of_them_only_read(evidence, open_conn, world):
    before = world.counts()
    evidence.summary(open_conn, interview=True)
    evidence.conversation(open_conn, CHAT1)
    evidence.run(open_conn, 1)
    evidence.module(open_conn, SURPLUS)
    evidence.events_page(open_conn, kind="ask.", limit=3)
    assert world.counts() == before


def test_test_now_is_the_one_that_writes(evidence, open_conn, world):
    before = world.counts()
    evidence.test_now(open_conn, MONTHS, session_id="by-hand")
    after = world.counts()
    assert after["test_runs"] == before["test_runs"] + 1 and after["events"] == before["events"] + 1


def test_not_found_is_none(evidence, open_conn, world):
    before = world.counts()
    assert evidence.conversation(open_conn, "nope") is None and evidence.run(open_conn, 999) is None
    assert evidence.module(open_conn, "nope") is None and evidence.test_now(open_conn, "nope", session_id="x") is None
    assert world.counts() == before


def test_the_brief_and_modules_folders_are_read_at_the_time_of_the_call(evidence, open_conn, world, monkeypatch, tmp_path):
    assert evidence.summary(open_conn, interview=False)["brief"] is not None
    assert evidence.module(open_conn, SURPLUS)["file_status"] == "unchanged"
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "elsewhere_brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "elsewhere_modules"))
    assert evidence.summary(open_conn, interview=False)["brief"] is None
    assert evidence.module(open_conn, SURPLUS)["file_status"] == "missing"


def test_a_conversation_is_found_only_by_the_exact_session_id(evidence, open_conn):
    assert evidence.conversation(open_conn, CHAT1.upper()) is None
    assert evidence.conversation(open_conn, CHAT1 + " ") is None
    assert evidence.conversation(open_conn, CHAT1)["session_id"] == CHAT1
