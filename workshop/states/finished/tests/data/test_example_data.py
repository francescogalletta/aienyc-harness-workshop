"""The example data is reproducible and internally consistent.

These tests do their own minimal parsing on purpose: they check the data,
not the harness.
"""
import csv
import importlib.util
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "tests" / "fixtures" / "accounts" / "example"
FILES = ["card_2026.csv", "checking_2026.csv", "savings_2026.csv", "wedding_budget.csv"]


def load_generator():
    spec = importlib.util.spec_from_file_location("generate", ROOT / "tests" / "fixtures" / "accounts" / "generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cents(spanish: str) -> int:
    return round(float(spanish.replace(".", "").replace(",", ".")) * 100)


def bank_rows(name: str):
    """Real rows of a bank export, oldest first: headers and repeats removed."""
    seen, rows = set(), []
    for line in (EXAMPLE / name).read_text(encoding="utf-8").splitlines():
        if line.startswith("Fecha;") or line in seen:
            continue
        seen.add(line)
        day, concept, amount, balance = line.split(";")
        rows.append((datetime.strptime(day, "%d/%m/%Y").date(), concept, cents(amount), cents(balance)))
    # Each export block is newest first; a stable sort on the reversed list
    # restores the true order within a day.
    rows.reverse()
    rows.sort(key=lambda r: r[0])
    return rows


def test_same_seed_gives_identical_files(tmp_path):
    gen = load_generator()
    gen.generate(tmp_path, tmp_path / "KEY.md")
    for name in FILES:
        assert (tmp_path / name).read_bytes() == (EXAMPLE / name).read_bytes(), name
    assert (tmp_path / "KEY.md").read_bytes() == (ROOT / "tests" / "fixtures" / "accounts" / "FACILITATOR_KEY.md").read_bytes()


def test_bank_balances_reconcile():
    gen = load_generator()
    for name, opening in [("checking_2026.csv", gen.CHECKING_OPENING), ("savings_2026.csv", gen.SAVINGS_OPENING)]:
        balance = opening
        for _day, concept, amount, stated in bank_rows(name):
            balance += amount
            assert balance == stated, (name, concept)


def test_checking_is_a_pasted_export():
    lines = (EXAMPLE / "checking_2026.csv").read_text(encoding="utf-8").splitlines()
    assert sum(line.startswith("Fecha;") for line in lines) == 2
    june_30 = [line for line in lines if line.startswith("30/06/2026;")]
    assert len(june_30) == 2 * len(set(june_30)) > 0


def test_card_bill_equals_previous_month_card_spending():
    by_month = {}
    with open(EXAMPLE / "card_2026.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            month = row["date"][:7]
            by_month[month] = by_month.get(month, 0) + round(float(row["amount"]) * 100)
    bills = {day.strftime("%Y-%m"): -amount for day, concept, amount, _ in bank_rows("checking_2026.csv")
             if concept.startswith("RECIBO TARJETA CREDITO")}
    for month in range(2, 10):
        assert bills[f"2026-{month:02d}"] == by_month[f"2026-{month - 1:02d}"]


def test_savings_transfers_match_between_accounts():
    out_of_checking = sorted((d, -a) for d, c, a, _ in bank_rows("checking_2026.csv")
                             if c == "TRASPASO A CUENTA AHORRO")
    into_savings = sorted((d, a) for d, c, a, _ in bank_rows("savings_2026.csv")
                          if c == "TRASPASO DESDE CUENTA CORRIENTE")
    assert out_of_checking == into_savings and len(into_savings) == 8
