"""SPEC 9.1: `0007_data.sql`: the four tables, and what `data clear` leaves."""
import re

import pytest

import step5_helpers as s5
from harness import db
from step5_helpers import ROOT, h

SPEC = (ROOT / "SPEC.md").read_text(encoding="utf-8")
MIGRATION = re.search(r"The migration `0007_data.sql` is exactly:\n\n```sql\n(.*?)```", SPEC, re.S).group(1)

COLUMNS = {
    "imports": [("id", "INTEGER", 0, 1), ("ts", "TEXT", 1, 0), ("session_id", "TEXT", 1, 0), ("file", "TEXT", 1, 0),
                ("sha256", "TEXT", 1, 0), ("account", "TEXT", 1, 0), ("sign", "TEXT", 1, 0), ("report", "TEXT", 1, 0)],
    "transactions": [("id", "INTEGER", 0, 1), ("import_id", "INTEGER", 1, 0), ("account", "TEXT", 1, 0),
                     ("date", "TEXT", 1, 0), ("amount", "TEXT", 1, 0), ("description", "TEXT", 1, 0),
                     ("balance", "TEXT", 0, 0), ("row", "INTEGER", 1, 0)],
    "data_summaries": [("id", "INTEGER", 0, 1), ("ts", "TEXT", 1, 0), ("session_id", "TEXT", 1, 0), ("inputs", "TEXT", 1, 0),
                       ("output", "TEXT", 1, 0), ("imports", "TEXT", 1, 0)],
    "findings": [("id", "INTEGER", 0, 1), ("ts", "TEXT", 1, 0), ("session_id", "TEXT", 1, 0), ("kind", "TEXT", 1, 0),
                 ("claim", "TEXT", 1, 0), ("claim_figure", "TEXT", 1, 0), ("reference", "TEXT", 1, 0),
                 ("reference_figure", "TEXT", 1, 0), ("summary_id", "INTEGER", 0, 0), ("input_name", "TEXT", 0, 0),
                 ("earlier", "TEXT", 0, 0), ("pending_note", "TEXT", 0, 0), ("difference", "TEXT", 1, 0),
                 ("block", "TEXT", 1, 0), ("options", "TEXT", 1, 0), ("status", "TEXT", 1, 0),
                 ("decision_id", "INTEGER", 0, 0), ("choice", "TEXT", 0, 0), ("chosen", "TEXT", 0, 0)],
}


def test_the_migration_file_is_the_one_of_the_spec():
    assert (db.MIGRATIONS / "0007_data.sql").read_text(encoding="utf-8").strip() == MIGRATION.strip()


def test_it_is_applied_after_the_earlier_ones(conn):
    applied = db.applied_migrations(conn)
    assert "0007_data.sql" in applied and applied.index("0007_data.sql") > applied.index("0006_decisions.sql")


@pytest.mark.parametrize("table", list(COLUMNS))
def test_the_columns_of_each_table(conn, table):
    columns = [(r["name"], r["type"], r["notnull"], r["pk"]) for r in conn.execute(f"PRAGMA table_info({table})")]
    assert columns == COLUMNS[table]


def test_the_references(conn):
    def targets(table):
        return {r["from"]: (r["table"], r["to"]) for r in conn.execute(f"PRAGMA foreign_key_list({table})")}
    assert targets("transactions") == {"import_id": ("imports", "id")}
    assert targets("findings") == {"summary_id": ("data_summaries", "id"), "decision_id": ("decisions", "id")}


def test_migrating_twice_changes_nothing(conn):
    before = db.applied_migrations(conn)
    db.migrate(conn)
    assert db.applied_migrations(conn) == before


def test_data_clear_empties_the_imports_and_transactions_only(adapter, findings, summaries, conn, example_loaded):
    summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 3}, session_id=s5.SESSION)
    findings.open_finding(conn, session_id=s5.SESSION, kind="data", claim="I spend about 5k a month", claim_figure="5k",
                          reference="x", reference_figure="4132.31", summary_id=1, difference="d")
    adapter.clear_data(conn, session_id="C")
    count = lambda table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert (count("imports"), count("transactions")) == (0, 0)
    assert (count("data_summaries"), count("findings")) == (1, 1)
    assert count("events") > 0 and len(s5.events(conn, "data.imported")) == 3


def test_the_data_clear_command_leaves_the_summaries_and_the_findings(conn, summaries, findings, example_loaded):
    summaries.run_summary(conn, {"measure": "money_out", "account": "all", "months": 3}, session_id=s5.SESSION)
    findings.open_finding(conn, session_id=s5.SESSION, kind="data", claim="I spend about 5k a month", claim_figure="5k",
                          reference="x", reference_figure="4132.31", summary_id=1, difference="d")
    result = h.run_cli(["data", "clear"])
    assert result.returncode == 0, result.stdout
    assert conn.execute("SELECT COUNT(*) FROM data_summaries").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 0
