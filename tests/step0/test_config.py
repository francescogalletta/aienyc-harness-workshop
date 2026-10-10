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


def test_the_defaults_are_under_my(monkeypatch):
    """SPEC 2, 3.1, 4.1: the database and the brief default to places under my/, the only place the harness writes."""
    for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_EXAMPLE"):
        monkeypatch.delenv(name, raising=False)
    config = load_config()
    assert (config.db_path, config.brief_dir) == (Path("my/var/harness.db"), Path("my/brief"))
