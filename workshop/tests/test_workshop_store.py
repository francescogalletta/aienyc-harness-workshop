"""DESIGN 8.7: export and store, and `store finished` pinning every other state."""
import pytest

import fake_workshop as fw
from workshop import __main__ as cli
from workshop import checks, states


@pytest.fixture
def root(tmp_path):
    return fw.make_workshop(tmp_path / "copy")


def run(root, *argv):
    return cli.main(list(argv), root=root)


def all_states(root):
    data = states.load(root)
    return {name: dict(data.state_map(name)) for name in data.names()}


def test_export_writes_the_state_and_refuses_a_folder_that_is_not_empty(root, tmp_path, capsys):
    assert run(root, "export", "1-done", str(tmp_path / "out")) == 0
    assert states.read_tree(tmp_path / "out", ["SPEC.md", "harness/", "tests/"]) == states.load(root).state_map("1-done")
    assert not (tmp_path / "out" / "pyproject.toml").exists()
    assert run(root, "export", "1-done", str(tmp_path / "out")) == 1
    assert capsys.readouterr().out.strip() == cli.DIR_NOT_EMPTY.format(dir=str(tmp_path / "out"))
    assert run(root, "export", "finished", str(tmp_path / "again")) == 0


def test_export_then_store_changes_nothing(root, tmp_path):
    before = all_states(root)
    for name in ("0-done", "1-done"):
        run(root, "export", name, str(tmp_path / name))
        assert run(root, "store", name, str(tmp_path / name)) == 0
    assert all_states(root) == before


def test_store_done_keeps_only_what_differs_from_finished(root, tmp_path, capsys):
    run(root, "export", "1-done", str(tmp_path / "x"))
    (tmp_path / "x" / "harness" / "a.py").write_text("A = 'edited'\n", encoding="utf-8")
    (tmp_path / "x" / "harness" / "note.md").unlink()
    assert run(root, "store", "1-done", str(tmp_path / "x")) == 0
    assert states.load(root).content("1-done", "harness/a.py") == b"A = 'edited'\n"
    assert states.load(root).content("1-done", "harness/note.md") is None
    assert checks.snapshots(states.load(root)) != []                  # the manifest does not explain it any more


def test_store_a_build_state_takes_only_start_files(root, tmp_path, capsys):
    run(root, "export", "2-build", str(tmp_path / "b"))
    (tmp_path / "b" / "harness" / "s.py").write_text("S = 'new start'\n", encoding="utf-8")
    assert run(root, "store", "2-build", str(tmp_path / "b")) == 0
    assert states.load(root).content("2-build", "harness/s.py") == b"S = 'new start'\n"
    capsys.readouterr()
    (tmp_path / "b" / "harness" / "a.py").write_text("A = 'not a start file'\n", encoding="utf-8")
    assert run(root, "store", "2-build", str(tmp_path / "b")) == 1
    assert capsys.readouterr().out.strip() == cli.STORE_NOT_START.format(n=2, paths="harness/a.py")
    assert states.load(root).content("2-build", "harness/a.py") == b"A = 1\n"        # nothing was stored


def test_store_finished_pins_every_other_state(root, tmp_path, capsys):
    before = all_states(root)
    run(root, "export", "finished", str(tmp_path / "f"))
    (tmp_path / "f" / "harness" / "a.py").write_text("A = 'fixed in the finished tree'\n", encoding="utf-8")
    (tmp_path / "f" / "harness" / "extra.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "f" / "harness" / "b.py").unlink()
    capsys.readouterr()
    assert run(root, "store", "finished", str(tmp_path / "f")) == 0
    out = capsys.readouterr().out.splitlines()
    after = all_states(root)
    assert after["2-done"]["harness/a.py"] == b"A = 'fixed in the finished tree'\n"
    assert after["2-done"]["harness/extra.py"] == b"X = 1\n" and "harness/b.py" not in after["2-done"]
    for name in ("0-build", "0-done", "1-build", "1-done", "2-build"):
        expected = dict(before[name])
        assert after[name] == expected, name
    assert cli.STORE_PINNED.format(state="0-done", path="harness/extra.py") not in out
    pinned = [line for line in out if line.startswith("Kept ")]
    assert cli.STORE_PINNED.format(state="1-done", path="harness/b.py") in pinned
    assert out[-1] == cli.STORED.format(state="finished", files=len(after["2-done"]), absent=0)


def test_store_finished_drops_an_overlay_file_that_now_equals_it(root, tmp_path):
    run(root, "export", "finished", str(tmp_path / "f"))
    (tmp_path / "f" / "harness" / "a.py").write_text("A = 1\n", encoding="utf-8")      # as the end of step 1 had it
    run(root, "store", "finished", str(tmp_path / "f"))
    assert "harness/a.py" not in states.load(root).overlays[1]
    assert states.load(root).content("1-done", "harness/a.py") == b"A = 1\n"
