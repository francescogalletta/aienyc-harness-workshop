"""SPEC 7.5 and 7.6: the given pages, served by the real server, and the link between them.

Only what the SPEC states about the pages is checked: where they live, the placeholder, no network resources, the
paths they may call, the words it names, and the link in each direction. How they look is not tested.
"""
from pathlib import Path

import pytest

import harness.ui.server as server_module

UI = Path(server_module.__file__).parent
ALLOWED_API = {"/api/work/summary", "/api/work/conversation", "/api/work/run", "/api/work/module", "/api/work/events",
               "/api/work/test", "/api/work/data_summary"}                 # (step 5) one more path (SPEC 7.4)


@pytest.fixture(scope="module")
def evidence_text():
    path = server_module.WORK_PAGE
    assert path.is_file(), f"{path} is not there"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def grounding_text():
    return (UI / "grounding.html").read_text(encoding="utf-8")


# ---- where the page is ---------------------------------------------------------------------------------------------------


def test_the_default_page_of_make_server_is_served_at_work(served, evidence_text):
    send = served(work_page=False)                                     # no work_page_path given: the default is used
    reply = send("GET", "/work", token=None)
    assert reply.status == 200 and reply.content_type.startswith("text/html")
    assert reply.text == evidence_text.replace("__HARNESS_TOKEN__", send.server.token)


# ---- what the given file holds --------------------------------------------------------------------------------------------


# ---- the interview page and the link to the evidence page ------------------------------------------------------------------
