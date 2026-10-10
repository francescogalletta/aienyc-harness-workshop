"""SPEC 9.4: a full calendar month, `full_months`, and `accounts`."""
import pytest

import step5_helpers as s5
from step5_helpers import put_import


def put_span(conn, account, first, last, *, extra=()):
    """Rows on the first and last day given (and `extra` days between), so that the rows reach exactly that far."""
    rows = [(first, "1.00", "first"), *[(day, "1.00", "between") for day in extra], (last, "1.00", "last")]
    return put_import(conn, account, rows)


# ---- full_months ------------------------------------------------------------------------------------------------------





def test_a_first_month_started_late_is_not_full(summaries, conn):
    put_span(conn, "main", "2026-01-02", "2026-03-31")
    assert summaries.full_months(conn, "main") == ["2026-02", "2026-03"]






















def test_for_all_a_month_is_full_when_it_is_full_for_every_account(summaries, conn):
    put_span(conn, "one", "2026-01-01", "2026-03-31")
    put_span(conn, "two", "2026-02-01", "2026-04-30")
    assert summaries.full_months(conn, "all") == ["2026-02", "2026-03"]






# ---- accounts ----------------------------------------------------------------------------------------------------------











