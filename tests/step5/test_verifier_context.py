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











def test_the_accounts_and_their_full_months_are_in_it(verifier, conn, brief):
    put_months(conn, "main", {"2026-02": ([], []), "2026-03": ([], [])})
    context = verifier.verifier_context(conn, brief, today=TODAY)
    assert '"account": "main"' in context and '"2026-02"' in context
    assert json.dumps({"full_months": ["2026-02", "2026-03"]}, indent=2) in context










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




# ---- the system prompt, the first message and the tools ------------------------------------------------------------------













