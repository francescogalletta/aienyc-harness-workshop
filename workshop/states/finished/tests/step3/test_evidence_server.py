"""SPEC 7.4 and 7.5: the evidence API and `/work` through a real server on an ephemeral port."""
import re
import threading

import pytest

import step3_helpers as s3
from step3_evidence_helpers import SURPLUS
from step3_helpers import CHAT1, STAND_IN_INTERVIEW, STAND_IN_PAGE

GET_PATHS = ["/api/work/summary", f"/api/work/conversation?session={CHAT1}", "/api/work/run?id=1",
             f"/api/work/module?name={SURPLUS}", "/api/work/events"]
ALL_PATHS = [*GET_PATHS, "/api/work/test"]
SIX_POSTS = ["/api/start", "/api/answer", "/api/accept", "/api/changes", "/api/wrap", "/api/stop"]


@pytest.fixture
def plain(served):
    """A server with no interview session, the stand-in evidence page, over whatever database the environment names."""
    return served()


# ---- the token ----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", GET_PATHS)
def test_every_evidence_get_needs_the_token(api, path):
    assert api.sender("GET", path, token=None).status == 403
    assert api.sender("GET", path, token="wrong").status == 403
    assert api.sender("GET", path).status == 200


def test_the_post_needs_the_token_too(api):
    assert api.sender("POST", "/api/work/test", {"module": SURPLUS}, token=None).status == 403
    assert api.sender("POST", "/api/work/test", {"module": SURPLUS}, token="wrong").status == 403


def test_an_unknown_path_under_work_is_404_with_the_token_and_403_without(api):
    assert api.sender("GET", "/api/work/nothing").status == 404
    assert api.sender("GET", "/api/work/nothing", token=None).status == 403
    assert api.sender("GET", "/api/work/").status == 404


def test_the_token_is_the_one_of_the_server_only(api):
    token = api.server.token
    assert isinstance(token, str) and len(token) >= 32
    assert api.sender("GET", "/api/work/summary", token=token[:-1] + ("a" if token[-1] != "a" else "b")).status == 403


def test_answers_and_errors_are_json(api):
    for path in GET_PATHS:
        reply = api.sender("GET", path)
        assert reply.content_type.startswith("application/json")
    reply = api.sender("GET", "/api/work/run?id=99")
    assert reply.status == 404 and reply.content_type.startswith("application/json") and list(reply.json()) == ["error"]
    assert "\n" not in reply.json()["error"]


def test_a_bad_request_does_not_stop_the_server(api):
    assert api.sender("GET", "/api/work/run?id=x").status == 400
    assert api.sender("POST", "/api/work/test", raw=b"{{").status == 400
    assert api.sender("GET", "/api/work/summary").status == 200


# ---- connections ---------------------------------------------------------------------------------------------------------------

def test_requests_at_the_same_time_each_get_an_answer(api):
    answers = []
    lock = threading.Lock()

    def ask(path):
        reply = api.sender("GET", path)
        with lock:
            answers.append((path, reply.status))

    threads = [threading.Thread(target=ask, args=(path,)) for path in GET_PATHS * 6]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert len(answers) == 30 and all(status == 200 for _, status in answers)


def test_the_database_is_read_at_each_request(api, world):
    from harness import db
    before = len(api.get("/api/work/events?limit=1000")[1]["events"])
    conn = db.connect()
    try:
        s3.record(conn, "later", "ask.message", "person", text="a later message")
    finally:
        conn.close()
    assert len(api.get("/api/work/events?limit=1000")[1]["events"]) == before + 1
    assert api.get("/api/work/summary")[1]["conversations"][0]["session_id"] == "later"


def test_a_server_over_an_empty_migrated_database(plain, tmp_path, monkeypatch):
    from harness import db
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "fresh" / "harness.db"))
    conn = db.connect()
    db.migrate(conn)
    conn.close()
    for path in ("/api/work/summary", "/api/work/events"):
        assert plain("GET", path).status == 200
    assert plain("GET", "/api/work/events").json() == {"events": [], "more": False}


# ---- the evidence session id ----------------------------------------------------------------------------------------------------

def test_each_server_has_its_own_evidence_session_id(served):
    first, second = served(), served()
    ids = [first.server.work_session_id, second.server.work_session_id]
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in ids) and ids[0] != ids[1]


# ---- /work and / ---------------------------------------------------------------------------------------------------------------------

def test_work_serves_the_page_with_the_token_in_place_and_needs_no_token(plain):
    reply = plain("GET", "/work", token=None)
    assert reply.status == 200 and reply.content_type.startswith("text/html")
    assert reply.text == STAND_IN_PAGE.replace("__HARNESS_TOKEN__", plain.server.token)
    assert "__HARNESS_TOKEN__" not in reply.text


def test_work_is_served_the_same_with_a_token(plain):
    assert plain("GET", "/work").text == plain("GET", "/work", token=None).text


def test_the_token_in_the_page_opens_the_api(plain, conn):
    token = re.search(r"const token = '([^']+)'", plain("GET", "/work", token=None).text).group(1)
    assert plain("GET", "/api/work/summary", token=token).status == 200


def test_the_page_given_to_make_server_is_the_one_served(served):
    send = served(work_page="<!doctype html><title>Mine</title>__HARNESS_TOKEN__")
    assert send("GET", "/work", token=None).text == f"<!doctype html><title>Mine</title>{send.server.token}"


def test_with_no_session_the_root_redirects_to_work(plain):
    reply = plain("GET", "/", token=None)
    assert reply.status == 303 and reply.headers["Location"] == "/work"


def test_with_no_session_the_interview_api_is_404(plain):
    assert plain("GET", "/api/state").status == 404
    for path in SIX_POSTS:
        assert plain("POST", path, {"opening": "x", "text": "x"}).status == 404, path


def test_unknown_paths_are_404(plain):
    assert plain("GET", "/nothing", token=None).status == 404
    assert plain("GET", "/work/extra", token=None).status == 404


@pytest.fixture
def with_interview(served, tmp_path, monkeypatch):
    """A server that has an interview session, the stand-in pages and the evidence API."""
    from harness import db
    from harness.config import load_config
    from harness.model import ScriptedModel
    from harness.ui.session import GroundingSession
    config = load_config()
    session = GroundingSession(config, db.connect(config.db_path), model_factory=lambda: ScriptedModel([]))
    return served(session, page=STAND_IN_INTERVIEW)


def test_with_a_session_the_root_is_the_interview_page(with_interview):
    reply = with_interview("GET", "/", token=None)
    assert reply.status == 200 and reply.text == STAND_IN_INTERVIEW.replace("__HARNESS_TOKEN__", with_interview.server.token)


def test_with_a_session_work_is_still_the_evidence_page(with_interview):
    reply = with_interview("GET", "/work", token=None)
    assert reply.status == 200 and reply.text == STAND_IN_PAGE.replace("__HARNESS_TOKEN__", with_interview.server.token)


def test_with_a_session_the_interview_api_answers(with_interview):
    assert with_interview("GET", "/api/state").status == 200


def test_with_a_session_the_summary_says_there_is_an_interview(with_interview, tmp_path):
    from harness import db
    conn = db.connect()
    db.migrate(conn)
    conn.close()
    assert with_interview("GET", "/api/work/summary").json()["interview"] is True


# ---- quiet and local --------------------------------------------------------------------------------------------------------------

def test_the_server_listens_on_this_machine_only(plain):
    assert plain.server.server_address[0] == "127.0.0.1"


def test_no_request_is_logged_to_the_terminal(api, capfd):
    capfd.readouterr()
    for path in GET_PATHS:
        api.sender("GET", path)
    api.sender("GET", "/work", token=None)
    api.sender("POST", "/api/work/test", {"module": SURPLUS})
    captured = capfd.readouterr()
    assert captured.out == "" and captured.err == ""
