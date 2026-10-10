"""SPEC 7.3, 7.4 and 9.9: what the evidence API gains: three summary keys, `data_summary`, and the traced finding block,
through a real server."""
import json

import pytest

import step5_helpers as s5
from step5_helpers import DATA_BLOCK, MESSAGE, ask_finding, entry, h, report, summary_call

OK = "Noted."
SUMMARY_ITEM_KEYS = ["id", "ts", "session_id", "measure", "account", "value"]
DATA_SUMMARY_KEYS = ["id", "ts", "session_id", "inputs", "output", "imports", "findings"]


@pytest.fixture
def story(talk, conn, example_loaded):
    """The conversation of 9.7: a finding put to the person, who keeps what they said (so a figure of the summary is shown
    in the block and nowhere else)."""
    return talk([summary_call(), report(entry()), ask_finding(1), h.say_text(OK)], ["1", "/quit"])


def summary_of(api):
    status, body = api.get("/api/work/summary")
    assert status == 200
    return body


# ---- the summary keys --------------------------------------------------------------------------------------------------------



def test_imports_are_the_payloads_of_the_events_newest_first_with_loaded_now(api, conn, example_loaded):
    body = summary_of(api)
    events = s5.payloads(conn, "data.imported")
    assert len(body["imports"]) == 3
    assert [{k: v for k, v in item.items() if k != "loaded_now"} for item in body["imports"]] == events[::-1]
    assert all(list(item)[-1] == "loaded_now" and item["loaded_now"] is True for item in body["imports"])
    assert [item["id"] for item in body["imports"]] == [3, 2, 1]












# ---- data_summary ------------------------------------------------------------------------------------------------------------------------



















# ---- the finding block, traced -------------------------------------------------------------------------------------------------------------

def block_event(api):
    status, body = api.get(f"/api/work/conversation?session={s5.SESSION}")
    assert status == 200
    [event] = [e for e in body["events"] if e["kind"] == "ask.decision_asked"]
    return event






def test_a_figure_of_the_summary_shows_as_data_with_the_id_of_the_summary(api, story):
    items = [i for i in block_event(api)["numbers"] if i["text"] == "4132.31"]
    assert items and all((i["source"], i["run_id"]) == ("data", 1) for i in items)










