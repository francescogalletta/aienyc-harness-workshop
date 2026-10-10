"""DESIGN 9: the static checks on broken data, and the per-state run."""
import shutil

import pytest

import fake_workshop as fw
from workshop import __main__ as cli
from workshop import checks, states


@pytest.fixture
def root(tmp_path):
    return fw.make_workshop(tmp_path / "copy")


def load(root):
    return states.load(root)


def test_the_fake_workshop_passes_every_static_check(root):
    data = load(root)
    fw.put_state(root, "2-done")
    assert checks.manifest(data) == [] and checks.snapshots(data) == []
    assert checks.prompts(data) == [] and checks.finished(data, fw.tree_of(root)) == []


# ---- manifest ------------------------------------------------------------------------------------------------------

def test_a_wrong_format_or_step_index_is_reported(root):
    fw.manifest_change(root, lambda m: m.update(format=2))
    fw.manifest_change(root, lambda m: m["steps"][1].update(step=5))
    problems = checks.manifest(load(root))
    assert "format is not 1" in problems and "step 1 has the index 5" in problems


def test_a_missing_key_is_reported(root):
    fw.manifest_change(root, lambda m: m["steps"][0].pop("given"))
    assert any("does not have exactly the keys" in p for p in checks.manifest(load(root)))


def test_built_start_and_changed_hold_files_under_harness(root):
    fw.manifest_change(root, lambda m: m["steps"][1]["built"].append("harness/"))
    fw.manifest_change(root, lambda m: m["steps"][1]["changed"].append("SPEC.md"))
    problems = checks.manifest(load(root))
    assert any("built holds harness/" in p for p in problems) and any("changed holds SPEC.md" in p for p in problems)


def test_a_path_that_no_step_introduces_is_reported(root):
    fw.manifest_change(root, lambda m: m["steps"][1]["given"].remove("harness/note.md"))
    assert any(p.startswith("harness/note.md: introduced by step 1, which lists it nowhere")
               for p in checks.manifest(load(root)))


def test_a_path_built_in_two_steps_is_reported(root):
    fw.manifest_change(root, lambda m: m["steps"][2]["built"].append("harness/b.py"))
    assert any("harness/b.py: introduced by step 1 but built or started in step 2" in p
               for p in checks.manifest(load(root)))


def test_a_code_path_in_a_given_list_is_reported(root):
    fw.manifest_change(root, lambda m: m["steps"][2]["given"].append("harness/a.py"))
    assert any("harness/a.py: a code path in the given files of step 2" in p for p in checks.manifest(load(root)))


def test_a_changed_file_must_be_built_or_started_earlier(root):
    fw.manifest_change(root, lambda m: m["steps"][1]["changed"].append("harness/c.py"))
    assert any("harness/c.py: changed in step 1, which no earlier step builds or starts" in p
               for p in checks.manifest(load(root)))


# ---- snapshots -------------------------------------------------------------------------------------------------------

def test_an_overlay_file_equal_to_the_finished_file_is_reported(root):
    folder = root / "workshop" / "states" / "0-done" / "files" / "harness"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "b.py").write_text(fw.FINISHED["harness/b.py"], encoding="utf-8")
    assert "0-done/files/harness/b.py equals finished/" in checks.snapshots(load(root))


def test_an_absent_path_finished_does_not_have_is_reported(root):
    path = root / "workshop" / "states" / "0-done" / "absent.json"
    path.write_text(states.dump_json(["harness/nowhere.py"]), encoding="utf-8")
    assert any("names harness/nowhere.py, which finished/ does not have" in p for p in checks.snapshots(load(root)))


def test_a_build_overlay_must_hold_exactly_the_start_files(root):
    (root / "workshop" / "states" / "1-build" / "files").mkdir(parents=True)
    (root / "workshop" / "states" / "1-build" / "files" / "x.py").write_text("x", encoding="utf-8")
    assert any("1-build/files does not hold exactly the start files of step 1" in p for p in checks.snapshots(load(root)))


def test_an_overlay_may_not_hold_the_spec_or_a_test(root):
    folder = root / "workshop" / "states" / "0-done"
    (folder / "files" / "tests" / "step0").mkdir(parents=True, exist_ok=True)
    (folder / "files" / "tests" / "step0" / "test_a.py").write_text("old test", encoding="utf-8")
    (folder / "absent.json").write_text(states.dump_json(["SPEC.md"]), encoding="utf-8")
    problems = checks.snapshots(load(root))
    assert any("0-done/files/tests/step0/test_a.py is SPEC.md or a test" in p for p in problems)
    assert any("0-done/absent.json names SPEC.md, which is SPEC.md or a test" in p for p in problems)


def test_a_difference_the_manifest_does_not_explain_is_reported(root):
    fw.manifest_change(root, lambda m: m["steps"][1]["given"].remove("harness/note.md"))
    assert any("step 1: not in the manifest but different from step 0: harness/note.md" in p
               for p in checks.snapshots(load(root)))


def test_a_stale_manifest_entry_is_reported(root):
    fw.manifest_change(root, lambda m: m["steps"][2]["changed"].append("harness/b.py"))
    fw.manifest_change(root, lambda m: m["steps"][2]["given"].append("harness/note.md"))
    problems = checks.snapshots(load(root))
    assert any("changed lists files that do not differ: harness/b.py" in p for p in problems)
    assert any("given lists harness/note.md, which does not differ" in p for p in problems)


# ---- finished, spec, prompts ---------------------------------------------------------------------------------------------

def test_finished_fails_when_the_copy_has_moved_and_says_so(root):
    fw.put_state(root, "1-done")
    problems = checks.finished(load(root), fw.tree_of(root))
    assert len(problems) == 1 and "after start, next or finish" in problems[0] and "harness/a.py" in problems[0]


def test_a_prompt_lists_exactly_what_the_manifest_says(root):
    assert checks.prompts(load(root)) == []
    path = root / "workshop" / "prompts" / "p2.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("- `harness/c.py`\n", "- `harness/c.py`\n- `harness/extra.py`\n"), encoding="utf-8")
    assert checks.prompts(load(root)) == [
        "workshop/prompts/p2.md: 'Build these files (new):' differs from the manifest: harness/extra.py"]
    path.write_text(text.replace("- `harness/s.py` (given in a starting form)\n", ""), encoding="utf-8")
    assert checks.prompts(load(root)) == [
        "workshop/prompts/p2.md: 'Change these files (they exist already):' differs from the manifest: harness/s.py"]
    path.write_text(text.replace("- `tests/step2/`", "- `tests/step1/`"), encoding="utf-8")
    assert checks.prompts(load(root))[0].startswith("workshop/prompts/p2.md: 'Given files (do not edit):' differs")


def test_a_prompt_must_have_the_sentence_about_later_steps(root):
    path = root / "workshop" / "prompts" / "p1.md"
    path.write_text(path.read_text(encoding="utf-8").replace(checks.LATER_STEP_SENTENCE, ""), encoding="utf-8")
    assert checks.prompts(load(root)) == ["workshop/prompts/p1.md lacks the sentence about passages of a later step"]


def test_a_missing_prompt_is_reported(root):
    (root / "workshop" / "prompts" / "p0.md").unlink()
    assert checks.prompts(load(root)) == ["workshop/prompts/p0.md is missing"]


# ---- the command (9.2) ------------------------------------------------------------------------------------------------

def test_check_runs_the_states_it_is_given_and_prints_one_line_each(root, capsys):
    fw.put_state(root, "2-done")
    code = cli.main(["check", "0-build", "1-build", "1-done", "2-build"], root=root)
    out = capsys.readouterr().out.splitlines()
    assert code == 0 and out[0] == cli.CHECK_INTRO and out[-1] == cli.CHECK_DONE.format(passed=8, total=8)
    names = [line.split()[0] for line in out[1:-1]]
    assert names == ["manifest", "snapshots", "finished", "prompts", "0-build", "1-build", "1-done", "2-build"]
    assert "every test passes (" in out[7] and "earlier steps pass and step 1 fails, as it should" in out[6]
    assert all(" ok " in line for line in out[1:-1])


def test_check_fails_with_a_reason_when_a_build_state_passes_its_own_tests(root, capsys):
    (root / "workshop" / "states" / "finished" / "tests" / "step1" / "test_b.py").write_text(
        "def test_b():\n    assert True\n", encoding="utf-8")
    code = cli.main(["check", "1-build"], root=root)
    out = capsys.readouterr().out
    assert code == 1 and "1-build    FAIL  step 1 passes before it is built" in out


def test_check_fails_when_the_earlier_steps_fail_in_a_build_state(root, capsys):
    (root / "workshop" / "states" / "finished" / "tests" / "data" / "test_fix.py").write_text(
        "def test_fix():\n    assert False\n", encoding="utf-8")
    code = cli.main(["check", "1-build"], root=root)
    out = capsys.readouterr().out
    assert code == 1 and "1-build    FAIL  earlier steps fail" in out


def test_check_marks_a_failing_done_state_and_names_the_test(root, capsys):
    (root / "workshop" / "states" / "finished" / "tests" / "step1" / "test_b.py").write_text(
        "def test_b():\n    assert False\n", encoding="utf-8")
    fw.put_state(root, "2-done")
    code = cli.main(["check", "2-done"], root=root)
    out = capsys.readouterr().out
    assert code == 1
    line = [line for line in out.splitlines() if line.startswith("2-done")][0]
    assert "FAIL" in line and "tests/step1/test_b.py::test_b" in line
    assert out.splitlines()[-1] == cli.CHECK_DONE.format(passed=4, total=5)


def test_check_keeps_the_temporary_folder_on_request(root, capsys):
    cli.main(["check", "0-done", "--keep"], root=root)
    line = [line for line in capsys.readouterr().out.splitlines() if line.startswith("0-done")][0]
    folder = line.split(" in ")[-1]
    assert (shutil.os.path.isdir(folder)) and (shutil.os.path.exists(folder + "/pyproject.toml"))
    shutil.rmtree(folder)


def test_the_environment_of_the_tests_has_no_harness_settings(root, monkeypatch):
    monkeypatch.setenv("HARNESS_DB", "/nowhere")
    (root / "workshop" / "states" / "finished" / "tests" / "data" / "test_fix.py").write_text(
        "import os\n\n\ndef test_fix():\n    assert not [k for k in os.environ if k.startswith('HARNESS_')]\n", encoding="utf-8")
    ok, detail, _ = checks.check_state(load(root), "0-done", root=root)
    assert ok, detail
