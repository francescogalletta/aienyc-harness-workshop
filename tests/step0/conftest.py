import pytest


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """Every test starts with no harness settings and its own database."""
    for name in ("HARNESS_DB", "HARNESS_MODEL_PROVIDER", "HARNESS_MODEL", "HARNESS_SCRIPT", "HARNESS_EXAMPLE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "harness.db"))
    return tmp_path
