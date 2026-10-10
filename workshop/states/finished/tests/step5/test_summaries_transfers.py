"""SPEC 9.4: own transfers, which are neither money in nor money out, and what the rule does not catch."""
from step5_helpers import month_rows, put_import, put_months


def put(conn, account, rows):
    """Rows (date, amount, description); returns the ids of the transactions in order."""
    return put_import(conn, account, rows)[1]


# ---- own_transfers: the pairing -------------------------------------------------------------------------------------------



def test_an_amount_and_its_opposite_on_one_day_in_two_accounts_are_a_pair(summaries, conn):
    [a] = put(conn, "main", [("2026-03-05", "-100.00", "to savings")])
    [b] = put(conn, "savings", [("2026-03-05", "100.00", "from main")])
    assert summaries.own_transfers(conn) == {a, b}






























# ---- what the rule deliberately does not catch -----------------------------------------------------------------------------





def test_a_payment_split_into_parts_is_not_caught(summaries, conn):
    put(conn, "main", [("2026-03-05", "-100.00", "out")])
    put(conn, "savings", [("2026-03-05", "60.00", "part"), ("2026-03-05", "40.00", "part")])
    assert summaries.own_transfers(conn) == set()






# ---- the pairs are left out of the figures --------------------------------------------------------------------------------

def transfer_world(conn):
    put_import(conn, "main", month_rows("2026-03", ins=["1000"], outs=["200"]) + [("2026-03-10", "-500.00", "to savings")])
    put_import(conn, "savings", month_rows("2026-03", ins=["30"]) + [("2026-03-10", "500.00", "from main")])


def figures(summaries, conn, measure, account):
    _, output, _ = summaries.summarise(conn, {"measure": measure, "account": account, "months": 1})
    return output["value"], output["left_out"]








