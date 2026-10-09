import json

import pytest

from step1_helpers import SOURCE


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """Every test starts with no harness settings, its own database and its own brief folder.

    The researcher is the saved reference file, so that no test reaches the web.
    """
    for name in ("HARNESS_DB", "HARNESS_MODEL_PROVIDER", "HARNESS_MODEL", "HARNESS_SCRIPT",
                 "HARNESS_RESEARCHER", "HARNESS_REFERENCE", "HARNESS_BRIEF_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "harness.db"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "brief"))
    monkeypatch.setenv("HARNESS_RESEARCHER", "reference")
    return tmp_path


@pytest.fixture
def reference_file(tmp_path):
    """A small saved reference file, as SPEC 4.2 describes."""
    path = tmp_path / "terms.json"
    path.write_text(json.dumps([
        {"term": "cash flow forecast", "aliases": ["cash forecast", "cash flow projection"],
         "definition": "A plan of the money expected in and out over a future period.",
         "sources": [{"title": "Example: cash flow forecast", "url": SOURCE}]},
        {"term": "account balance", "aliases": ["balance"],
         "definition": "The amount of money in an account at a given time.",
         "sources": [{"title": "Example: account balance", "url": "https://example.org/account-balance"}]},
    ]), encoding="utf-8")
    return path

