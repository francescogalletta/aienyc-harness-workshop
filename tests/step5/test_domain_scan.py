"""SPEC 1 (rule 2, step 5) and 9: nothing under `harness/` names the example domain, its files or its column names."""
import pytest

from step5_helpers import EXAMPLE_DATA, ROOT

SUFFIXES = {".py", ".sql", ".md", ".json", ".html"}
# The stems of the example's files, headings no bank export would share and words of its story: none is a heading
# of COLUMN_NAMES, which is the one list of names under harness/ (rule 2).
NAMES = ["checking_2026", "savings_2026", "card_2026", "wedding_budget", "original_amount", "original_currency",
         "deposit paid", "glovo", "castellana", "finca los olivos"]


def harness_files():
    return [p for p in (ROOT / "harness").rglob("*") if p.is_file() and p.suffix in SUFFIXES and "__pycache__" not in p.parts]


@pytest.mark.parametrize("name", NAMES)
def test_the_harness_does_not_name_the_example(name):
    offenders = [str(p.relative_to(ROOT)) for p in harness_files() if name in p.read_text(encoding="utf-8").lower()]
    assert offenders == []


def test_the_names_are_those_of_the_example():
    """The list above is read from the example's own files, so it cannot drift from them."""
    text = " ".join(p.read_text(encoding="utf-8").lower() for p in EXAMPLE_DATA.glob("*.csv"))
    assert all(name in text or name in {"checking_2026", "savings_2026", "card_2026", "wedding_budget"} for name in NAMES)
    assert {p.stem for p in EXAMPLE_DATA.glob("*.csv")} == {"checking_2026", "savings_2026", "card_2026", "wedding_budget"}
