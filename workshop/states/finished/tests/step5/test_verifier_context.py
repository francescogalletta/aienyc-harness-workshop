"""SPEC 9.6: the context of the verifier, its system prompt, its first message and its tools."""
import json

import step5_helpers as s5
from step5_helpers import MESSAGE, TODAY, h, put_months


def context_of(summaries, conn, brief, *, today=TODAY, saved=None):
    return h.sections(
        ("today", today), ("particulars", brief["particulars"]), ("inputs", brief["inputs"]),
        ("saved inputs", {} if saved is None else saved), ("accounts", summaries.accounts(conn)),
        ("all accounts", {"full_months": summaries.full_months(conn, "all")}), ("measures", summaries.MEASURES))


# ---- the context ---------------------------------------------------------------------------------------------------------

def test_the_sections_in_order_with_nothing_loaded(verifier, summaries, conn, brief):
    assert verifier.verifier_context(conn, brief, today=TODAY) == context_of(summaries, conn, brief)


def test_the_sections_in_order_with_the_example_files_loaded(verifier, summaries, conn, brief, example_loaded):
    assert verifier.verifier_context(conn, brief, today="2026-10-09") == context_of(summaries, conn, brief, today="2026-10-09")


def test_the_titles_come_in_the_order_of_the_contract(verifier, conn, brief):
    context = verifier.verifier_context(conn, brief, today=TODAY)
    positions = [context.index(f"[{title}]\n") for title in
                 ("today", "particulars", "inputs", "saved inputs", "accounts", "all accounts", "measures")]
    assert positions == sorted(positions) and positions[0] == 0


def test_today_is_the_date_given(verifier, conn, brief):
    assert verifier.verifier_context(conn, brief, today="2031-01-02").startswith("[today]\n2031-01-02\n\n[particulars]")


def test_nothing_loaded_gives_empty_accounts_and_no_full_months(verifier, conn, brief):
    context = verifier.verifier_context(conn, brief, today=TODAY)
    assert "[saved inputs]\n{}\n\n[accounts]\n[]\n\n[all accounts]\n" in context
    assert json.dumps({"full_months": []}, indent=2) in context


def test_the_accounts_and_their_full_months_are_in_it(verifier, conn, brief):
    put_months(conn, "main", {"2026-02": ([], []), "2026-03": ([], [])})
    context = verifier.verifier_context(conn, brief, today=TODAY)
    assert '"account": "main"' in context and '"2026-02"' in context
    assert json.dumps({"full_months": ["2026-02", "2026-03"]}, indent=2) in context


def test_the_measures_are_those_of_the_summaries(verifier, conn, brief):
    assert h.sections(("measures", s5.MEASURES)) in verifier.verifier_context(conn, brief, today=TODAY)


def test_saved_inputs_are_in_it_with_their_notes(verifier, conn, brief):
    s5.put_input(conn, "monthly_spending", "4,000", note="said last week")
    s5.put_input(conn, "monthly_income", "5,000", note="from the payslip")
    context = verifier.verifier_context(conn, brief, today=TODAY)
    section = context.split("[saved inputs]\n")[1].split("\n\n[accounts]")[0]
    saved = json.loads(section)
    assert sorted(saved) == ["monthly_income", "monthly_spending"]
    assert saved["monthly_spending"]["note"] == "said last week" and "4,000" in json.dumps(saved["monthly_spending"]["value"])
    assert set(saved["monthly_income"]) == {"value", "note"}


def test_saved_inputs_of_every_session_are_in_it(verifier, conn, brief):
    s5.put_input(conn, "a_value", "1,111", session_id="one")
    s5.put_input(conn, "b_value", "2,222", session_id="two")
    context = verifier.verifier_context(conn, brief, today=TODAY)
    assert "a_value" in context and "b_value" in context


def test_the_context_is_made_afresh_each_time(verifier, summaries, conn, brief):
    before = verifier.verifier_context(conn, brief, today=TODAY)
    put_months(conn, "main", {"2026-03": ([], [])})
    s5.put_input(conn, "monthly_spending", "4,000")
    after = verifier.verifier_context(conn, brief, today=TODAY)
    assert before != after and '"account": "main"' in after and "monthly_spending" in after
    assert '"account": "main"' not in before and "monthly_spending" not in before


def test_the_context_never_holds_the_conversation_or_the_rest_of_the_brief(verifier, conn, brief, example_loaded):
    from harness.calc import notes
    notes.add_note(conn, step_id="s1", text="A note about my car costing 700 a month", session_id="one")
    context = verifier.verifier_context(conn, brief, today=TODAY)
    for text in (brief["goal"], "Emergency fund", "Money kept aside for surprises", "Work out the monthly surplus",
                 "surplus = income - spending", "A note about my car", "Decide how much to set aside",
                 "I know how many months the fund takes"):
        assert text not in context, text


def test_the_context_holds_no_transaction_rows(verifier, conn, brief, example_loaded):
    context = verifier.verifier_context(conn, brief, today=TODAY)
    for text in ("RECIBO ALQUILER INMOB. CASTELLANA", "GLOVO*PEDIDO", "TRASPASO A CUENTA AHORRO", "6318.60"):
        assert text not in context, text


def test_the_particulars_and_inputs_are_the_briefs(verifier, conn, brief):
    context = verifier.verifier_context(conn, brief, today=TODAY)
    assert h.PARTICULAR in context and "Monthly income" in context and "What comes in each month" in context


# ---- the system prompt, the first message and the tools ------------------------------------------------------------------

def test_the_system_prompt_is_verifier_md_with_the_context(check_verifier, verifier, summaries, conn, brief, example_loaded):
    _, _, model = check_verifier([s5.report()], MESSAGE)
    expected = h.prompt_text("verifier.md").replace("{context}", verifier.verifier_context(conn, brief, today=TODAY))
    assert model.calls[0]["system"].strip() == expected.strip()
    assert "{context}" not in model.calls[0]["system"]


def test_the_first_message_is_the_message_exactly(check_verifier):
    message = "I spend about 5k a month.   How long until I reach my target?"
    _, _, model = check_verifier([s5.report()], message)
    assert model.calls[0]["messages"] == [{"role": "user", "content": message}]


def test_the_verifier_sees_nothing_of_the_conversation(check_verifier, conn, brief):
    _, _, model = check_verifier([s5.report()], MESSAGE)
    call = model.calls[0]
    assert [m["role"] for m in call["messages"]] == ["user"]
    assert brief["goal"] not in call["system"] and brief["goal"] not in call["messages"][0]["content"]


def test_the_tools_are_data_summary_and_report_in_that_order(check_verifier):
    _, _, model = check_verifier([s5.report()], MESSAGE)
    tools = model.calls[0]["tools"]
    assert [t.name for t in tools] == ["data_summary", "report"]
    assert [h.without_descriptions(t.input_schema) for t in tools] == [s5.DATA_SUMMARY_SCHEMA, s5.REPORT_SCHEMA]


def test_every_call_of_the_check_has_the_same_system_prompt_and_tools(check_verifier, example_loaded):
    _, _, model = check_verifier([s5.summary_call(), s5.summary_call("net"), s5.report()], MESSAGE)
    assert len(model.calls) == 3
    assert len({call["system"] for call in model.calls}) == 1
    assert all([t.name for t in call["tools"]] == ["data_summary", "report"] for call in model.calls)


def test_the_context_is_made_afresh_at_each_check(check_verifier, conn, brief):
    _, _, first = check_verifier([s5.report()], MESSAGE)
    put_months(conn, "main", {"2026-03": ([], [])})
    _, _, second = check_verifier([s5.report()], MESSAGE)
    assert first.calls[0]["system"] != second.calls[0]["system"]
    assert '"account": "main"' in second.calls[0]["system"] and '"account": "main"' not in first.calls[0]["system"]


def test_today_is_the_date_the_conversation_uses(check_verifier):
    _, _, model = check_verifier([s5.report()], MESSAGE, today="2031-07-22")
    assert "[today]\n2031-07-22\n" in model.calls[0]["system"]
