"""SPEC 6.3: `candidates(conn)`, the module folders that are not registered (or whose files changed)."""
import pytest

import step3_helpers as s3
from step3_helpers import h


def test_no_modules_folder_gives_no_candidates(adopt, conn, modules_dir):
    assert not modules_dir.exists()
    assert adopt.candidates(conn) == []


def test_an_empty_modules_folder_gives_no_candidates(adopt, conn, modules_dir):
    modules_dir.mkdir()
    assert adopt.candidates(conn) == []


def test_unregistered_folders_are_candidates_sorted_by_name(adopt, conn, modules_dir):
    for name in ("zeta", "alpha", "monthly_surplus", "beta"):
        (modules_dir / name).mkdir(parents=True)
    assert adopt.candidates(conn) == ["alpha", "beta", "monthly_surplus", "zeta"]


def test_a_folder_need_not_hold_anything_to_be_a_candidate(adopt, conn, modules_dir):
    (modules_dir / "empty").mkdir(parents=True)
    h.write_files(modules_dir / "partial", {"module.py": "x = 1\n"})
    assert adopt.candidates(conn) == ["empty", "partial"]


@pytest.mark.parametrize("name", ["_build", "_anything", ".hidden", ".git"])
def test_folders_that_start_with_an_underscore_or_a_dot_are_not_candidates(adopt, conn, modules_dir, name):
    (modules_dir / name / "inner").mkdir(parents=True)
    (modules_dir / "real").mkdir()
    assert adopt.candidates(conn) == ["real"]


def test_files_in_the_modules_folder_are_ignored(adopt, conn, modules_dir):
    modules_dir.mkdir()
    (modules_dir / "notes.txt").write_text("x", encoding="utf-8")
    (modules_dir / "folder").mkdir()
    assert adopt.candidates(conn) == ["folder"]


def test_only_folders_directly_in_the_modules_folder_count(adopt, conn, modules_dir):
    (modules_dir / "outer" / "inner").mkdir(parents=True)
    assert adopt.candidates(conn) == ["outer"]


def test_a_registered_module_with_unchanged_files_is_not_a_candidate(adopt, conn, modules_dir):
    h.install_surplus(conn, "s1")
    (modules_dir / "other").mkdir()
    assert adopt.candidates(conn) == ["other"]


def test_a_registered_module_whose_files_changed_is_a_candidate(adopt, conn, modules_dir):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    assert adopt.candidates(conn) == ["monthly_surplus"]


def test_a_registered_module_that_lost_a_file_is_a_candidate(adopt, conn, modules_dir):
    h.install_surplus(conn, "s1")
    (modules_dir / "monthly_surplus" / "tests.py").unlink()
    assert adopt.candidates(conn) == ["monthly_surplus"]


def test_a_registered_module_without_its_folder_is_not_a_candidate(adopt, conn, modules_dir):
    import shutil
    h.install_surplus(conn, "s1")
    shutil.rmtree(modules_dir / "monthly_surplus")
    assert adopt.candidates(conn) == []


def test_the_modules_folder_is_read_at_the_time_of_the_call(adopt, conn, monkeypatch, tmp_path):
    (tmp_path / "modules" / "here").mkdir(parents=True)
    (tmp_path / "elsewhere" / "there").mkdir(parents=True)
    assert adopt.candidates(conn) == ["here"]
    monkeypatch.setenv("HARNESS_MODULES_DIR", str(tmp_path / "elsewhere"))
    assert adopt.candidates(conn) == ["there"]


def test_candidates_changes_nothing(adopt, conn, modules_dir):
    s3.surplus_folder(modules_dir)
    before = sum(len(conn.execute(f"SELECT * FROM {t}").fetchall()) for t in ("events", "test_runs", "modules"))
    adopt.candidates(conn)
    after = sum(len(conn.execute(f"SELECT * FROM {t}").fetchall()) for t in ("events", "test_runs", "modules"))
    assert before == after
