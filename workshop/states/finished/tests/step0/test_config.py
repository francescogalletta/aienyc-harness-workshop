"""SPEC 3.1: configuration comes from the environment, with defaults."""
from pathlib import Path

from harness.config import load_config


def test_environment_overrides_and_is_read_on_every_call(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.setenv("HARNESS_MODEL", "some-model")
    monkeypatch.setenv("HARNESS_SCRIPT", str(tmp_path / "script.json"))
    config = load_config()
    assert (config.model_provider, config.model_name) == ("scripted", "some-model")
    assert config.script_path == tmp_path / "script.json"
    monkeypatch.setenv("HARNESS_MODEL", "another-model")
    assert load_config().model_name == "another-model"


def test_the_database_default_is_under_my(monkeypatch):
    """SPEC 2, 3.1: the database defaults to a place under my/, the only place the harness writes."""
    for name in ("HARNESS_DB", "HARNESS_EXAMPLE"):
        monkeypatch.delenv(name, raising=False)
    assert load_config().db_path == Path("my/var/harness.db")
