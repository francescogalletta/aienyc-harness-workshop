"""SPEC 9.6: when the verifier runs: `needs_check`."""
import pytest

import step5_helpers as s5
from step5_helpers import h, put_import

NO_FIGURES_IN_THE_BRIEF = {"particulars": [{"what": "I rent a flat", "handling": "Count it as spending"}],
                           "inputs": [{"name": "Monthly income", "description": "What comes in each month"}]}


def bare_brief(**changes):
    return h.make_brief(**{**NO_FIGURES_IN_THE_BRIEF, **changes})


@pytest.mark.parametrize("message", ["I spend about 5k a month"])
def test_a_message_with_a_figure_is_checked_when_the_brief_has_a_figure(verifier, conn, brief, message):
    assert verifier.needs_check(conn, brief, message) is True






















def test_the_files_cleared_leave_nothing_to_check_against(adapter, verifier, conn, tmp_path):
    s5.add_text(adapter, conn, tmp_path, "bank.csv", s5.simple())
    assert verifier.needs_check(conn, bare_brief(), s5.MESSAGE) is True
    adapter.clear_data(conn, session_id="C")
    assert verifier.needs_check(conn, bare_brief(), s5.MESSAGE) is False


