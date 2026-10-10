"""DESIGN 8: each command's lines and exit codes, on the fake workshop."""
import io

import pytest

import fake_workshop as fw
from workshop import __main__ as cli
from workshop import states


@pytest.fixture
def root(tmp_path):
    return fw.make_workshop(tmp_path / "copy")


def run(root, *argv, stdin=""):
    import sys
    old = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        code = cli.main(list(argv), root=root)
    finally:
        sys.stdin = old
    return code


def lines(capsys):
    return capsys.readouterr().out.splitlines()


# ---- start and finish (8.3) ----------------------------------------------------------------------------------------

def test_start_0_leaves_no_harness_code(root, capsys):
    fw.put_state(root, "2-done")
    assert run(root, "start", "0") == 0
    assert lines(capsys) == [
        cli.APPLIED.format(written=0, removed=7),
        cli.START_DONE_ZERO,
        cli.HINT_BUILD.format(prompt="workshop/prompts/p0.md", n=0)]
    assert sorted(fw.tree_of(root)) == ["SPEC.md", "tests/data/test_fix.py", "tests/step0/test_a.py"]


def test_start_n_puts_the_copy_at_the_start_of_step_n(root, capsys):
    assert run(root, "start", "1") == 0
    out = lines(capsys)
    assert out[1:] == [cli.START_DONE.format(n=1, prev=0), cli.HINT_BUILD.format(prompt="workshop/prompts/p1.md", n=1)]
    assert fw.tree_of(root) == {p: b for p, b in states.load(root).state_map("1-build").items()}


def test_finish_n_puts_the_copy_at_the_end_of_step_n(root, capsys):
    assert run(root, "start", "2") == 0
    capsys.readouterr()
    assert run(root, "finish", "1") == 0
    assert lines(capsys)[1:] == [cli.FINISH_DONE.format(n=1), cli.HINT_NEXT.format(m=2)]
    assert states.where(states.load(root), fw.tree_of(root))["exact"] == "1-done"


def test_finish_the_last_step_says_this_is_the_finished_harness(root, capsys):
    run(root, "start", "1")
    capsys.readouterr()
    assert run(root, "finish", "2") == 0
    assert lines(capsys)[-1] == cli.HINT_FINISHED


def test_when_nothing_changes_it_says_so(root, capsys):
    run(root, "finish", "2")
    capsys.readouterr()
    assert run(root, "finish", "2") == 0
    assert lines(capsys)[0] == cli.ALREADY


def test_start_sets_the_person_s_edit_aside_and_says_so(root, capsys):
    run(root, "finish", "2")
    capsys.readouterr()
    (root / "harness" / "a.py").write_text("A = 'mine'\n", encoding="utf-8")
    (root / "my" / "brief").mkdir(parents=True)
    (root / "my" / "brief" / "domain_brief.md").write_text("my plan", encoding="utf-8")
    assert run(root, "start", "2") == 0
    out = lines(capsys)
    assert out[0].startswith("Set aside your version of harness/a.py in my/var/set-aside/")
    copy = root / out[0].split(" in ")[1] 
    assert copy.read_text(encoding="utf-8") == "A = 'mine'\n"
    assert (root / "my" / "brief" / "domain_brief.md").read_text(encoding="utf-8") == "my plan"


def test_a_folder_in_the_way_changes_nothing_and_exits_1(root, capsys):
    run(root, "start", "1")
    capsys.readouterr()
    (root / "harness" / "c.py").mkdir()
    before = fw.tree_of(root)
    assert run(root, "finish", "2") == 1
    assert lines(capsys) == [cli.IN_THE_WAY.format(path="harness/c.py")]
    assert fw.tree_of(root) == before


@pytest.mark.parametrize("argv", [("start", "6"), ("finish", "x"), ("start", "-1")])
def test_a_bad_step_is_a_usage_error(root, capsys, argv):
    with pytest.raises(SystemExit) as stop:
        run(root, *argv)
    assert stop.value.code == 2
    assert cli.BAD_STEP in capsys.readouterr().err


def test_an_unknown_state_name_is_a_usage_error(root):
    with pytest.raises(SystemExit) as stop:
        run(root, "check", "9-done")
    assert stop.value.code == 2


# ---- next (8.4) ------------------------------------------------------------------------------------------------------

def test_next_installs_only_the_next_step_s_contract_tests_and_given_files(root, capsys):
    run(root, "finish", "1")
    capsys.readouterr()
    (root / "harness" / "a.py").write_text("A = 'my own code'\n", encoding="utf-8")
    before_code = {p: b for p, b in fw.tree_of(root).items() if p.startswith("harness/")}
    assert run(root, "next") == 0
    out = lines(capsys)
    installed = ["harness/s.py", "tests/step2/test_c.py"]            # step 2's tests and start file, nothing else
    assert out == [cli.NEXT_DONE.format(n=2, count=len(installed)), cli.HINT_BUILD.format(prompt="workshop/prompts/p2.md", n=2)]
    tree = fw.tree_of(root)
    assert tree["SPEC.md"] == fw.SPEC.encode() and "tests/step2/test_c.py" in tree
    assert tree["harness/s.py"] == fw.START_S.encode()                               # the start file of step 2
    assert {p: b for p, b in tree.items() if p.startswith("harness/") and p != "harness/s.py"} == before_code
    assert not (root / "my").exists()                 # the person's own harness/a.py is not a contract file


def test_next_sets_aside_a_start_file_the_person_already_wrote(root, capsys):
    run(root, "finish", "1")
    capsys.readouterr()
    (root / "harness" / "s.py").write_text("S = 'mine'\n", encoding="utf-8")
    assert run(root, "next") == 0
    out = lines(capsys)
    assert out[0].startswith("Set aside your version of harness/s.py in my/var/set-aside/")
    assert (root / "harness" / "s.py").read_text(encoding="utf-8") == fw.START_S


def test_next_refuses_a_copy_whose_contract_was_edited(root, capsys):
    run(root, "finish", "1")
    capsys.readouterr()
    (root / "SPEC.md").write_text(fw.SPEC + "\nmy note\n", encoding="utf-8")
    assert run(root, "next") == 1
    assert lines(capsys)[0].startswith("next needs a copy whose contract is that of a step.")


def test_next_needs_the_previous_step_to_be_built(root, capsys):
    run(root, "start", "1")
    capsys.readouterr()
    assert run(root, "next") == 1
    assert lines(capsys) == [cli.NEXT_UNFINISHED.format(n=1, paths="harness/b.py", prompt="workshop/prompts/p1.md")]


def test_next_after_the_last_step(root, capsys):
    run(root, "finish", "2")
    capsys.readouterr()
    assert run(root, "next") == 1 and lines(capsys) == [cli.NEXT_LAST]


def test_next_names_the_closest_step_when_nothing_matches(root, capsys):
    run(root, "finish", "1")
    capsys.readouterr()
    for name in ("SPEC.md", "tests/step0/test_a.py", "tests/step1/test_b.py"):
        (root / name).write_text("changed", encoding="utf-8")
    (root / "harness" / "note.md").write_text("changed", encoding="utf-8")
    assert run(root, "next") == 1
    assert lines(capsys) == [cli.NEXT_NO_MATCH.format(
        n=1, paths="SPEC.md, harness/note.md, tests/step0/test_a.py, tests/step1/test_b.py")]


# ---- status (8.2) ----------------------------------------------------------------------------------------------------

def test_status_quick_at_a_state(root, capsys):
    run(root, "start", "1")
    capsys.readouterr()
    assert run(root, "status", "--quick") == 0
    assert lines(capsys) == [cli.STATUS_EXACT.format(label="the start of step 1"), cli.STATUS_TESTS_SKIPPED,
                             cli.HINT_BUILD.format(prompt="workshop/prompts/p1.md", n=1)]


def test_status_quick_at_an_end_state_points_to_next(root, capsys):
    run(root, "finish", "0")
    capsys.readouterr()
    run(root, "status", "--quick")
    assert lines(capsys)[-1] == cli.HINT_NEXT.format(m=1)


def test_status_quick_with_own_code_gives_both_hints(root, capsys):
    run(root, "finish", "1")
    capsys.readouterr()
    (root / "harness" / "b.py").write_text("B = 'mine'\n", encoding="utf-8")
    run(root, "status", "--quick")
    assert lines(capsys) == [
        cli.STATUS_CONTRACT.format(n=1), cli.STATUS_OWN_CODE.format(count=1, n=1), cli.STATUS_TESTS_SKIPPED,
        cli.HINT_BUILD.format(prompt="workshop/prompts/p1.md", n=1), cli.HINT_WHEN_GREEN.format(n=1)]


def test_status_with_no_match(root, capsys):
    run(root, "finish", "1")
    capsys.readouterr()
    (root / "SPEC.md").write_text("changed", encoding="utf-8")
    assert run(root, "status", "--quick") == 0
    out = lines(capsys)
    assert out[0] == cli.STATUS_NO_MATCH.format(n=1, paths="SPEC.md") and out[-1] == cli.HINT_NO_MATCH


def test_status_runs_the_tests_of_each_step_folder_that_is_there(root, capsys):
    run(root, "finish", "1")
    capsys.readouterr()
    assert run(root, "status") == 0
    out = lines(capsys)
    assert out[0] == cli.STATUS_EXACT.format(label="the end of step 1") and out[1] == cli.STATUS_TESTS_INTRO
    assert out[2].startswith("  step 0: pass (") and out[3].startswith("  step 1: pass (") and len(out) == 5
    assert out[4] == cli.HINT_NEXT.format(m=2)


def test_status_reports_a_failing_step_with_the_last_pytest_line(root, capsys):
    run(root, "start", "1")
    capsys.readouterr()
    run(root, "status")
    out = lines(capsys)
    assert out[2].startswith("  step 0: pass") and out[3].startswith("  step 1: FAIL: ")
    assert out[-1] == cli.HINT_BUILD.format(prompt="workshop/prompts/p1.md", n=1)


# ---- leave (8.5) -----------------------------------------------------------------------------------------------------

def test_leave_removes_only_the_workshop_folder_after_yes(root, capsys):
    run(root, "finish", "2")
    capsys.readouterr()
    assert run(root, "leave", stdin="  YES \n") == 0
    assert lines(capsys) == [cli.LEAVE_STATE.format(label="the end of step 2, the finished harness"), cli.LEAVE_ASK,
                             cli.LEAVE_DONE]
    assert not (root / "workshop").exists()
    assert (root / "harness" / "a.py").is_file() and (root / "tests").is_dir() and not (root / "my").exists()


@pytest.mark.parametrize("answer", ["no\n", "\n", "yes please\n", ""])
def test_leave_keeps_everything_for_any_other_answer_and_at_the_end_of_input(root, capsys, answer):
    run(root, "start", "1")
    capsys.readouterr()
    assert run(root, "leave", stdin=answer) == 0
    assert lines(capsys) == [cli.LEAVE_STATE.format(label="the start of step 1"), cli.LEAVE_ASK, cli.LEAVE_KEPT]
    assert (root / "workshop" / "manifest.json").is_file()


def test_leave_says_where_a_personal_copy_stands(root, capsys):
    run(root, "finish", "1")
    capsys.readouterr()
    (root / "harness" / "b.py").write_text("B = 'mine'\n", encoding="utf-8")
    run(root, "leave", stdin="no\n")
    assert lines(capsys)[0] == cli.LEAVE_STATE.format(label="the contract of step 1 with your own code")


# ---- the data (8) ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("damage", ["manifest", "finished", "absent", "json"])
def test_missing_or_broken_data_is_named_on_standard_error(root, capsys, damage):
    base = root / "workshop"
    if damage == "manifest":
        (base / "manifest.json").unlink()
    elif damage == "finished":
        import shutil
        shutil.rmtree(base / "states" / "finished")
    elif damage == "absent":
        (base / "states" / "0-done" / "absent.json").unlink()
    else:
        (base / "manifest.json").write_text("{not json", encoding="utf-8")
    assert run(root, "status", "--quick") == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err.startswith("The workshop data is incomplete: ")
    assert captured.err.strip().endswith("Run: python -m workshop check")
