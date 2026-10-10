"""Every test here checks the harness at step 4 (ARCHITECTURE.md section 7)."""
import shutil

import pytest

from harness.config import load_config
from harness.core import Session
from harness.model import ScriptedModel
from layer4_helpers import SETTLE, small_plan, write_world


@pytest.fixture(autouse=True)
def harness_at_step_4(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_LAYERS", "4")
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "harness.db"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "modules"))
    monkeypatch.setenv("HARNESS_RESEARCHER", "reference")
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.delenv("HARNESS_EXAMPLE", raising=False)


@pytest.fixture(scope="session")
def built_world(tmp_path_factory):
    """The small plan and its two modules, adopted once: the files and the database that holds the registry."""
    folder = tmp_path_factory.mktemp("built")
    write_world(folder)
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("HARNESS_LAYERS", "4")
        patch.setenv("HARNESS_DB", str(folder / "harness.db"))
        patch.setenv("HARNESS_BRIEF_DIR", str(folder / "brief"))
        patch.setenv("HARNESS_MODULES_DIR", str(folder / "modules"))
        patch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
        session = Session(load_config(), model_factory=lambda: ScriptedModel([]))
        session.settle(SETTLE)
        session.close()
    return folder


@pytest.fixture
def world(tmp_path, built_world):
    """A copy of the small world where the session finds it, already adopted."""
    for name in ("brief", "modules"):
        shutil.copytree(built_world / name, tmp_path / name)
    shutil.copy(built_world / "harness.db", tmp_path / "harness.db")
    return small_plan()


@pytest.fixture
def open_session(world):
    """Open a Session at layer 4 on the small world with a scripted model (`session.script`). Closed after."""
    opened = []

    def make(script=None, *, today="2026-10-10"):
        model = ScriptedModel(script or [])
        session = Session(load_config(), model_factory=lambda: model)
        session.script = model
        session.memory["today"] = today
        opened.append(session)
        session.settle(SETTLE)
        return session

    yield make
    for session in opened:
        session.close()
