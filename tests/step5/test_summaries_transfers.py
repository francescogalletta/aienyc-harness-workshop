"""SPEC 9.4: own transfers, which are neither money in nor money out, and what the rule does not catch."""
from step5_helpers import month_rows, put_import, put_months


def put(conn, account, rows):
    """Rows (date, amount, description); returns the ids of the transactions in order."""
    return put_import(conn, account, rows)[1]


# ---- own_transfers: the pairing -------------------------------------------------------------------------------------------

def test_no_transactions_no_transfers(summaries, conn):
    assert summaries.own_transfers(conn) == set()


def test_an_amount_and_its_opposite_on_one_day_in_two_accounts_are_a_pair(summaries, conn):
    [a] = put(conn, "main", [("2026-03-05", "-100.00", "to savings")])
    [b] = put(conn, "savings", [("2026-03-05", "100.00", "from main")])
    assert summaries.own_transfers(conn) == {a, b}


def test_the_result_is_a_set_of_ids(summaries, conn):
    put(conn, "main", [("2026-03-05", "-100.00", "x")])
    put(conn, "savings", [("2026-03-05", "100.00", "y")])
    found = summaries.own_transfers(conn)
    assert isinstance(found, set) and all(isinstance(i, int) for i in found)


def test_the_same_day_is_needed(summaries, conn):
    put(conn, "main", [("2026-03-05", "-100.00", "to savings")])
    put(conn, "savings", [("2026-03-06", "100.00", "from main")])
    assert summaries.own_transfers(conn) == set()


def test_another_account_is_needed(summaries, conn):
    put(conn, "main", [("2026-03-05", "-100.00", "out"), ("2026-03-05", "100.00", "in")])
    assert summaries.own_transfers(conn) == set()


def test_two_files_of_one_account_are_not_two_accounts(summaries, conn):
    put(conn, "main", [("2026-03-05", "-100.00", "out")])
    put(conn, "main", [("2026-03-05", "100.00", "in")])
    assert summaries.own_transfers(conn) == set()


def test_the_amount_must_be_exactly_the_opposite(summaries, conn):
    put(conn, "main", [("2026-03-05", "-100.00", "out")])
    put(conn, "savings", [("2026-03-05", "100.01", "in"), ("2026-03-05", "-100.00", "also out"),
                          ("2026-03-05", "99.99", "in too")])
    assert summaries.own_transfers(conn) == set()


def test_a_zero_amount_is_not_paired(summaries, conn):
    put(conn, "main", [("2026-03-05", "0.00", "nothing")])
    put(conn, "savings", [("2026-03-05", "0.00", "nothing")])
    assert summaries.own_transfers(conn) == set()


def test_two_money_in_transactions_are_not_a_pair(summaries, conn):
    put(conn, "main", [("2026-03-05", "100.00", "in")])
    put(conn, "savings", [("2026-03-05", "100.00", "in")])
    assert summaries.own_transfers(conn) == set()


def test_the_lowest_id_that_is_not_yet_paired_is_taken(summaries, conn):
    [out] = put(conn, "main", [("2026-03-05", "-50.00", "out")])
    [first_in] = put(conn, "savings", [("2026-03-05", "50.00", "in")])
    [second_in] = put(conn, "card", [("2026-03-05", "50.00", "in")])
    assert summaries.own_transfers(conn) == {out, first_in}
    assert second_in not in summaries.own_transfers(conn)


def test_a_lower_id_in_the_same_account_is_skipped(summaries, conn):
    [same_account_in, out] = put(conn, "main", [("2026-03-05", "50.00", "in"), ("2026-03-05", "-50.00", "out")])
    [other_in] = put(conn, "savings", [("2026-03-05", "50.00", "in")])
    assert summaries.own_transfers(conn) == {out, other_in}


def test_each_transaction_is_in_at_most_one_pair(summaries, conn):
    [one, two] = put(conn, "main", [("2026-03-05", "-50.00", "out"), ("2026-03-05", "-50.00", "out again")])
    [only_in] = put(conn, "savings", [("2026-03-05", "50.00", "in")])
    found = summaries.own_transfers(conn)
    assert found == {one, only_in} and two not in found


def test_negatives_are_taken_in_order_of_date_then_id(summaries, conn):
    """Two outs for one in: the out with the lower id is paired. With the order reversed, the other would be."""
    [first_out] = put(conn, "main", [("2026-03-05", "-50.00", "out")])
    [second_out] = put(conn, "other", [("2026-03-05", "-50.00", "out")])
    [the_in] = put(conn, "savings", [("2026-03-05", "50.00", "in")])
    assert summaries.own_transfers(conn) == {first_out, the_in}


def test_several_pairs_at_once(summaries, conn):
    a1, a2 = put(conn, "main", [("2026-03-05", "-100.00", "out"), ("2026-03-20", "-30.00", "out")])
    b1, b2 = put(conn, "savings", [("2026-03-05", "100.00", "in"), ("2026-03-20", "30.00", "in")])
    stray = put(conn, "main", [("2026-03-21", "-8.00", "shop")])[0]
    assert summaries.own_transfers(conn) == {a1, a2, b1, b2}
    assert stray not in summaries.own_transfers(conn)


def test_a_transfer_may_be_between_any_two_accounts(summaries, conn):
    [a] = put(conn, "card", [("2026-03-05", "-75.00", "out")])
    [b] = put(conn, "checking", [("2026-03-05", "75.00", "in")])
    assert summaries.own_transfers(conn) == {a, b}


def test_the_decimals_written_do_not_matter_for_an_exact_opposite(summaries, conn):
    [a] = put(conn, "main", [("2026-03-05", "-100.00", "out")])
    [b] = put(conn, "savings", [("2026-03-05", "100.00", "in")])
    assert summaries.own_transfers(conn) == {a, b}


# ---- what the rule deliberately does not catch -----------------------------------------------------------------------------

def test_a_transfer_booked_on_different_days_is_not_caught(summaries, conn):
    put(conn, "main", [("2026-03-05", "-100.00", "out")])
    put(conn, "savings", [("2026-03-07", "100.00", "in")])
    assert summaries.own_transfers(conn) == set()


def test_a_transfer_to_an_account_that_is_not_loaded_is_not_caught(summaries, conn):
    put(conn, "main", [("2026-03-05", "-100.00", "to somewhere else")])
    assert summaries.own_transfers(conn) == set()


def test_a_payment_split_into_parts_is_not_caught(summaries, conn):
    put(conn, "main", [("2026-03-05", "-100.00", "out")])
    put(conn, "savings", [("2026-03-05", "60.00", "part"), ("2026-03-05", "40.00", "part")])
    assert summaries.own_transfers(conn) == set()


def test_two_unrelated_equal_payments_in_two_accounts_are_paired_wrongly(summaries, conn):
    [a] = put(conn, "main", [("2026-03-05", "-20.00", "dinner")])
    [b] = put(conn, "savings", [("2026-03-05", "20.00", "refund from a friend")])
    assert summaries.own_transfers(conn) == {a, b}


def test_a_card_bill_that_the_cards_file_does_not_list_counts_twice(summaries, conn):
    """The bill leaves the bank account; the card file lists the charges but not the payment. Both are money out."""
    put(conn, "bank", month_rows("2026-03", outs=["300"]))
    put(conn, "card", month_rows("2026-03", outs=["300"]))
    assert summaries.own_transfers(conn) == set()
    inputs, output, _ = summaries.summarise(conn, {"measure": "money_out", "account": "all", "months": 1})
    assert output["value"] == "600.00"


# ---- the pairs are left out of the figures --------------------------------------------------------------------------------

def transfer_world(conn):
    put_import(conn, "main", month_rows("2026-03", ins=["1000"], outs=["200"]) + [("2026-03-10", "-500.00", "to savings")])
    put_import(conn, "savings", month_rows("2026-03", ins=["30"]) + [("2026-03-10", "500.00", "from main")])


def figures(summaries, conn, measure, account):
    _, output, _ = summaries.summarise(conn, {"measure": measure, "account": account, "months": 1})
    return output["value"], output["left_out"]


def test_pairs_are_left_out_for_all_accounts(summaries, conn):
    transfer_world(conn)
    assert figures(summaries, conn, "money_out", "all") == ("200.00", 2)
    assert figures(summaries, conn, "money_in", "all") == ("1030.00", 2)
    assert figures(summaries, conn, "net", "all") == ("830.00", 2)


def test_pairs_are_left_out_for_one_account_too(summaries, conn):
    transfer_world(conn)
    assert figures(summaries, conn, "money_out", "main") == ("200.00", 1)
    assert figures(summaries, conn, "money_in", "main") == ("1000.00", 1)
    assert figures(summaries, conn, "money_in", "savings") == ("30.00", 1)
    assert figures(summaries, conn, "money_out", "savings") == ("0.00", 1)


def test_left_out_counts_only_the_months_asked_for(summaries, conn):
    put_import(conn, "main", month_rows("2026-02") + [("2026-02-10", "-500.00", "to savings")] + month_rows("2026-03"))
    put_import(conn, "savings", month_rows("2026-02") + [("2026-02-10", "500.00", "from main")] + month_rows("2026-03"))
    _, output, _ = summaries.summarise(conn, {"measure": "money_out", "account": "all", "months": 1})
    assert output["months"] == ["2026-03"] and output["left_out"] == 0
    _, output, _ = summaries.summarise(conn, {"measure": "money_out", "account": "all", "months": 2})
    assert output["left_out"] == 2 and output["value"] == "0.00"


def test_a_pair_is_left_out_whichever_account_it_is_looked_at_from(summaries, conn):
    put_months(conn, "main", {"2026-03": ([], ["10"])})
    put_import(conn, "other", [("2026-03-15", "10.00", "in"), ("2026-03-01", "0.00", "s"), ("2026-03-31", "0.00", "e")])
    assert figures(summaries, conn, "money_out", "main") == ("0.00", 1)
