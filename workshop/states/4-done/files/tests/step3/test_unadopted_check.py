"""SPEC 6.6: `build` and `ask` refuse to run while module folders that are not registered sit in the modules folder."""
import pytest

import step3_helpers as s3
from step3_helpers import UNADOPTED, h, typed


@pytest.fixture
def brief_saved(save_confirmed_brief):
    return save_confirmed_brief()


def refusal(names):
    return UNADOPTED.format(names=names)


# ---- build ---------------------------------------------------------------------------------------------------

def test_build_refuses_while_a_folder_is_not_registered(brief_saved, modules_dir, write_script):
    s3.surplus_folder(modules_dir)
    write_script(h.surplus_script())
    result = h.run_cli(["build"], typed(*h.built()))
    assert result.returncode == 1
    assert result.stderr.strip() == refusal("monthly_surplus") == (
        "The modules folder has modules that are not registered here: monthly_surplus. "
        "Adopt them first with: python -m harness adopt")
    assert result.stdout == ""                                                     # before anything else
    assert "Traceback" not in result.stderr


def test_the_names_are_sorted_and_joined_by_a_comma_and_a_space(brief_saved, modules_dir, write_script):
    for name in ("zeta", "monthly_surplus", "alpha"):
        (modules_dir / name).mkdir(parents=True)
    write_script([])
    result = h.run_cli(["build"])
    assert result.returncode == 1 and result.stderr.strip() == refusal("alpha, monthly_surplus, zeta")


def test_nothing_is_built_and_no_model_is_called(brief_saved, modules_dir, write_script, conn):
    s3.surplus_folder(modules_dir)
    write_script([])                                                               # a model call would fail loudly
    h.run_cli(["build"])
    assert h.rows(conn, "modules") == [] and [e for e in h.events(conn) if e[0].startswith("calc.")] == []


def test_registered_modules_with_changed_files_are_not_counted(brief_saved, conn, modules_dir, write_script):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    write_script(h.surplus_script())
    result = h.run_cli(["build"], typed(*h.built()))
    assert result.returncode == 0, result.stderr
    assert "not registered here" not in result.stderr
    assert result.stdout.splitlines()[-3:] == ["s1 -> monthly_surplus (built)", "s3 -> months_to_goal (already built)",
                                               h.ALL_BUILT]


def test_only_the_unregistered_folders_are_named(brief_saved, conn, modules_dir, write_script):
    h.install_surplus(conn, "s1")
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    (modules_dir / "zeta").mkdir()
    write_script([])
    result = h.run_cli(["build"])
    assert result.returncode == 1 and result.stderr.strip() == refusal("zeta")


def test_staging_and_hidden_folders_and_plain_files_are_not_counted(brief_saved, conn, modules_dir, write_script):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")
    (modules_dir / "_build" / "left_over").mkdir(parents=True)
    (modules_dir / ".hidden").mkdir()
    (modules_dir / "readme.txt").write_text("x", encoding="utf-8")
    write_script([])
    result = h.run_cli(["build"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == h.ALL_BUILT


def test_rebuild_of_a_registered_module_does_not_look(brief_saved, conn, modules_dir, write_script):
    h.install_surplus(conn, "s1")
    (modules_dir / "stray").mkdir()
    write_script(h.surplus_script())
    result = h.run_cli(["build", "--rebuild", "monthly_surplus"], typed(*h.built()))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "s1 -> monthly_surplus (built)"
    assert "not registered here" not in result.stderr


def test_the_brief_is_loaded_first(save_confirmed_brief, modules_dir, write_script):
    save_confirmed_brief(status="draft")
    (modules_dir / "stray").mkdir(parents=True)
    write_script([])
    result = h.run_cli(["build"])
    assert result.returncode == 1 and h.DRAFT_BRIEF in result.stderr and "not registered here" not in result.stderr


def test_it_comes_before_the_news_that_the_brief_has_no_calculation_steps(save_confirmed_brief, modules_dir, write_script):
    save_confirmed_brief(h.make_brief(process=[h.make_brief()["process"][1]]))
    (modules_dir / "stray").mkdir(parents=True)
    write_script([])
    result = h.run_cli(["build"])
    assert result.returncode == 1 and result.stderr.strip() == refusal("stray") and result.stdout == ""


# ---- ask ---------------------------------------------------------------------------------------------------------------

def test_ask_refuses_while_a_folder_is_not_registered(brief_saved, modules_dir, write_script):
    s3.surplus_folder(modules_dir)
    write_script([h.say_text("Hello.")])
    result = h.run_cli(["ask", "Hi"], typed("/quit"))
    assert result.returncode == 1
    assert result.stderr.strip() == refusal("monthly_surplus")
    assert result.stdout == ""                                                     # not even the greeting


def test_ask_names_the_folders_before_it_says_that_no_module_is_built(brief_saved, modules_dir, write_script):
    s3.surplus_folder(modules_dir)
    s3.months_folder(modules_dir)
    write_script([])
    result = h.run_cli(["ask", "Hi"])
    assert result.returncode == 1 and result.stderr.strip() == refusal("monthly_surplus, months_to_goal")
    assert s3.NO_BUILT_MODULES not in result.stderr


def test_ask_does_not_count_a_registered_module_with_changed_files(brief_saved, conn, modules_dir, write_script):
    h.install_surplus(conn, "s1")
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    write_script([h.say_text("Hello.")])
    result = h.run_cli(["ask", "Hi"], typed("/quit"))
    assert result.returncode == 0, result.stderr


def test_ask_loads_the_brief_first(save_confirmed_brief, modules_dir, write_script):
    save_confirmed_brief(status="draft")
    (modules_dir / "stray").mkdir(parents=True)
    write_script([])
    result = h.run_cli(["ask", "Hi"])
    assert result.returncode == 1 and h.DRAFT_BRIEF in result.stderr and "not registered here" not in result.stderr


# ---- the way out: adopt -----------------------------------------------------------------------------------------------------

def test_after_adopting_build_and_ask_go_ahead(brief_saved, modules_dir, write_script):
    s3.surplus_folder(modules_dir)
    s3.months_folder(modules_dir)
    write_script([])
    assert h.run_cli(["build"]).returncode == 1
    adopted = h.run_cli(["adopt"], typed("yes"))
    assert adopted.returncode == 0, adopted.stdout
    built = h.run_cli(["build"])
    assert built.returncode == 0, built.stderr
    assert built.stdout.splitlines()[-3:] == ["s1 -> monthly_surplus (already built)",
                                              "s3 -> months_to_goal (already built)", h.ALL_BUILT]
    write_script([h.run_module(), h.say_text("monthly_surplus gives 2,000.")])
    asked = h.run_cli(["ask", "I", "earn", "5000", "and", "spend", "3000."], typed("/quit"))
    assert asked.returncode == 0, asked.stderr
    assert "monthly_surplus gives 2,000." in asked.stdout
