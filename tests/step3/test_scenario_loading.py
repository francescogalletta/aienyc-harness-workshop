"""SPEC 6.4: `load_scenarios` reads the scenario files of an example and reports every problem at once."""
import json

import pytest

import step3_helpers as s3
from step3_helpers import NO_SCENARIO, NO_SCENARIOS, h


def load(replay, folder, brief=None, only=None):
    return replay.load_scenarios(folder, brief or h.make_brief(), only)


def messages(replay, folder, **options):
    with pytest.raises(ValueError) as caught:
        load(replay, folder, **options)
    return str(caught.value)


@pytest.fixture
def folder(tmp_path):
    return s3.make_example(tmp_path / "examples", "savings", scenarios={
        "b_second": s3.ask_scenario("b_second"), "a_first": s3.build_scenario("a_first"),
        "c_third": s3.ask_scenario("c_third", description="Another.")})


def test_scenarios_come_back_as_read_sorted_by_file_name(replay, folder):
    loaded = load(replay, folder)
    assert [s["name"] for s in loaded] == ["a_first", "b_second", "c_third"]
    assert loaded[0] == s3.build_scenario("a_first") and loaded[2] == s3.ask_scenario("c_third", description="Another.")


def test_the_folder_may_be_given_as_text(replay, folder):
    assert [s["name"] for s in load(replay, str(folder))] == ["a_first", "b_second", "c_third"]


def test_only_loads_the_one_scenario(replay, folder):
    assert load(replay, folder, only="b_second") == [s3.ask_scenario("b_second")]


def test_only_ignores_the_other_files_even_when_they_are_wrong(replay, folder):
    (folder / "scenarios" / "a_first.json").write_text("{ not json", encoding="utf-8")
    (folder / "scenarios" / "c_third.json").write_text("[]", encoding="utf-8")
    assert [s["name"] for s in load(replay, folder, only="b_second")] == ["b_second"]


def test_files_that_are_not_json_files_are_not_scenarios(replay, folder):
    (folder / "scenarios" / "notes.txt").write_text("not a scenario", encoding="utf-8")
    (folder / "scenarios" / "a_first.json.bak").write_text("{ not json", encoding="utf-8")
    (folder / "scenarios" / "README.md").write_text("# x", encoding="utf-8")
    assert [s["name"] for s in load(replay, folder)] == ["a_first", "b_second", "c_third"]


def test_a_missing_scenario_names_the_ones_there_are(replay, folder):
    assert messages(replay, folder, only="nope") == NO_SCENARIO.format(
        scenario="nope", folder=str(folder / "scenarios"), names="a_first, b_second, c_third")
    assert messages(replay, folder, only="nope").endswith("The scenarios are: a_first, b_second, c_third.")
    assert messages(replay, folder, only="nope").startswith("There is no scenario 'nope' in ")


def test_no_scenario_files_at_all(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", scenarios={})
    assert messages(replay, folder) == NO_SCENARIOS.format(folder=str(folder / "scenarios"))
    assert messages(replay, folder) == f"There are no scenarios in {folder / 'scenarios'}."


def test_only_non_json_files_is_no_scenario_files_either(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", scenarios={})
    (folder / "scenarios" / "notes.txt").write_text("x", encoding="utf-8")
    (folder / "scenarios" / "inner").mkdir()
    assert messages(replay, folder) == NO_SCENARIOS.format(folder=str(folder / "scenarios"))


def test_a_file_that_is_not_json(replay, folder):
    (folder / "scenarios" / "b_second.json").write_text("{ not json", encoding="utf-8")
    lines = messages(replay, folder).splitlines()
    assert len(lines) == 1 and lines[0].startswith("b_second.json: not valid JSON: ")
    assert len(lines[0]) > len("b_second.json: not valid JSON: ")                 # the reason follows


def test_an_empty_file_is_not_json(replay, folder):
    (folder / "scenarios" / "b_second.json").write_text("", encoding="utf-8")
    assert messages(replay, folder).startswith("b_second.json: not valid JSON: ")


def test_each_problem_of_the_validation_is_a_line_of_its_own(replay, folder):
    (folder / "scenarios" / "b_second.json").write_text("{}", encoding="utf-8")
    assert messages(replay, folder).splitlines() == [
        "b_second.json: missing: name", "b_second.json: missing: kind", "b_second.json: missing: lines",
        "b_second.json: missing: expect"]


def test_a_scenario_that_is_not_an_object(replay, folder):
    (folder / "scenarios" / "c_third.json").write_text("[1, 2]", encoding="utf-8")
    assert messages(replay, folder).splitlines() == ["c_third.json: the scenario must be an object"]


def test_the_name_must_be_the_file_name(replay, folder):
    (folder / "scenarios" / "c_third.json").write_text(s3.dump(s3.ask_scenario("other")), encoding="utf-8")
    assert messages(replay, folder).splitlines() == [
        "c_third.json: name must be the file name without .json, in snake_case: 'c_third'"]


def test_a_file_name_that_is_not_snake_case(replay, tmp_path):
    folder = s3.make_example(tmp_path / "examples", "savings", scenarios={"Bad-Name": s3.ask_scenario("Bad-Name")})
    assert messages(replay, folder).splitlines() == [
        "Bad-Name.json: name must be the file name without .json, in snake_case: 'Bad-Name'"]


def test_the_brief_is_the_one_given(replay, folder):
    scenario = s3.build_scenario("a_first", without=["ghost"], expect={"steps": {"s1": "built"}})
    (folder / "scenarios" / "a_first.json").write_text(s3.dump(scenario), encoding="utf-8")
    assert messages(replay, folder).splitlines() == ["a_first.json: without: 'ghost' is not a calculation step of the brief"]
    assert load(replay, folder, brief=h.make_brief(process=[{**h.make_brief()["process"][0], "id": "ghost"}]), only="b_second")


def test_every_problem_of_every_file_comes_back_in_one_error_in_file_name_order(replay, folder):
    (folder / "scenarios" / "c_third.json").write_text("{ not json", encoding="utf-8")
    (folder / "scenarios" / "a_first.json").write_text(s3.dump(s3.build_scenario("a_first", lines=[], kind="build")),
                                                      encoding="utf-8")
    (folder / "scenarios" / "b_second.json").write_text(s3.dump(s3.ask_scenario("b_second", today="soon", lines=[])),
                                                       encoding="utf-8")
    lines = messages(replay, folder).splitlines()
    assert lines[0] == "a_first.json: lines must be a non-empty list of non-empty strings"
    assert lines[1:3] == ["b_second.json: today must be a date written YYYY-MM-DD",
                          "b_second.json: lines must be a non-empty list of non-empty strings"]
    assert lines[3].startswith("c_third.json: not valid JSON: ") and len(lines) == 4


def test_only_checks_only_that_file(replay, folder):
    (folder / "scenarios" / "b_second.json").write_text("{}", encoding="utf-8")
    assert len(messages(replay, folder, only="b_second").splitlines()) == 4
    assert load(replay, folder, only="a_first")[0]["name"] == "a_first"


def test_every_scenario_is_returned_whole(replay, folder):
    extra = s3.ask_scenario("b_second", today="2031-07-22", description="x")
    (folder / "scenarios" / "b_second.json").write_text(json.dumps(extra), encoding="utf-8")
    [loaded] = load(replay, folder, only="b_second")
    assert loaded == extra and list(loaded) == list(extra)
