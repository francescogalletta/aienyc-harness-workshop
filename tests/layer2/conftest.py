"""Every test here checks the harness at step 2 (ARCHITECTURE.md section 7)."""
import pytest

from harness.config import load_config
from harness.core import Session
from harness.model import ScriptedModel
from layer2_helpers import SETTLE, write_plan


@pytest.fixture(autouse=True)
def harness_at_step_2(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_LAYERS", "2")
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "harness.db"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "modules"))
    monkeypatch.setenv("HARNESS_RESEARCHER", "reference")
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.delenv("HARNESS_EXAMPLE", raising=False)


@pytest.fixture
def plan(tmp_path):
    """The small confirmed plan, written to the brief folder."""
    return write_plan(tmp_path / "brief")


@pytest.fixture
def open_session():
    """Open a Session at layer 2 with a scripted model (`session.script`). Closed after the test."""
    opened = []

    def make(script=None, model=None):
        model = model or ScriptedModel(script or [])
        session = Session(load_config(), model_factory=lambda: model)
        session.script = model
        opened.append(session)
        session.settle(SETTLE)          # adoption on load, if there is any
        return session

    yield make
    for session in opened:
        session.close()


@pytest.fixture
def build():
    """Press Build and wait until the build is done. Returns the state."""
    def run(session):
        applied, reason = session.act("build", {})
        assert applied, reason
        return session.settle(SETTLE)
    return run
