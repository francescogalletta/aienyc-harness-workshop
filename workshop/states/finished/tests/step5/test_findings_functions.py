"""SPEC 9.5: `figure`, `disagree`, `plain`, `same_value`, `brief_texts` and the constants."""
from decimal import Decimal

import pytest

import step5_helpers as s5
from step5_helpers import h


def number(value, *, written=None, percent=False):
    return {"written": written or str(value), "date": False, "value": Decimal(str(value)), "percent": percent}


def date(text):
    return {"written": text, "date": True, "value": text, "percent": False}


# ---- the constants ------------------------------------------------------------------------------------------------------





# ---- figure -------------------------------------------------------------------------------------------------------------





























# ---- disagree -----------------------------------------------------------------------------------------------------------

def test_about_5k_against_5080_does_not_disagree_and_against_4132_does(findings):
    claim = findings.figure("I spend about 5k a month")
    assert findings.disagree(claim, findings.figure("5080")) is False
    assert findings.disagree(claim, findings.figure("4132.31")) is True






















# ---- plain --------------------------------------------------------------------------------------------------------------







# ---- same_value ---------------------------------------------------------------------------------------------------------







# ---- brief_texts --------------------------------------------------------------------------------------------------------









