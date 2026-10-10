"""SPEC 9.6: the loop of the verifier: its calls, its two tools, its bounds, and what happens when a check fails."""
import json

import pytest

import step5_helpers as s5
from step5_helpers import MESSAGE, PROGRESS, SESSION, entry, h, report, summary_call

CALL = ("call", "verifier")
FAILED = "  (the check of your figures did not finish: {reason})"
ARGUMENTS = {"measure": "money_out", "account": "all", "months": 3}


def roles(model, index):
    return [m["role"] for m in model.calls[index]["messages"]]


def tool_messages(model, index):
    return [m for m in model.calls[index]["messages"] if m["role"] == "tool"]


def failed_reasons(conn):
    return [p["reason"] for p in s5.payloads(conn, "verify.failed")]


# ---- the calls and the progress line -----------------------------------------------------------------------------------------















# ---- tool errors -------------------------------------------------------------------------------------------------------------







@pytest.mark.parametrize("call, name", [(h.run_module(), "run_module"), (h.save_input(), "save_input")])
def test_the_verifier_cannot_run_a_module_save_an_input_or_talk_to_the_person(check_verifier, conn, installed, call, name):
    _, person, model = check_verifier([call, report()])
    [result] = tool_messages(model, 1)
    assert result["content"] == f"There is no tool called {name} here." and result["is_error"] is True
    assert s5.sql_rows(conn, "SELECT * FROM inputs") == [] and s5.sql_rows(conn, "SELECT * FROM calc_runs") == []
    assert person.asked == [] and s5.events(conn, "calc.run") == []




# ---- the report ends the check ---------------------------------------------------------------------------------------------------







# ---- a reply with no tool call -----------------------------------------------------------------------------------------------------









# ---- the bounds ---------------------------------------------------------------------------------------------------------------------











def test_six_summaries_are_handled_and_the_rest_are_refused(check_verifier, conn, example_loaded):
    reply = h.tools(*[("data_summary", ARGUMENTS)] * 8)
    _, _, model = check_verifier([reply, report()])
    results = tool_messages(model, 1)
    assert len(results) == 8
    assert [bool(r.get("is_error")) for r in results] == [False] * 6 + [True, True]
    assert [r["content"] for r in results[6:]] == [s5.SUMMARY_LIMIT, s5.SUMMARY_LIMIT]
    assert len(s5.events(conn, "data.summary")) == 6 and len(s5.summary_rows(conn)) == 6
    assert s5.events(conn, "data.summary_refused") == []










# ---- failure ----------------------------------------------------------------------------------------------------------------------------

class Failing:
    """A model that answers some replies and then raises."""

    def __init__(self, replies, error):
        self.inner = s5.ScriptedModel(replies)
        self.error = error
        self.calls = self.inner.calls

    def complete(self, **options):
        if len(self.inner.calls) >= len(self.inner.script):
            self.inner.calls.append(options)
            raise self.error
        return self.inner.complete(**options)


def test_an_exception_fails_the_check_and_is_not_raised(check_verifier, conn):
    found, person, _ = check_verifier(None, model=Failing([], ValueError("it broke")))
    assert found == []
    assert failed_reasons(conn) == ["ValueError: it broke"]
    assert person.log == [PROGRESS, ("say", FAILED.format(reason="ValueError: it broke"))]












