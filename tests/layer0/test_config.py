"""SPEC 2.1: settings come from the environment, read afresh on every call."""
from pathlib import Path

import pytest

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


def test_defaults_are_under_my_and_an_empty_variable_is_unset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)         # no local my/var/layers
    for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR", "HARNESS_EXAMPLE",
                 "HARNESS_MODEL_PROVIDER", "HARNESS_LAYERS"):
        monkeypatch.setenv(name, "")
    config = load_config()
    assert config.db_path == Path("my/var/harness.db")
    assert config.brief_dir == Path("my/brief")
    assert config.modules_dir == Path("my/modules")
    assert config.model_provider == "auto"
    assert config.example is None
    assert config.layers == 5
    assert config.review == "auto"


def test_example_mode_moves_the_defaults_to_a_copy_under_my(monkeypatch):
    for name in ("HARNESS_DB", "HARNESS_BRIEF_DIR", "HARNESS_MODULES_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARNESS_EXAMPLE", "sample")
    config = load_config()
    for path in (config.db_path, config.brief_dir, config.modules_dir):
        assert path.parts[:4] == ("my", "var", "examples", "sample")


@pytest.mark.parametrize("value, layers", [("0", 0), ("3", 3), ("5", 5), (" 2 ", 2)])
def test_harness_layers_takes_a_whole_number_from_0_to_5(monkeypatch, value, layers):
    monkeypatch.setenv("HARNESS_LAYERS", value)
    assert load_config().layers == layers


@pytest.mark.parametrize("value", ["6", "-1", "two", "1.5", "²"])
def test_any_other_harness_layers_is_an_error_naming_the_variable(monkeypatch, value):
    monkeypatch.setenv("HARNESS_LAYERS", value)
    with pytest.raises(ValueError, match="HARNESS_LAYERS"):
        load_config()


def test_harness_review_is_auto_or_off(monkeypatch):
    monkeypatch.setenv("HARNESS_REVIEW", "off")
    assert load_config().review == "off"
    monkeypatch.setenv("HARNESS_REVIEW", "sometimes")
    with pytest.raises(ValueError, match="HARNESS_REVIEW"):
        load_config()


def test_a_local_layers_file_is_the_default_and_the_variable_wins(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HARNESS_LAYERS", raising=False)
    (tmp_path / "my" / "var").mkdir(parents=True)
    (tmp_path / "my" / "var" / "layers").write_text("3\n")
    assert load_config().layers == 3
    monkeypatch.setenv("HARNESS_LAYERS", "1")
    assert load_config().layers == 1
    monkeypatch.setenv("HARNESS_LAYERS", "")       # an empty variable counts as unset
    assert load_config().layers == 3


def test_a_bad_layers_file_is_an_error_naming_the_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("HARNESS_LAYERS", raising=False)
    (tmp_path / "my" / "var").mkdir(parents=True)
    (tmp_path / "my" / "var" / "layers").write_text("six")
    with pytest.raises(ValueError, match="my.var.layers"):
        load_config()
