"""Every test here checks the harness at step 5 (ARCHITECTURE.md section 7). Automatic passes are off unless a
test turns them on with `review="auto"`."""
import shutil

import pytest

from harness.config import load_config
from harness.core import Session
from harness.grounding.research import ResearchDesk
from harness.model import ScriptedModel
from layer5_helpers import SETTLE, FakeResearcher, SplitModel, small_plan, write_world


@pytest.fixture(autouse=True)
def harness_at_step_5(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_LAYERS", "5")
    monkeypatch.setenv("HARNESS_REVIEW", "off")
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "harness.db"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "modules"))
    monkeypatch.setenv("HARNESS_RESEARCHER", "reference")
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.delenv("HARNESS_EXAMPLE", raising=False)


@pytest.fixture(scope="session")
def built_world(tmp_path_factory):
    """The small plan and its two modules, adopted once (at step 4: the registry is layer 2's)."""
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
    for name in ("brief", "modules"):
        shutil.copytree(built_world / name, tmp_path / name)
    shutil.copy(built_world / "harness.db", tmp_path / "harness.db")
    return small_plan()


@pytest.fixture
def open_session(world, monkeypatch):
    """Open a Session at step 5 on the small world. `make(analyst, reviewer, review=, researcher=)` gives it a
    `SplitModel` (`session.model_double`) and a fake researcher (`session.researcher`). Closed after."""
    opened = []

    def make(analyst=(), reviewer=(), *, review="off", researcher=None, today="2026-10-10"):
        monkeypatch.setenv("HARNESS_REVIEW", review)
        model, fake = SplitModel(analyst, reviewer), researcher or FakeResearcher()
        session = Session(load_config(), model_factory=lambda: model,
                          desk_factory=lambda conn: ResearchDesk(fake, conn))
        session.model_double, session.researcher = model, fake
        session.memory["today"] = today
        opened.append(session)
        session.settle(SETTLE)
        return session

    yield make
    for session in opened:
        session.model_double.gate and session.model_double.gate.set()
        session.close()
