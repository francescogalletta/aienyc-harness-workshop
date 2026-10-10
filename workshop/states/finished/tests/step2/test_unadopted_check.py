"""SPEC 5.13: `build` and `ask` refuse to run while module folders that are not registered sit in the modules folder."""
import pytest

import step2_adopt_helpers as s3
import step2_helpers as h
from step2_adopt_helpers import (UNADOPTED, typed)


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


# ---- ask ---------------------------------------------------------------------------------------------------------------

def test_ask_refuses_while_a_folder_is_not_registered(brief_saved, modules_dir, write_script):
    s3.surplus_folder(modules_dir)
    write_script([h.say_text("Hello.")])
    result = h.run_cli(["ask", "Hi"], typed("/quit"))
    assert result.returncode == 1
    assert result.stderr.strip() == refusal("monthly_surplus")
    assert result.stdout == ""                                                     # not even the greeting


# ---- the way out: adopt -----------------------------------------------------------------------------------------------------
