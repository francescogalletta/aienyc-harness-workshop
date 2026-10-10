"""SPEC 5.13: `candidates(conn)`, the module folders that are not registered (or whose files changed)."""

import step2_helpers as h



def test_unregistered_folders_are_candidates_sorted_by_name(adopt, conn, modules_dir):
    for name in ("zeta", "alpha", "monthly_surplus", "beta"):
        (modules_dir / name).mkdir(parents=True)
    assert adopt.candidates(conn) == ["alpha", "beta", "monthly_surplus", "zeta"]


def test_a_registered_module_whose_files_changed_is_a_candidate(adopt, conn, modules_dir):
    h.install_surplus(conn, "s1")
    h.install_months(conn, "s3")
    (modules_dir / "monthly_surplus" / "module.py").write_text("# edited\n" + h.SURPLUS_PY, encoding="utf-8")
    assert adopt.candidates(conn) == ["monthly_surplus"]
