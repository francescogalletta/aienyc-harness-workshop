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

def test_a_report_alone_is_one_call_after_a_progress_line(check_verifier):
    found, person, model = check_verifier([report()])
    assert found == []
    assert person.log == [PROGRESS, CALL] and len(model.calls) == 1


def test_a_summary_and_a_report_are_two_calls_each_after_a_progress_line(check_verifier, example_loaded):
    found, person, model = check_verifier([summary_call(), report()])
    assert person.log == [PROGRESS, CALL, PROGRESS, CALL]
    assert len(model.calls) == 2


def test_the_progress_line_is_the_one_of_the_contract(check_verifier):
    _, person, _ = check_verifier([report()])
    assert person.told == ["  (checking your figures)"]


def test_the_assistant_message_and_the_results_are_added_together(check_verifier, example_loaded):
    _, _, model = check_verifier([summary_call(), report()])
    assert roles(model, 0) == ["user"] and roles(model, 1) == ["user", "assistant", "tool"]
    assert model.calls[1]["messages"][0] == {"role": "user", "content": MESSAGE}


def test_a_summary_result_is_the_json_of_the_run_summary_result(check_verifier, summaries, conn, example_loaded):
    expected = {"summary": 1, **summaries.summarise(conn, ARGUMENTS)[1]}
    _, _, model = check_verifier([summary_call(), report()])
    [result] = tool_messages(model, 1)
    assert result["content"] == json.dumps(expected) and not result.get("is_error")
    assert json.loads(result["content"])["value"] == "4132.31"


def test_one_reply_with_several_calls_gets_all_the_results_in_order(check_verifier, example_loaded):
    reply = h.tools(("data_summary", {"measure": "money_out", "account": "all", "months": 3}),
                    ("data_summary", {"measure": "balance", "account": "checking_2026"}),
                    ("data_summary", {"measure": "net", "account": "card_2026", "months": 3}))
    _, _, model = check_verifier([reply, report()])
    assert roles(model, 1) == ["user", "assistant", "tool", "tool", "tool"]
    results = [json.loads(m["content"]) for m in tool_messages(model, 1)]
    assert [r["summary"] for r in results] == [1, 2, 3]
    assert [r["measure"] for r in results] == ["money_out", "balance", "net"]


def test_the_summaries_are_recorded_in_order_with_the_session_of_the_check(check_verifier, conn, example_loaded):
    check_verifier([h.tools(("data_summary", ARGUMENTS), ("data_summary", {**ARGUMENTS, "measure": "net"})), report()],
                   session_id="the-check")
    assert [p["id"] for p in s5.payloads(conn, "data.summary")] == [1, 2]
    rows = s5.sql_rows(conn, "SELECT session_id FROM data_summaries")
    assert [r["session_id"] for r in rows] == ["the-check", "the-check"]


# ---- tool errors -------------------------------------------------------------------------------------------------------------

def test_a_refused_summary_is_an_error_result_with_its_reason(check_verifier, conn, example_loaded):
    arguments = {"measure": "money_out", "account": "nowhere", "months": 3}
    found, _, model = check_verifier([h.tool("data_summary", arguments), report()])
    [result] = tool_messages(model, 1)
    message = s5.SUMMARY_ACCOUNT.format(account="nowhere", accounts="card_2026, checking_2026, savings_2026")
    assert result["content"] == message and result["is_error"] is True
    assert s5.payloads(conn, "data.summary_refused") == [{"arguments": arguments, "error": message}]
    assert found == [] and len(model.calls) == 2


def test_a_summary_with_no_data_loaded_is_refused(check_verifier):
    _, _, model = check_verifier([summary_call(), report()])
    [result] = tool_messages(model, 1)
    assert result["content"] == s5.SUMMARY_NO_DATA and result["is_error"] is True


def test_any_other_tool_is_an_error(check_verifier, conn):
    _, _, model = check_verifier([h.tool("look_up", {"query": "budget"}), report()])
    [result] = tool_messages(model, 1)
    assert result["content"] == "There is no tool called look_up here." and result["is_error"] is True


@pytest.mark.parametrize("call, name", [(h.run_module(), "run_module"), (h.save_input(), "save_input"),
                                        (h.request_module(), "request_module"),
                                        (h.tool("ask_decision", {"question": "q", "options": ["a", "b"], "runs": []}),
                                         "ask_decision")])
def test_the_verifier_cannot_run_a_module_save_an_input_or_talk_to_the_person(check_verifier, conn, installed, call, name):
    _, person, model = check_verifier([call, report()])
    [result] = tool_messages(model, 1)
    assert result["content"] == f"There is no tool called {name} here." and result["is_error"] is True
    assert s5.sql_rows(conn, "SELECT * FROM inputs") == [] and s5.sql_rows(conn, "SELECT * FROM calc_runs") == []
    assert person.asked == [] and s5.events(conn, "calc.run") == []


@pytest.mark.parametrize("arguments", [{"findings": "none"}, {"findings": None}, {}, {"findings": {"claim": "x"}},
                                       {"findings": 3}])
def test_a_report_without_a_list_is_an_error_and_the_check_goes_on(check_verifier, conn, arguments):
    found, _, model = check_verifier([h.tool("report", arguments), report()])
    [result] = tool_messages(model, 1)
    assert result["content"] == s5.REPORT_SHAPE and result["is_error"] is True
    assert len(model.calls) == 2 and found == []
    assert len(s5.events(conn, "verify.report")) == 1


# ---- the report ends the check ---------------------------------------------------------------------------------------------------

def test_the_calls_before_the_report_in_one_reply_are_handled(check_verifier, conn, example_loaded):
    reply = h.tools(("data_summary", ARGUMENTS), ("report", {"findings": [entry(summary=1)]}))
    found, _, model = check_verifier([reply])
    assert len(model.calls) == 1 and len(found) == 1 and found[0]["summary"] == 1
    assert [k for k in h.kinds(conn) if k in ("data.summary", "verify.report", "finding.opened")] == [
        "data.summary", "verify.report", "finding.opened"]


def test_the_calls_after_the_report_in_one_reply_are_not_handled(check_verifier, conn, example_loaded):
    reply = h.tools(("report", {"findings": []}), ("data_summary", ARGUMENTS), ("report", {"findings": []}))
    found, _, model = check_verifier([reply, report(), report()])
    assert len(model.calls) == 1 and found == []
    assert s5.summary_rows(conn) == [] and len(s5.events(conn, "verify.report")) == 1
    assert s5.events(conn, "data.summary") == []


def test_no_model_is_called_after_the_report(check_verifier, example_loaded):
    _, person, model = check_verifier([report(), summary_call()])
    assert len(model.calls) == 1 and person.log == [PROGRESS, CALL]


# ---- a reply with no tool call -----------------------------------------------------------------------------------------------------

def test_a_reply_of_text_gets_the_reminder_to_report(check_verifier):
    found, _, model = check_verifier([h.say_text("I see nothing that differs."), report()])
    assert [(m["role"], m["content"]) for m in model.calls[1]["messages"]] == [
        ("user", MESSAGE), ("assistant", "I see nothing that differs."), ("user", s5.VERIFY_NO_REPORT)]
    assert found == []


def test_a_reply_with_no_text_and_no_call_adds_only_the_reminder(check_verifier):
    _, _, model = check_verifier([h.say_text(""), report()])
    assert [(m["role"], m["content"]) for m in model.calls[1]["messages"]] == [
        ("user", MESSAGE), ("user", s5.VERIFY_NO_REPORT)]


def test_the_reminder_is_the_text_of_the_contract(check_verifier):
    _, _, model = check_verifier([h.say_text("hmm"), report()])
    assert model.calls[1]["messages"][-1]["content"] == (
        "[harness] Call report now, with an empty list of findings when nothing differs.")


def test_text_replies_are_never_shown_to_the_person(check_verifier):
    _, person, _ = check_verifier([h.say_text("a private thought"), report()])
    assert not any("private thought" in text for _, text in person.log)


# ---- the bounds ---------------------------------------------------------------------------------------------------------------------

def test_the_constants(verifier):
    assert verifier.MAX_VERIFY_CALLS == 4 and verifier.MAX_VERIFY_SUMMARIES == 6
    for name in ("VERIFY_PROGRESS", "VERIFY_FAILED", "VERIFY_NO_REPORT", "NO_REPORT_REASON", "SUMMARY_LIMIT",
                 "REPORT_SHAPE"):
        assert getattr(verifier, name) == getattr(s5, name)
    assert h.without_descriptions(verifier.DATA_SUMMARY_SCHEMA) == s5.DATA_SUMMARY_SCHEMA
    assert h.without_descriptions(verifier.REPORT_SCHEMA) == s5.REPORT_SCHEMA


def test_four_replies_with_no_report_fail_the_check(check_verifier, conn):
    texts = [h.say_text(f"thought {k}") for k in range(5)]
    found, person, model = check_verifier(texts)
    assert found == [] and len(model.calls) == 4
    assert person.log == [PROGRESS, CALL] * 4 + [("say", FAILED.format(reason="the verifier gave no report"))]
    assert s5.events(conn, "verify.failed") == [("verify.failed", "harness", {"reason": "the verifier gave no report"})]
    assert s5.events(conn, "verify.report") == []


def test_a_report_on_the_fourth_call_is_in_time(check_verifier, example_loaded):
    found, person, model = check_verifier([summary_call(), summary_call("net"), summary_call("money_in"),
                                           report(entry(summary=1))])
    assert len(model.calls) == 4 and len(found) == 1
    assert person.told == [PROGRESS[1]] * 4


def test_a_report_on_a_fifth_call_is_too_late(check_verifier, conn, example_loaded):
    script = [summary_call(), summary_call("net"), summary_call("money_in"), summary_call("money_out"),
              report(entry(summary=1))]
    found, person, model = check_verifier(script)
    assert found == [] and len(model.calls) == 4
    assert failed_reasons(conn) == [s5.NO_REPORT_REASON]
    assert person.told[-1] == FAILED.format(reason=s5.NO_REPORT_REASON)
    assert s5.events(conn, "verify.report") == []


def test_the_summaries_of_a_failed_check_stay_recorded_and_in_order(check_verifier, conn, example_loaded):
    check_verifier([summary_call(), summary_call("net"), h.say_text("a"), h.say_text("b")])
    assert h.kinds(conn)[-3:] == ["data.summary", "data.summary", "verify.failed"]
    assert len(s5.summary_rows(conn)) == 2


def test_six_summaries_are_handled_and_the_rest_are_refused(check_verifier, conn, example_loaded):
    reply = h.tools(*[("data_summary", ARGUMENTS)] * 8)
    _, _, model = check_verifier([reply, report()])
    results = tool_messages(model, 1)
    assert len(results) == 8
    assert [bool(r.get("is_error")) for r in results] == [False] * 6 + [True, True]
    assert [r["content"] for r in results[6:]] == [s5.SUMMARY_LIMIT, s5.SUMMARY_LIMIT]
    assert len(s5.events(conn, "data.summary")) == 6 and len(s5.summary_rows(conn)) == 6
    assert s5.events(conn, "data.summary_refused") == []


def test_refused_summaries_count_towards_the_limit(check_verifier, conn, example_loaded):
    bad = {"measure": "nonsense", "account": "all", "months": 3}
    reply = h.tools(*[("data_summary", bad)] * 6, ("data_summary", ARGUMENTS))
    _, _, model = check_verifier([reply, report()])
    results = tool_messages(model, 1)
    assert [r["content"] for r in results[:6]] == [s5.SUMMARY_MEASURE] * 6
    assert results[6]["content"] == s5.SUMMARY_LIMIT and results[6]["is_error"] is True
    assert len(s5.events(conn, "data.summary_refused")) == 6 and s5.events(conn, "data.summary") == []


def test_the_limit_holds_across_replies(check_verifier, conn, example_loaded):
    three = h.tools(*[("data_summary", ARGUMENTS)] * 3)
    _, _, model = check_verifier([three, three, h.tool("data_summary", ARGUMENTS), report()])
    assert tool_messages(model, 3)[-1]["content"] == s5.SUMMARY_LIMIT
    assert len(s5.events(conn, "data.summary")) == 6


def test_the_limit_is_per_check(check_verifier, conn, example_loaded):
    six = h.tools(*[("data_summary", ARGUMENTS)] * 6)
    check_verifier([six, report()])
    _, _, model = check_verifier([h.tool("data_summary", ARGUMENTS), report()])
    assert not tool_messages(model, 1)[0].get("is_error")
    assert len(s5.events(conn, "data.summary")) == 7


def test_the_calls_of_the_verifier_are_its_own_and_make_no_other_progress_line(check_verifier, example_loaded):
    _, person, _ = check_verifier([summary_call(), summary_call("net"), report()])
    assert person.told == [PROGRESS[1]] * 3


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


def test_the_reason_is_on_one_line(check_verifier, conn):
    check_verifier(None, model=Failing([], RuntimeError("a long\nreason   with\n\nbreaks")))
    assert failed_reasons(conn) == ["RuntimeError: a long reason with breaks"]


def test_the_type_is_the_name_of_the_class(check_verifier, conn):
    class Odd(Exception):
        pass
    check_verifier(None, model=Failing([], Odd("strange")))
    assert failed_reasons(conn) == ["Odd: strange"]


def test_what_came_before_the_failure_stays_recorded(check_verifier, conn, example_loaded):
    found, person, _ = check_verifier(None, model=Failing([summary_call()], OSError("the network went")))
    assert found == []
    assert h.kinds(conn)[-2:] == ["data.summary", "verify.failed"]
    assert failed_reasons(conn) == ["OSError: the network went"]
    assert person.told == [PROGRESS[1], PROGRESS[1], FAILED.format(reason="OSError: the network went")]


def test_a_script_that_runs_out_is_an_exception_too(check_verifier, conn, example_loaded):
    found, person, model = check_verifier([summary_call()])
    assert found == [] and len(model.calls) == 2
    [reason] = failed_reasons(conn)
    assert reason.startswith("ScriptExhausted: ")
    assert person.told[-1] == FAILED.format(reason=reason)


def test_the_failure_is_recorded_for_the_session_of_the_check(check_verifier, conn):
    check_verifier(None, model=Failing([], ValueError("x")), session_id="the-check")
    [row] = s5.sql_rows(conn, "SELECT session_id, actor FROM events WHERE kind = 'verify.failed'")
    assert row == {"session_id": "the-check", "actor": "harness"}


def test_the_failure_line_does_not_look_like_a_shown_reply(check_verifier):
    _, person, _ = check_verifier(None, model=Failing([], ValueError("x")))
    assert all(text.startswith("  (") for text in person.told)
