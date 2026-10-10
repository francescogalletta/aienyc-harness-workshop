"""Every test here checks the harness at step 0 (ARCHITECTURE.md section 7).

The core is tested with made-up layers (`layer0_helpers.fake_layer`), so these tests rely on
nothing a real layer registers.
"""
import pytest

from harness.config import load_config
from harness.core import Session
from harness.layers import BASE
from harness.model import ScriptedModel

SETTINGS = ("HARNESS_DB", "HARNESS_MODEL_PROVIDER", "HARNESS_MODEL", "HARNESS_SCRIPT", "HARNESS_RESEARCHER",
            "HARNESS_REFERENCE", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE",
            "HARNESS_LAYERS", "HARNESS_REVIEW")


@pytest.fixture(autouse=True)
def harness_at_step_0(monkeypatch, tmp_path):
    """No harness setting from outside; layer 0 only; a database and folders of the test's own."""
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_LAYERS", "0")
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "var" / "harness.db"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "modules"))
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    return tmp_path


@pytest.fixture
def open_session():
    """Open a Session on the test database with the given made-up layers. Closed after the test."""
    opened = []

    def make(*layers, script=None, **options):
        model_factory = options.pop("model_factory", None) or (lambda: ScriptedModel(script or [{"text": "ok"}]))
        session = Session(load_config(), layers=[BASE, *layers], model_factory=model_factory, **options)
        opened.append(session)
        return session

    yield make
    for session in opened:
        session.close()
