"""Shared by the step 1 tests: a brief that passes every check, and the lookups behind it."""

SOURCE = "https://example.org/cash-flow-forecast"


def make_brief(**changes):
    """A brief that passes every check, given the lookups in `lookups_made()`."""
    brief = {
        "goal": "Keep a monthly cash flow forecast so that planned payments are covered.",
        "mode": "ongoing",
        "scope": {"in": ["Current account", "Planned payments"], "out": ["Investing"]},
        "glossary": [
            {"term": "Cash flow forecast", "definition": "A plan of money expected in and out.",
             "person_says": "cash flow", "source": SOURCE},
            {"term": "Typical month", "definition": "What the person usually spends in a month."},
        ],
        "particulars": [{"what": "Salary sometimes arrives late", "handling": "Do not rely on the exact day"}],
        "inputs": [{"name": "Bank export", "description": "CSV of the current account"}],
        "process": [
            {"id": "s1", "name": "Confirm the planned payments", "kind": "input",
             "needs": [], "produces": "Dated payments"},
            {"id": "s2", "name": "Decide which payments are regular", "kind": "judgment",
             "needs": ["Bank export"], "produces": "Regular payments"},
            {"id": "s3", "name": "Forecast the balance month by month", "kind": "calculation",
             "method": "cash flow forecast",
             "formula": "closing balance = opening balance + money in - money out",
             "needs": ["s1", "s2", "Bank export"], "produces": "Projected balance per month",
             "cadence": "monthly"},
            {"id": "s4", "name": "Find the months that fall short", "kind": "calculation",
             "method": "arithmetic", "formula": "shortfall = payments due - projected balance, when positive",
             "needs": ["s3"], "produces": "Months with a shortfall"},
        ],
        "definition_of_done": ["Each month I can see whether the planned payments are covered."],
        "open_questions": [],
    }
    brief.update(changes)
    return brief


def lookups_made():
    return [{"query": "cash flow forecast", "found": True, "name": "cash flow forecast",
             "definition": "A plan of the money expected in and out over a future period.",
             "sources": [{"title": "Example: cash flow forecast", "url": SOURCE}]}]
