"""The workshop tool's own tests. They run with `uv run pytest workshop/tests`, not with the harness's suite."""
import argparse
import shutil
from pathlib import Path

import pytest

from workshop import __main__ as cli
from workshop import drift, tree

from conftest import write, git


def test_the_real_manifest_matches_the_tree():
    manifest = tree.load()
    assert tree.problems(manifest) == []
    assert [s["tests"] for s in manifest["steps"]] == [f"tests/layer{k}/" for k in range(6)]
    assert manifest["steps"][0]["built"] == []         # the core is given


def test_steps_md_is_the_manifest_table():
    manifest = tree.load()
    assert (Path(cli.__file__).parent / "STEPS.md").read_text(encoding="utf-8") == cli.render_steps(manifest)


def test_the_real_manifest_names_the_packages_the_harness_discovers():
    from harness.layers import PACKAGES
    assert [s["package"] for s in tree.load()["steps"][1:]] == [p.replace(".", "/") + "/" for p in PACKAGES]


def test_the_manifest_check_names_a_file_in_two_places_a_missing_one_and_an_unlisted_one(project):
    root, manifest = project
    manifest["steps"][2]["built"].append("harness/calc/ghost.py")
    manifest["steps"][3]["given"].append("harness/calc/work.py")
    write(root, "harness/review/extra.py", "")
    found = " | ".join(tree.problems(manifest, root))
    assert "harness/calc/ghost.py (step 2) is not in the tree" in found
    assert "harness/calc/work.py is in step 2 and in step 3" in found
    assert "harness/review/extra.py is under harness/ but in no step" in found


def test_at_writes_the_local_default_and_removes_nothing(project, capsys):
    root, manifest = project
    before = tree.files_under(root, ".")
    assert cli.main(["at", "3"]) == 0
    assert (root / "my/var/layers").read_text() == "3\n"
    assert sorted(tree.files_under(root, ".")) == sorted(before + ["my/var/layers"])
    assert "step 3" in capsys.readouterr().out


def test_at_tells_when_a_layer_is_not_here_and_when_the_shell_overrides(project, monkeypatch, capsys):
    root, manifest = project
    shutil.rmtree(root / "harness/answers")
    monkeypatch.setenv("HARNESS_LAYERS", "1")
    cli.cmd_at(manifest, argparse.Namespace(n="4"))
    out = capsys.readouterr().out
    assert "Layer 3 is not in this copy" in out and "HARNESS_LAYERS=1" in out


@pytest.mark.parametrize("bad", ["6", "-1", "x", "1.5", ""])
def test_a_step_number_outside_0_to_5_is_refused_and_nothing_changes(project, bad, capsys):
    root, _ = project
    assert cli.main(["start", bad]) == 1
    assert "0 to 5" in capsys.readouterr().err
    assert (root / "harness/calc/work.py").is_file()


def test_start_removes_the_step_built_files_and_the_later_packages_and_keeps_the_rest(project):
    root, manifest = project
    tree.start(root, manifest, 3)
    assert not (root / "harness/answers/work.py").exists() and not (root / "harness/answers/layer.py").exists()
    assert (root / "harness/answers/prompt.md").is_file()                  # given
    assert not (root / "harness/needs_you").exists() and not (root / "harness/review").exists()
    assert (root / "harness/calc/work.py").is_file() and (root / "harness/base.py").is_file()
    assert all((root / f"tests/layer{k}").is_dir() for k in range(6))      # every step's tests stay
    assert (root / "workshop/README.md").is_file()


def test_start_0_removes_only_the_later_layers(project):
    root, manifest = project
    tree.start(root, manifest, 0)
    assert [p for p in tree.present(root, manifest)] == [True] + [False] * 5
    assert (root / "harness/base.py").is_file()


def test_start_sets_aside_what_the_person_changed_and_only_that(project):
    root, manifest = project
    write(root, "harness/answers/work.py", "mine = True\n")
    write(root, "harness/review/own.py", "also mine\n")
    done = tree.start(root, manifest, 3)
    kept = done["set_aside"]
    assert kept.parent == root / "my/var/set-aside"
    assert (kept / "harness/answers/work.py").read_text() == "mine = True\n"
    assert (kept / "harness/review/own.py").is_file()
    assert not (kept / "harness/answers/layer.py").exists() and not (kept / "harness/needs_you").exists()


def test_start_with_nothing_changed_makes_no_set_aside_folder(project):
    root, manifest = project
    assert tree.start(root, manifest, 2)["set_aside"] is None
    assert not (root / "my/var/set-aside").exists()


def test_start_outside_git_sets_everything_aside_because_it_cannot_tell(tmp_path):
    from conftest import make_project
    root = tmp_path / "plain"
    manifest = make_project(root)
    kept = tree.start(root, manifest, 5)["set_aside"]
    assert (kept / "harness/review/work.py").is_file()


def test_start_and_finish_never_touch_my_brief_modules_or_the_database(project):
    root, manifest = project
    keep = {"my/brief/brief.json": "b", "my/modules/m/code.py": "m", "my/var/harness.db": "d"}
    for rel, text in keep.items():
        write(root, rel, text)
    tree.start(root, manifest, 1)
    tree.finish(root, manifest, 4)
    assert {rel: (root / rel).read_text() for rel in keep} == keep


def test_finish_restores_layers_1_to_n_from_git_and_sets_aside_a_changed_file(project):
    root, manifest = project
    tree.start(root, manifest, 2)
    write(root, "harness/grounding/work.py", "changed = 1\n")
    done = tree.finish(root, manifest, 5)
    assert (root / "harness/grounding/work.py").read_text() == "X = 1\n"
    assert (done["set_aside"] / "harness/grounding/work.py").read_text() == "changed = 1\n"
    assert (root / "harness/needs_you/work.py").is_file() is True
    assert (root / "harness/calc/prompt.md").is_file()
    subprocess_status = __import__("subprocess").run(["git", "-C", str(root), "status", "--short", "harness"],
                                                     capture_output=True, text=True).stdout
    assert subprocess_status.strip() == ""            # the tree is the committed one again


def test_finish_outside_git_says_so_and_changes_nothing(tmp_path, monkeypatch, capsys):
    from conftest import make_project
    root = tmp_path / "plain"
    make_project(root)
    monkeypatch.setattr(tree, "ROOT", root)
    monkeypatch.setattr(cli, "ROOT", root)
    shutil.rmtree(root / "harness/calc")
    assert cli.main(["finish", "2"]) == 1
    assert "not a git checkout" in capsys.readouterr().err
    assert not (root / "harness/calc").exists()


def test_finish_takes_files_from_the_commit_in_the_manifest_when_head_has_moved_on(project):
    root, manifest = project
    first = __import__("subprocess").run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                                         text=True).stdout.strip()
    write(root, "harness/calc/work.py", "X = 'later'\n")
    git(root, "commit", "-qam", "moved on")
    manifest["reference"] = first
    tree.finish(root, manifest, 2)
    assert (root / "harness/calc/work.py").read_text() == "X = 2\n"
    manifest["reference"] = "0" * 40
    with pytest.raises(tree.Problem, match="not in this repository"):
        tree.finish(root, manifest, 2)


def test_finish_changes_nothing_when_the_commit_lacks_a_file(project):
    root, manifest = project
    manifest["steps"][2]["built"].append("harness/calc/new.py")
    shutil.rmtree(root / "harness/review")
    with pytest.raises(tree.Problem, match="harness/calc/new.py"):
        tree.finish(root, manifest, 5)
    assert not (root / "harness/review").exists()


def test_leave_removes_workshop_only_after_an_accept_word(project):
    root, manifest = project
    args = argparse.Namespace()
    cli.cmd_leave(manifest, args, ask=lambda _: "no")
    assert (root / "workshop").is_dir()
    cli.cmd_leave(manifest, args, ask=lambda _: (_ for _ in ()).throw(EOFError))
    assert (root / "workshop").is_dir()
    cli.cmd_leave(manifest, args, ask=lambda _: "Yes ")
    assert not (root / "workshop").exists() and (root / "harness/base.py").is_file()


def test_status_quick_shows_the_setting_and_which_layers_are_present_and_on(project, capsys):
    root, manifest = project
    tree.write_layers_file(root, 2)
    shutil.rmtree(root / "harness/needs_you")
    cli.status(manifest, argparse.Namespace(quick=True))
    lines = capsys.readouterr().out.splitlines()
    assert "my/var/layers says 2" in lines[0]
    rows = {line.split()[0]: line.split() for line in lines[2:8]}
    assert rows["2"][-3:-1] == ["yes", "yes"] and rows["3"][-3:-1] == ["yes", "no"]
    assert rows["4"][2:4] == ["harness/needs_you/", "no"] or "no" in rows["4"]


def test_check_passes_on_a_clean_project_and_names_a_layering_failure(project):
    root, manifest = project
    out = []
    assert drift.check(manifest, root, write=out.append, workers=4) == 0
    assert len([line for line in out if line.startswith(("layers<=", "HARNESS_LAYERS=", "start "))]) == 18
    write(root, "tests/layer1/test_1.py", "def test_1():\n    import harness.calc.work\n")   # layer 1 reaches up
    out.clear()
    assert drift.check(manifest, root, write=out.append, workers=4) == 1
    assert any(line.startswith("layers<=1 only") and "SURPRISE" in line for line in out)


def test_the_real_workshop_does_not_import_the_harness():
    import re
    sources = [p for p in (Path(cli.__file__).parent).glob("*.py")]
    assert not [p for p in sources if re.search(r"^\s*(import|from)\s+harness", p.read_text(), re.M)]
