"""SPEC 3.1: configuration comes from the environment, with defaults."""
from pathlib import Path

from harness.config import load_config


def test_defaults(monkeypatch):
    # HARNESS_EXAMPLE changes the default database (SPEC 6.2), so a shell that sets it would fail this test.
    monkeypatch.delenv("HARNESS_DB", raising=False)
    monkeypatch.delenv("HARNESS_EXAMPLE", raising=False)
    config = load_config()
    assert config.db_path == Path("var/harness.db")
    assert config.example is None
    assert config.model_provider == "auto"
    assert config.model_name == "claude-sonnet-5-5"
    assert config.script_path is None


def test_environment_overrides_and_is_read_on_every_call(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
    monkeypatch.setenv("HARNESS_MODEL", "some-model")
    monkeypatch.setenv("HARNESS_SCRIPT", str(tmp_path / "script.json"))
    config = load_config()
    assert (config.model_provider, config.model_name) == ("scripted", "some-model")
    assert config.script_path == tmp_path / "script.json"
    monkeypatch.setenv("HARNESS_MODEL", "another-model")
    assert load_config().model_name == "another-model"


def test_config_is_frozen():
    config = load_config()
    try:
        config.model_name = "changed"
    except Exception:
        return
    raise AssertionError("Config must be a frozen dataclass")
