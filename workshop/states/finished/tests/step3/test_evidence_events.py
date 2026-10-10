"""SPEC 7.4: `GET /api/work/events`, the raw event log, newest first, a page at a time."""
from urllib.parse import quote

import pytest

from step3_evidence_helpers import events_where

LIMIT_PROBLEM = "limit must be a whole number from 1 to 1000"
BEFORE_PROBLEM = "before must be a whole number"


def page(api, **query):
    path = "/api/work/events"
    if query:
        path += "?" + "&".join(f"{key}={quote(str(value), safe='')}" for key, value in query.items())
    status, body = api.get(path)
    assert status == 200, body
    return body


def ids(body):
    return [e["id"] for e in body["events"]]


@pytest.fixture
def stored(world):
    return events_where(world, newest_first=True)


# ---- the whole log -------------------------------------------------------------------------------------------------------


# ---- limit and more -------------------------------------------------------------------------------------------------------

def test_a_limit_gives_that_many_and_more(api, stored):
    body = page(api, limit=10)
    newest = stored[0]["id"]
    assert ids(body) == [e["id"] for e in stored][:10] == list(range(newest, newest - 10, -1)) and body["more"] is True


# ---- filters ----------------------------------------------------------------------------------------------------------------


def test_a_kind_that_ends_with_a_dot_is_a_prefix(api, world):
    body = page(api, kind="ask.")
    expected = events_where(world, "kind LIKE 'ask.%'", newest_first=True)
    assert ids(body) == [e["id"] for e in expected] and len(expected) > 10
    assert all(e["kind"].startswith("ask.") for e in body["events"])


# ---- no limit elsewhere / nothing written -----------------------------------------------------------------------------------------
