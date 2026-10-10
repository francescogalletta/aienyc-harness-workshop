"""Every test here checks the harness at step 1 (ARCHITECTURE.md section 7)."""
import json
from pathlib import Path

import pytest

from harness.config import load_config
from harness.core import Session
from harness.grounding import Lookup, ResearchDesk
from harness.model import ScriptedModel


@pytest.fixture(autouse=True)
def harness_at_step_1(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_LAYERS", "1")
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "harness.db"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "modules"))
    monkeypatch.setenv("HARNESS_RESEARCHER", "reference")
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.delenv("HARNESS_EXAMPLE", raising=False)


EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SETTLE = 10


class FakeResearcher:
    """Knows two terms, finds nothing else, and counts its requests."""
    TERMS = {"sinking fund": ("Sinking fund", "https://example.test/sinking-fund"),
             "opening balance": ("Opening balance", "https://example.test/opening-balance")}

    def __init__(self):
        self.asked = []

    def look_up(self, query):
        self.asked.append(query)
        found = self.TERMS.get(query.lower())
        if found is None:
            return Lookup(query=query, found=False, origin="fake")
        return Lookup(query=query, found=True, name=found[0], definition=f"{found[0]} means something.",
                      sources=({"title": f"{found[0]} (Example)", "url": found[1]},), origin="fake")


@pytest.fixture
def researcher():
    return FakeResearcher()


@pytest.fixture
def open_session(researcher):
    """Open a Session at layer 1 with a scripted model and the fake researcher. Closed after the test."""
    opened = []

    def make(script=None, **options):
        model = ScriptedModel(script or [])
        session = Session(load_config(), model_factory=lambda: model,
                          desk_factory=lambda conn: ResearchDesk(researcher, conn), **options)
        session.script = model
        opened.append(session)
        return session

    yield make
    for session in opened:
        session.close()


@pytest.fixture
def moving_brief():
    return json.loads((EXAMPLES / "moving" / "brief" / "domain_brief.json").read_text(encoding="utf-8"))


def say(session, text, step=None):
    session.act("say", {"text": text, "step": step})
    return session.settle(SETTLE)
