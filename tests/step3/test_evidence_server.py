"""SPEC 7.4 and 7.5: the evidence API and `/work` through a real server on an ephemeral port."""

import pytest

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

def test_every_evidence_get_needs_the_token(api):
    for path in GET_PATHS:
        assert api.sender("GET", path, token=None).status == 403
        assert api.sender("GET", path, token="wrong").status == 403
        assert api.sender("GET", path).status == 200


def test_the_post_needs_the_token_too(api):
    assert api.sender("POST", "/api/work/test", {"module": SURPLUS}, token=None).status == 403
    assert api.sender("POST", "/api/work/test", {"module": SURPLUS}, token="wrong").status == 403


# ---- connections ---------------------------------------------------------------------------------------------------------------


# ---- the evidence session id ----------------------------------------------------------------------------------------------------


# ---- /work and / ---------------------------------------------------------------------------------------------------------------------

def test_work_serves_the_page_with_the_token_in_place_and_needs_no_token(plain):
    reply = plain("GET", "/work", token=None)
    assert reply.status == 200 and reply.content_type.startswith("text/html")
    assert reply.text == STAND_IN_PAGE.replace("__HARNESS_TOKEN__", plain.server.token)
    assert "__HARNESS_TOKEN__" not in reply.text


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


# ---- quiet and local --------------------------------------------------------------------------------------------------------------
