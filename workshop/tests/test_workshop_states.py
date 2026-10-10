"""DESIGN 6, 7 and 8.1: the content of a state, setting aside, and where a copy stands."""
import os
import time

import pytest

import fake_workshop as fw
from workshop import states


@pytest.fixture
def root(tmp_path):
    return fw.make_workshop(tmp_path / "copy")


@pytest.fixture
def data(root):
    return states.load(root)


def as_text(state):
    return {p: b.decode() for p, b in state.items()}


# ---- content (6) --------------------------------------------------------------------------------------------------

def test_the_last_done_state_is_the_finished_tree(data):
    assert as_text(data.state_map("2-done")) == fw.FINISHED


@pytest.mark.parametrize("name,tree", [("0-done", fw.END0), ("1-done", fw.END1)])
def test_an_earlier_done_state_is_finished_plus_its_overlay_minus_its_absent_files(data, name, tree):
    assert as_text(data.state_map(name)) == tree


def test_the_start_of_step_0_holds_only_what_step_0_gives(data):
    assert sorted(data.state_map("0-build")) == ["SPEC.md", "tests/data/test_fix.py", "tests/step0/test_a.py"]
    assert data.content("0-build", "SPEC.md") == fw.SPEC.encode()


def test_a_build_state_is_the_step_before_plus_the_given_files(data):
    build = as_text(data.state_map("1-build"))
    assert build["harness/a.py"] == "A = 0\n" and "harness/b.py" not in build   # the code of step 0
    assert build["harness/note.md"] == "a note\n" and build["SPEC.md"] == fw.SPEC     # step 1's given files, today's SPEC
    assert build["tests/step1/test_b.py"] == fw.FINISHED["tests/step1/test_b.py"]
    assert "tests/step2/test_c.py" not in build                                       # the tests of later steps wait


def test_a_start_file_comes_from_the_build_overlay_and_every_test_from_the_finished_tree(data):
    build = as_text(data.state_map("2-build"))
    assert build["harness/s.py"] == fw.START_S
    assert {p: t for p, t in build.items() if p.startswith("tests/")} == {p: t for p, t in fw.FINISHED.items() if p.startswith("tests/")}
    assert build["harness/a.py"] == "A = 1\n" and "harness/c.py" not in build


def test_the_tests_and_the_spec_are_the_finished_ones_in_every_state(data):
    for name in data.names():
        state = data.state_map(name)
        n = int(name[0])
        assert state["SPEC.md"] == fw.SPEC.encode()
        assert sorted(p for p in state if p.startswith("tests/step")) == [f"tests/step{k}/test_{'abc'[k]}.py" for k in range(n + 1)]
        assert all(state[p] == fw.FINISHED[p].encode() for p in state if p.startswith("tests/"))


def test_known_paths_and_known_versions(data):
    assert "harness/c.py" in data.all_paths() and "harness/s.py" in data.all_paths()
    assert data.known_versions("harness/a.py") == {b"A = 0\n", b"A = 1\n", b"A = 2\n"}
    assert data.known_versions("harness/s.py") == {fw.START_S.encode(), b"S = 'done'\n"}
    assert data.known_versions("nothing.py") == set()


def test_code_paths_and_contract_files(data):
    assert "harness/a.py" in data.code_paths() and "harness/s.py" in data.code_paths()
    assert "harness/note.md" not in data.code_paths() and "SPEC.md" not in data.code_paths()
    assert "harness/note.md" in data.contract_files() and "tests/step2/test_c.py" in data.contract_files()


def test_a_folder_entry_expands_over_the_known_paths(data):
    assert data.given(1) == ["harness/note.md", "tests/step1/test_b.py"]
    assert data.given(0) == ["SPEC.md", "tests/data/test_fix.py", "tests/step0/test_a.py"]


def test_ignored_names_are_never_read(tmp_path):
    (tmp_path / "harness" / "__pycache__").mkdir(parents=True)
    (tmp_path / "harness" / "__pycache__" / "a.cpython-313.pyc").write_bytes(b"x")
    (tmp_path / "harness" / "b.pyc").write_bytes(b"x")
    (tmp_path / "harness" / "a.py").write_text("A", encoding="utf-8")
    assert sorted(states.read_tree(tmp_path, ["harness/"])) == ["harness/a.py"]


def test_hidden_files_count(tmp_path):
    (tmp_path / "harness").mkdir()
    (tmp_path / "harness" / ".hidden").write_text("h", encoding="utf-8")
    assert list(states.read_tree(tmp_path, ["harness/"])) == ["harness/.hidden"]


# ---- apply (7) -------------------------------------------------------------------------------------------------------

def test_apply_writes_replaces_and_removes(root, data):
    fw.put_state(root, "2-done")
    written, removed, aside = states.apply(data, data.state_map("0-done"), data.all_paths(), root)
    assert fw.tree_of(root) == {p: t.encode() for p, t in fw.END0.items()}
    assert (written, removed, aside) == (1, 6, [])
    assert not (root / "tests" / "step2").exists()             # a folder left empty goes with its last file
    assert (root / "tests").is_dir()                            # a managed root stays


def test_apply_changes_nothing_when_the_copy_is_already_there(root, data):
    fw.put_state(root, "1-done")
    assert states.apply(data, data.state_map("1-done"), data.all_paths(), root) == (0, 0, [])


def test_a_changed_file_is_set_aside_before_it_is_replaced(root, data):
    fw.put_state(root, "1-done")
    (root / "harness" / "a.py").write_text("A = 'mine'\n", encoding="utf-8")
    os.utime(root / "harness" / "a.py", (1_000_000, 1_000_000))
    seen = []
    _, _, aside = states.apply(data, data.state_map("2-done"), data.all_paths(), root,
                               now=time.strptime("2026-10-01 09:08:07", "%Y-%m-%d %H:%M:%S"),
                               report=lambda path, copy: seen.append((path, copy.exists())))
    copy = root / "my" / "var" / "set-aside" / "2026-10-01_09-08-07" / "harness" / "a.py"
    assert aside == [("harness/a.py", copy)] and copy.read_text(encoding="utf-8") == "A = 'mine'\n"
    assert seen == [("harness/a.py", False)]                    # said before it was copied
    assert int(copy.stat().st_mtime) == 1_000_000               # copy2 keeps the time
    assert (root / "harness" / "a.py").read_text(encoding="utf-8") == "A = 2\n"


def test_a_file_equal_to_a_known_version_is_not_copied(root, data):
    fw.put_state(root, "1-done")
    states.apply(data, data.state_map("2-done"), data.all_paths(), root)
    assert not (root / "my").exists()


def test_a_removed_file_that_the_person_wrote_is_set_aside_too(root, data):
    fw.put_state(root, "2-done")
    (root / "harness" / "c.py").write_text("C = 'mine'\n", encoding="utf-8")
    _, _, aside = states.apply(data, data.state_map("0-done"), data.all_paths(), root)
    assert [p for p, _ in aside] == ["harness/c.py"] and not (root / "harness" / "c.py").exists()


def test_the_set_aside_folder_gets_a_number_when_the_name_is_taken(root, data):
    fw.put_state(root, "1-done")
    now = time.strptime("2026-10-01 09:08:07", "%Y-%m-%d %H:%M:%S")
    (root / "my" / "var" / "set-aside" / "2026-10-01_09-08-07").mkdir(parents=True)
    (root / "harness" / "a.py").write_text("mine", encoding="utf-8")
    _, _, aside = states.apply(data, data.state_map("2-done"), data.all_paths(), root, now=now)
    assert aside[0][1].parts[-3] == "2026-10-01_09-08-07_2"


def test_what_is_outside_the_managed_roots_and_the_known_paths_is_never_touched(root, data):
    fw.put_state(root, "2-done")
    keep = {"my/brief/x.md": "mine", "README.md": "r", ".git/config": "g", "workshop/extra.txt": "w",
            "harness/own_helper.py": "mine too", "tests/step9/test_own.py": "mine", "pyproject.toml": fw.PYPROJECT}
    fw.write_tree(root, keep)
    (root / "harness" / "__pycache__").mkdir()
    (root / "harness" / "__pycache__" / "a.pyc").write_bytes(b"x")
    states.apply(data, data.state_map("0-build"), data.all_paths(), root)
    for path, text in keep.items():
        assert (root / path).read_text(encoding="utf-8") == text, path
    assert (root / "harness" / "__pycache__" / "a.pyc").exists()
    assert not (root / "my" / "var").exists()


def test_a_folder_where_a_file_belongs_stops_everything_before_any_write(root, data):
    fw.put_state(root, "1-done")
    (root / "harness" / "c.py").mkdir()
    with pytest.raises(states.InTheWay) as error:
        states.apply(data, data.state_map("2-done"), data.all_paths(), root)
    assert error.value.path == "harness/c.py"
    assert (root / "harness" / "a.py").read_text(encoding="utf-8") == "A = 1\n"        # nothing was written


def test_a_file_where_a_folder_belongs_stops_everything(root, data):
    fw.put_state(root, "0-done")
    (root / "tests" / "step1").write_text("a file", encoding="utf-8")
    with pytest.raises(states.InTheWay) as error:
        states.apply(data, data.state_map("1-done"), data.all_paths(), root)
    assert error.value.path == "tests/step1"


# ---- where the copy stands (8.1) -------------------------------------------------------------------------------------

def where(root):
    return states.where(states.load(root), fw.tree_of(root))


@pytest.mark.parametrize("name", ["0-build", "0-done", "1-build", "1-done", "2-build", "2-done"])
def test_a_copy_that_is_a_state_is_exactly_that_state(root, name):
    fw.put_state(root, name)
    assert where(root)["exact"] == name


def test_files_outside_the_known_paths_do_not_hide_a_state(root):
    fw.put_state(root, "1-done")
    fw.write_tree(root, {"harness/own_helper.py": "x", "my/brief/x": "y"})
    assert where(root)["exact"] == "1-done"


def test_own_code_is_the_contract_of_a_step_with_the_code_that_differs(root):
    fw.put_state(root, "1-build")
    fw.write_tree(root, {"harness/b.py": "B = 'mine'\n", "harness/c.py": "C = 'early'\n"})
    result = where(root)
    assert (result["exact"], result["contract"]) == (None, 1)
    # step 0's code differs from the end of step 1, the person's file does, and a later step's file written early does
    assert result["own_code"] == ["harness/a.py", "harness/b.py", "harness/c.py"]


def test_the_contract_is_the_highest_step_whose_contract_files_are_all_there(root):
    fw.put_state(root, "1-done")
    fw.write_tree(root, {"harness/a.py": "mine"})
    assert where(root)["contract"] == 1
    fw.put_state(root, "2-done")
    (root / "harness" / "b.py").unlink()
    assert where(root)["contract"] == 2


def test_a_copy_with_no_matching_contract_gives_the_closest_step_and_the_files_that_differ(root):
    fw.put_state(root, "1-done")
    (root / "SPEC.md").write_text("changed", encoding="utf-8")
    (root / "tests" / "step1" / "test_b.py").write_text("changed", encoding="utf-8")
    result = where(root)
    assert result["contract"] is None and result["closest"] == 1
    assert result["differ"] == ["SPEC.md", "tests/step1/test_b.py"]


def test_the_labels(data):
    assert data.label("0-build") == "the start of step 0" and data.label("1-done") == "the end of step 1"
    assert data.label("2-done") == "the end of step 2, the finished harness"
