"""Every test here checks the harness at step 2 (ARCHITECTURE.md section 7)."""
import pytest


@pytest.fixture(autouse=True)
def harness_at_step_2(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_LAYERS", "2")
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "harness.db"))
    monkeypatch.setenv("HARNESS_BRIEF_DIR", str(tmp_path / "brief"))
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "modules"))
    monkeypatch.setenv("HARNESS_RESEARCHER", "reference")
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
