"""SPEC 7.4 and 7.8: `POST /api/work/test`, the one write: a fresh, recorded test run (reason `status`)."""


from step3_evidence_helpers import NO_MODULE, SURPLUS, TEST_RUN_KEYS
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
    assert set(ANSWER_KEYS) <= set(body) and body["module"] == SURPLUS and body["file_status"] == "unchanged"
    assert set([*TEST_RUN_KEYS, "report"]) <= set(body["test_run"])


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


# ---- files that changed ---------------------------------------------------------------------------------------------------------


# ---- what is refused --------------------------------------------------------------------------------------------------------------

def refused_and_nothing_recorded(api, world, body=None, raw=None, **options):
    before = world.counts()
    reply = api.sender("POST", "/api/work/test", body, raw=raw, **options)
    assert world.counts() == before
    return reply


def test_an_unknown_module_is_404_with_the_gates_message(api, world):
    reply = refused_and_nothing_recorded(api, world, {"module": "nope"})
    assert reply.status == 404 and reply.json() == {"error": NO_MODULE.format(name="nope")}
    assert reply.json()["error"] == h.NOT_REGISTERED.format(name="nope")


# ---- the function --------------------------------------------------------------------------------------------------------------------
