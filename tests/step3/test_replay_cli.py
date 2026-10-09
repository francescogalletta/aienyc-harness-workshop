"""SPEC 6.7: `python -m harness replay EXAMPLE [SCENARIO] [--keep]`, run as a program in a folder with `examples/`."""
from pathlib import Path

import pytest

import step3_helpers as s3
from step3_helpers import REPLAY_DONE, UNKNOWN_EXAMPLE, ask_script, h, run_in

SURPLUS_RUN = '{"income": "5000", "spending": "3000"}'
PASSING = [
    "Scenario upfront (ask)",
    f'  PASS  ran monthly_surplus with {{"income": "5000"}} (seen: run 1: {SURPLUS_RUN})',
    "  PASS  shows 2,000 (seen: in reply 1 of 1)",
    "  PASS  at most 0 replies withheld (seen: 0 withheld)",
    "  PASS  at most 0 corrections (seen: 0 corrections)",
]


@pytest.fixture
def replay_cli(tmp_path, write_script):
    """Run `replay` in the test's folder (where `examples/` is) with the given scripted model."""
    def run(*args, script=None, typed_text=""):
        write_script(ask_script() if script is None else script)
        return run_in(tmp_path, ["replay", *args], typed_text)
    return run


def lines(result):
    return result.stdout.splitlines()


def done(passed, total):
    return REPLAY_DONE.format(passed=passed, total=total)


# ---- the printed lines and the exit code ----------------------------------------------------------------------------

def test_a_passing_scenario_prints_its_checks_and_the_total(example, replay_cli):
    example()
    result = replay_cli("savings")
    assert lines(result) == [*PASSING, done(1, 1)] and result.returncode == 0 and result.stderr == ""


def test_the_marks_are_two_spaces_the_word_and_two_spaces(example, replay_cli):
    example(scenarios={"upfront": s3.ask_scenario(expect={"shown": ["2,000", "9,999"]})})
    result = replay_cli("savings")
    assert "  PASS  shows 2,000 (seen: in reply 1 of 1)" in lines(result)
    assert "  FAIL  shows 9,999 (seen: in none of 1 replies)" in lines(result)


def test_a_failing_check_gives_exit_code_1_and_counts_the_scenario_as_failed(example, replay_cli):
    example(scenarios={"upfront": s3.ask_scenario(expect={"shown": ["9,999"]})})
    result = replay_cli("savings")
    assert lines(result) == ["Scenario upfront (ask)", "  FAIL  shows 9,999 (seen: in none of 1 replies)", done(0, 1)]
    assert result.returncode == 1


def test_an_error_replaces_the_checks(example, replay_cli):
    example()
    result = replay_cli("savings", script=[])
    [header, error, last] = lines(result)
    assert header == "Scenario upfront (ask)" and error.startswith("  ERROR  ScriptExhausted: ")
    assert last == done(0, 1) and result.returncode == 1


def test_a_module_that_is_not_adopted_is_an_error_line(example, replay_cli):
    example(modules={"monthly_surplus": {**h.surplus_files("s1"), "module.py": h.WRONG_SURPLUS_PY},
                     "months_to_goal": h.months_files("s3")})
    result = replay_cli("savings")
    assert lines(result) == ["Scenario upfront (ask)", f"  ERROR  monthly_surplus was not adopted: {s3.REASON_TESTS}",
                             done(0, 1)]
    assert result.returncode == 1


def test_the_scenarios_run_in_file_name_order_and_each_starts_the_script_again(example, replay_cli):
    example(scenarios={"b_second": s3.ask_scenario("b_second"), "a_first": s3.ask_scenario("a_first"),
                       "c_third": s3.ask_scenario("c_third")})
    result = replay_cli("savings")
    assert [line for line in lines(result) if line.startswith("Scenario ")] == [
        "Scenario a_first (ask)", "Scenario b_second (ask)", "Scenario c_third (ask)"]
    assert lines(result)[-1] == done(3, 3) and not any("FAIL" in line or "ERROR" in line for line in lines(result))
    assert result.returncode == 0


def test_one_failed_scenario_among_others_gives_exit_code_1(example, replay_cli):
    example(scenarios={"a_first": s3.ask_scenario("a_first"),
                       "b_second": s3.ask_scenario("b_second", expect={"shown": ["9,999"]})})
    result = replay_cli("savings")
    assert lines(result)[-1] == done(1, 2) and result.returncode == 1
    assert lines(result)[0] == "Scenario a_first (ask)" and "Scenario b_second (ask)" in lines(result)


def test_the_scenario_argument_runs_that_one_only(example, replay_cli):
    example(scenarios={"a_first": s3.ask_scenario("a_first"), "b_second": s3.ask_scenario("b_second")})
    result = replay_cli("savings", "b_second")
    assert [line for line in lines(result) if line.startswith("Scenario ")] == ["Scenario b_second (ask)"]
    assert lines(result)[-1] == done(1, 1)


def test_a_build_scenario_is_run_as_a_build(example, replay_cli):
    example(scenarios={"rebuild_one": s3.build_scenario("rebuild_one")})
    result = replay_cli("savings", script=h.surplus_script())
    assert lines(result) == ["Scenario rebuild_one (build)", f"  PASS  step {h.label('s1')} built (seen: built)",
                             f"  PASS  step {h.label('s3')} kept (seen: kept)", done(1, 1)]
    assert result.returncode == 0


def test_only_the_lines_of_the_report_are_printed(example, replay_cli):
    example()
    result = replay_cli("savings")
    assert all(line.startswith(("Scenario ", "  PASS  ", "  FAIL  ", "  ERROR  ")) or line == done(1, 1)
               for line in lines(result))


def test_the_database_of_the_caller_is_not_touched(example, replay_cli, tmp_path):
    example()
    replay_cli("savings")
    assert not (tmp_path / "var" / "harness.db").exists()


def test_the_brief_of_the_example_is_the_one_used(example, replay_cli, tmp_path):
    example()
    assert not (tmp_path / "brief").exists()                                  # the configured brief folder is empty
    assert replay_cli("savings").returncode == 0


# ---- --keep -------------------------------------------------------------------------------------------------------------

def test_keep_prints_the_folder_and_how_to_open_it(example, replay_cli, tmp_path):
    example()
    result = replay_cli("savings", "--keep")
    assert result.returncode == 0
    out = lines(result)
    assert out[:5] == PASSING[:5] and out[-1] == done(1, 1)
    kept, opened = out[5], out[6]
    assert kept.startswith("  kept: ")
    folder = kept[len("  kept: "):]
    assert Path(folder).name.startswith("savings-upfront-") and (tmp_path / folder).is_dir()
    assert opened == (f"  open it with: HARNESS_DB={folder}/harness.db HARNESS_BRIEF_DIR={folder}/brief "
                      f"HARNESS_MODULES_DIR={folder}/modules python -m harness work")
    assert len(out) == 8


def test_the_kept_folder_holds_the_database_the_brief_and_the_modules(example, replay_cli, tmp_path):
    example()
    folder = tmp_path / lines(replay_cli("savings", "--keep"))[5][len("  kept: "):]
    assert sorted(p.name for p in folder.iterdir()) == ["brief", "harness.db", "modules"]
    kinds = [e["kind"] for e in s3.stored_events(folder / "harness.db")]
    assert kinds[0] == "replay.scenario" and kinds[-1] == "replay.checked"


def test_keep_after_the_scenario_name_works_too(example, replay_cli):
    example(scenarios={"a_first": s3.ask_scenario("a_first"), "b_second": s3.ask_scenario("b_second")})
    result = replay_cli("savings", "a_first", "--keep")
    assert result.returncode == 0 and sum(line.startswith("  kept: ") for line in lines(result)) == 1


def test_keep_before_the_example_works_too(example, replay_cli):
    example()
    result = replay_cli("--keep", "savings")
    assert result.returncode == 0 and sum(line.startswith("  kept: ") for line in lines(result)) == 1


def test_keep_prints_a_folder_for_each_scenario_after_its_checks(example, replay_cli):
    example(scenarios={"a_first": s3.ask_scenario("a_first"), "b_second": s3.ask_scenario("b_second")})
    out = lines(replay_cli("savings", "--keep"))
    assert [line.split(" ")[0] if line.startswith("Scenario") else line.strip().split(" ")[0] for line in out].count("kept:") == 2
    first, second = out.index("Scenario a_first (ask)"), out.index("Scenario b_second (ask)")
    assert out[first + 5].startswith("  kept: ") and out[first + 6].startswith("  open it with: ")
    assert out[second + 5].startswith("  kept: ") and out[-1] == done(2, 2)
    assert out[first + 5] != out[second + 5]


def test_keep_prints_the_folder_after_an_error_too(example, replay_cli):
    example()
    out = lines(replay_cli("savings", "--keep", script=[]))
    assert out[1].startswith("  ERROR  ") and out[2].startswith("  kept: ") and out[3].startswith("  open it with: ")
    assert out[-1] == done(0, 1)


def test_without_keep_nothing_stays(example, replay_cli, tmp_path):
    example()
    result = replay_cli("savings")
    assert "kept:" not in result.stdout and "open it with" not in result.stdout
    assert not (tmp_path / "var" / "replay").exists() or list((tmp_path / "var" / "replay").iterdir()) == []


# ---- what is refused ----------------------------------------------------------------------------------------------------

def test_an_unknown_example(example, replay_cli):
    example()
    result = replay_cli("nope")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.strip() == UNKNOWN_EXAMPLE.format(name="nope", names="savings")


def test_an_unknown_example_is_refused_before_any_scenario_runs(example, replay_cli, tmp_path):
    example()
    replay_cli("nope")
    assert not (tmp_path / "var" / "replay").exists()


def test_a_brief_that_is_still_a_draft(example, replay_cli, save_confirmed_brief):
    example(status="draft")
    save_confirmed_brief()                                                    # the configured brief is fine; the example's is not
    result = replay_cli("savings")
    assert result.returncode == 1 and result.stdout == "" and result.stderr.strip() == h.DRAFT_BRIEF


def test_an_example_without_a_brief(example, replay_cli):
    example(with_brief=False)
    result = replay_cli("savings")
    assert result.returncode == 1 and result.stdout == "" and result.stderr.strip() == h.NO_BRIEF


def test_a_missing_scenario_names_the_ones_there_are(example, replay_cli, tmp_path):
    example(scenarios={"a_first": s3.ask_scenario("a_first"), "b_second": s3.ask_scenario("b_second")})
    result = replay_cli("savings", "nope")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.strip().startswith("There is no scenario 'nope' in ")
    assert "scenarios" in result.stderr.splitlines()[0]
    assert result.stderr.strip().endswith("The scenarios are: a_first, b_second.")


def test_an_example_with_no_scenarios(example, replay_cli):
    example(scenarios={})
    result = replay_cli("savings")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.strip().startswith("There are no scenarios in ") and result.stderr.strip().endswith("scenarios.")


def test_every_problem_of_the_scenarios_is_printed_one_per_line_before_any_runs(example, replay_cli, tmp_path):
    example(scenarios={"a_first": s3.ask_scenario("a_first", lines=[]),
                       "b_second": "{ not json",
                       "c_third": s3.ask_scenario("c_third", today="soon")})
    result = replay_cli("savings")
    problems = result.stderr.splitlines()
    assert result.returncode == 1 and result.stdout == ""
    assert problems[0] == "a_first.json: lines must be a non-empty list of non-empty strings"
    assert problems[1].startswith("b_second.json: not valid JSON: ")
    assert problems[2] == "c_third.json: today must be a date written YYYY-MM-DD" and len(problems) == 3
    assert not (tmp_path / "var" / "replay").exists()


def test_the_scenarios_are_checked_against_the_brief_of_the_example(example, replay_cli):
    example(scenarios={"upfront": s3.ask_scenario(without=["ghost"])})
    result = replay_cli("savings")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.splitlines() == ["upfront.json: without: 'ghost' is not a calculation step of the brief"]


def test_a_problem_in_one_scenario_stops_the_run_of_the_good_ones(example, replay_cli):
    example(scenarios={"a_first": s3.ask_scenario("a_first"), "b_second": s3.ask_scenario("b_second", today="soon")})
    result = replay_cli("savings")
    assert result.returncode == 1 and result.stdout == ""
    assert result.stderr.splitlines() == ["b_second.json: today must be a date written YYYY-MM-DD"]
