"""ARCHITECTURE.md 4.3 and 7: layer discovery stops at the setting and at the first missing package."""
import itertools
import sys

import pytest

from harness.config import load_config
from harness.layers import BASE, enabled

_names = itertools.count()


@pytest.fixture
def packages(tmp_path, monkeypatch):
    """Make five made-up layer packages on sys.path; `missing` leaves some out, `no_layer_file` some
    layer.py files. Returns the package names, in layer order."""
    monkeypatch.syspath_prepend(str(tmp_path))

    def make(missing=(), no_layer_file=(), numbers=None, layer_body=None):
        prefix = f"fakelayers{next(_names)}"
        names = []
        for k in range(1, 6):
            name = f"{prefix}_{k}"
            names.append(name)
            if k in missing:
                continue
            folder = tmp_path / name
            folder.mkdir()
            (folder / "__init__.py").write_text("", encoding="utf-8")
            if k in no_layer_file:
                continue
            number = (numbers or {}).get(k, k)
            body = (layer_body or {}).get(k, "")
            (folder / "layer.py").write_text(
                f"from harness.layers import Layer\n{body}\nLAYER = Layer(number={number}, name='fake {k}')\n",
                encoding="utf-8")
        return tuple(names)
    return make


def numbers(layers) -> list[int]:
    return [layer.number for layer in layers]


def test_all_present_and_all_enabled(monkeypatch, packages):
    monkeypatch.setenv("HARNESS_LAYERS", "5")
    found = enabled(load_config(), packages())
    assert numbers(found) == [0, 1, 2, 3, 4, 5]
    assert found[0] is BASE


def test_the_setting_turns_layers_above_it_off_and_they_are_never_imported(monkeypatch, packages):
    names = packages()
    monkeypatch.setenv("HARNESS_LAYERS", "2")
    assert numbers(enabled(load_config(), names)) == [0, 1, 2]
    assert f"{names[2]}.layer" not in sys.modules and names[2] not in sys.modules


def test_at_zero_only_the_base_is_on(monkeypatch, packages):
    names = packages()
    monkeypatch.setenv("HARNESS_LAYERS", "0")
    assert enabled(load_config(), names) == [BASE]
    assert names[0] not in sys.modules


def test_discovery_stops_at_the_first_missing_package(monkeypatch, packages):
    monkeypatch.setenv("HARNESS_LAYERS", "5")
    assert numbers(enabled(load_config(), packages(missing=(3,)))) == [0, 1, 2]


def test_a_package_without_its_layer_file_counts_as_missing(monkeypatch, packages):
    monkeypatch.setenv("HARNESS_LAYERS", "5")
    assert numbers(enabled(load_config(), packages(no_layer_file=(2,)))) == [0, 1]


def test_a_missing_import_inside_a_layer_is_an_error_not_a_missing_layer(monkeypatch, packages):
    monkeypatch.setenv("HARNESS_LAYERS", "5")
    names = packages(layer_body={2: "import no_such_module_anywhere"})
    with pytest.raises(ModuleNotFoundError):
        enabled(load_config(), names)


def test_a_layer_that_gives_the_wrong_number_is_an_error(monkeypatch, packages):
    monkeypatch.setenv("HARNESS_LAYERS", "5")
    with pytest.raises(ValueError):
        enabled(load_config(), packages(numbers={2: 4}))


def test_the_real_tree_gives_contiguous_layers_up_to_the_setting(monkeypatch):
    monkeypatch.setenv("HARNESS_LAYERS", "0")
    assert enabled(load_config()) == [BASE]
    monkeypatch.setenv("HARNESS_LAYERS", "5")
    found = numbers(enabled(load_config()))
    assert found == list(range(len(found)))
