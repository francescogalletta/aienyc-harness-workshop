"""SPEC 5.4 and ARCHITECTURE.md 12.4: the re-run engine. Which runs of the last answer a changed value reaches,
directly or through an earlier run's result, and running them again through the gate, with no model."""
import json
import shutil

import pytest

from harness.answers import rerun as engine
from harness.calc import gate
from harness.config import load_config
from harness.core import Session
from harness.model import ScriptedModel
from layer3_helpers import PROPOSED, SETTLE, item, small_plan

HEAD = "from decimal import Decimal\n\n\n"
TEST_HEAD = "from decimal import Decimal\nfrom module import calculate\n\n\n"


def _plan() -> dict:
    """c1 total -> c2 double, c1 -> c3 split -> c4 sum_up -> j1; inputs Unit count, Unit price, First."""
    plan = small_plan()
    step = {"method": "arithmetic", "cadence": "", "origin": PROPOSED}
    plan["inputs"] = [{"name": name, "description": name.lower(), "origin": PROPOSED}
                      for name in ("Unit count", "Unit price", "First")]
    plan["process"] = [
        {"id": "c1", "name": "Total", "kind": "calculation", "formula": "count x price",
         "needs": ["Unit count", "Unit price"], "produces": "total", **step},
        {"id": "c2", "name": "Double", "kind": "calculation", "formula": "total x 2", "needs": ["c1"],
         "produces": "double", **step},
        {"id": "c3", "name": "Split", "kind": "calculation", "formula": "first, then the rest in halves",
         "needs": ["c1", "First"], "produces": "three payments", **step},
        {"id": "c4", "name": "Sum", "kind": "calculation", "formula": "payments + extra", "needs": ["c3"],
         "produces": "a sum", **step},
        {"id": "j1", "name": "Is it enough?", "kind": "judgment", "method": "", "formula": "", "needs": ["c4"],
         "produces": "a decision", "cadence": "", "origin": PROPOSED}]
    plan["particulars"] = [{"what": "Amounts are in euros", "handling": "Say so", "step": "c1", "origin": PROPOSED}]
    plan["definition_of_done"] = [item("I know the sum")]
    return plan


def _module(name, step, inputs, output, code, test, examples):
    spec = {"name": name, "description": name, "step_id": step, "method": "arithmetic", "formula": name,
            "inputs": [{"name": key, "type": kind, "description": key} for key, kind in inputs],
            "output": {"type": output, "description": name}}
    golden = [{"inputs": given, "expected": expected, "working": "by hand", "checked_by": "second_pass"}
              for given, expected in examples]
    return {"spec.json": json.dumps(spec), "golden.json": json.dumps(golden), "module.py": HEAD + code,
            "tests.py": TEST_HEAD + test}


MODULES = {
    "total": _module(
        "total", "c1", [("unit_count", "integer"), ("unit_price", "number")], "number",
        "def calculate(unit_count, unit_price):\n    return unit_count * unit_price\n",
        "def test_it():\n    assert calculate(unit_count=2, unit_price=Decimal('3')) == Decimal('6')\n",
        [({"unit_count": "2", "unit_price": "3"}, "6"), ({"unit_count": "0", "unit_price": "5"}, "0"),
         ({"unit_count": "10", "unit_price": "2.5"}, "25")]),
    "double": _module(
        "double", "c2", [("total", "number")], "number", "def calculate(total):\n    return total * 2\n",
        "def test_it():\n    assert calculate(total=Decimal('4')) == Decimal('8')\n",
        [({"total": "1"}, "2"), ({"total": "0"}, "0"), ({"total": "250"}, "500")]),
    "split": _module(
        "split", "c3", [("total", "number"), ("first", "number")], "object",
        "def calculate(total, first):\n"
        "    if total < first:\n        raise ValueError('the total must be at least the first payment')\n"
        "    rest = (total - first) / 2\n"
        "    return {'first': first, 'rest': rest, 'last': total - first - rest}\n",
        "def test_it():\n    assert calculate(total=Decimal('10'), first=Decimal('2'))['rest'] == Decimal('4')\n",
        [({"total": "100", "first": "50"}, {"first": "50", "rest": "25", "last": "25"}),
         ({"total": "10", "first": "0"}, {"first": "0", "rest": "5", "last": "5"}),
         ({"total": "8", "first": "8"}, {"first": "8", "rest": "0", "last": "0"})]),
    "sum_up": _module(
        "sum_up", "c4", [("payments", "list"), ("extra", "object")], "number",
        "def calculate(payments, extra):\n"
        "    return sum(Decimal(each['amount']) for each in payments) + Decimal(extra['amount'])\n",
        "def test_it():\n    assert calculate(payments=[{'amount': '1'}], extra={'amount': '2'}) == Decimal('3')\n",
        [({"payments": [{"name": "p", "amount": "1"}], "extra": {"amount": "2"}}, "3"),
         ({"payments": [], "extra": {"amount": "0"}}, "0"),
         ({"payments": [{"name": "p", "amount": "1"}, {"name": "q", "amount": "4"}], "extra": {"amount": "5"}}, "10")]),
}


def _write(folder):
    (folder / "brief").mkdir(parents=True, exist_ok=True)
    (folder / "brief" / "domain_brief.json").write_text(json.dumps(_plan()), encoding="utf-8")
    for name, files in MODULES.items():
        (folder / "modules" / name).mkdir(parents=True, exist_ok=True)
        for file, text in files.items():
            (folder / "modules" / name / file).write_text(text, encoding="utf-8")


@pytest.fixture(scope="module")
def adopted(tmp_path_factory):
    folder = tmp_path_factory.mktemp("rerun")
    _write(folder)
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("HARNESS_LAYERS", "3")
        patch.setenv("HARNESS_DB", str(folder / "harness.db"))
        patch.setenv("HARNESS_BRIEF_DIR", str(folder / "brief"))
        patch.setenv("HARNESS_MODULES_DIR", str(folder / "modules"))
        patch.setenv("HARNESS_MODEL_PROVIDER", "scripted")
        session = Session(load_config(), model_factory=lambda: ScriptedModel([]))
        session.settle(SETTLE)
        session.close()
    return folder


class Work:
    """What `rerun` takes of a main-lane job: a connection, the conversation, the config, progress."""

    def __init__(self, session):
        self.conn, self.conversation, self.config = session.conn, session.conversation, session.config
        self.progressed = []

    def progress(self, text, step=None, what=None, thread=None):
        self.progressed.append({"text": text, "step": step, "what": what})

    def changed(self):
        pass


@pytest.fixture
def session(tmp_path, adopted):
    for name in ("brief", "modules"):
        shutil.copytree(adopted / name, tmp_path / name)
    shutil.copy(adopted / "harness.db", tmp_path / "harness.db")
    opened = Session(load_config(), model_factory=lambda: ScriptedModel([]))
    opened.settle(SETTLE)
    assert {row["name"] for row in opened.conn.execute("SELECT name FROM modules")} == set(MODULES)
    yield opened
    opened.close()


def run(session, module, inputs, assumptions=()):
    return gate.call(session.conn, module, inputs, assumptions=list(assumptions), expected="as worked out",
                     session_id=session.conversation)


def answer(session, *results):
    """Post an answer that used these runs: it becomes the last answer."""
    session.post("Here it is.", who="assistant", kind="text", data={"_runs": [each["run_id"] for each in results]})


def row(session, run_id):
    found = session.conn.execute("SELECT * FROM calc_runs WHERE id = ?", (int(str(run_id).lstrip("r")),)).fetchone()
    return {"module": found["module"], "inputs": json.loads(found["inputs"]), "output": json.loads(found["output"]),
            "assumptions": json.loads(found["assumptions"]), "expected": found["expected"]}


def chain(session, *, count="40", price="100", first="500"):
    """total -> split (fed the total) -> sum_up (fed the split's payments in a list, the total in an object)."""
    total = run(session, "total", {"unit_count": count, "unit_price": price})
    split = run(session, "split", {"total": total["output"], "first": first})
    parts = split["output"]
    payments = [{"name": name, "amount": parts[name]} for name in ("first", "rest", "last")]
    summed = run(session, "sum_up", {"payments": payments, "extra": {"amount": total["output"]}})
    return total, split, summed


def test_the_last_answer_and_the_values_it_took(session):
    earlier = run(session, "total", {"unit_count": "7", "unit_price": "100"})
    answer(session, earlier)
    low = run(session, "total", {"unit_count": "40", "unit_price": "100"})
    high = run(session, "total", {"unit_count": 60, "unit_price": "100"})
    again = run(session, "double", {"total": "4,000"})
    answer(session, high, low, again)
    assert engine.last_answer_runs(session.conn, session.conversation) == sorted(
        [low["run_id"], high["run_id"], again["run_id"]])
    assert engine.old_values(session.conn, session.conversation, "unit_count") == ["40", "60"]
    assert engine.old_values(session.conn, session.conversation, "unit_price") == ["100"]
    assert engine.old_values(session.conn, session.conversation, "nothing") == []


def test_a_change_runs_again_the_direct_run_and_every_run_fed_its_result_inside_lists_and_objects(session):
    total, split, summed = chain(session)
    answer(session, total, split, summed)
    work = Work(session)
    result = engine.rerun(work, key="unit_count", old="40", new="50", label="Unit count")
    assert result["failed"] == []
    assert list(result["replaced"]) == [f"r{each['run_id']}" for each in (total, split, summed)]
    new_total, new_split, new_sum = (row(session, result["replaced"][f"r{each['run_id']}"])
                                     for each in (total, split, summed))
    assert new_total["inputs"] == {"unit_count": "50", "unit_price": "100"} and new_total["output"] == "5000"
    assert new_split["inputs"] == {"total": "5000", "first": "500"}
    assert new_split["output"] == {"first": "500", "rest": "2250", "last": "2250"}
    assert new_sum["inputs"]["payments"] == [{"name": "first", "amount": "500"}, {"name": "rest", "amount": "2250"},
                                             {"name": "last", "amount": "2250"}]
    assert new_sum["inputs"]["extra"] == {"amount": "5000"} and new_sum["output"] == "10000"
    assert result["runs"] == sorted(int(each[1:]) for each in result["replaced"].values())
    assert [(each["step"], each["what"]) for each in work.progressed] == [("c1", "join"), ("c3", "join"),
                                                                         ("c4", "join")]
    assert "1" in work.progressed[0]["text"] and "3" in work.progressed[1]["text"]


def test_impact_is_the_same_walk_without_running_and_names_the_steps_further_down(session):
    total, split, summed = chain(session)
    unrelated = run(session, "double", {"total": "123"})
    answer(session, total, split, summed, unrelated)
    before = session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0]
    state = session.state()
    found = engine.impact(session.conn, state, key="unit_count", old="40")
    assert found == {"inputs": ["in:unit_count"], "runs": [f"r{each['run_id']}" for each in (total, split, summed)],
                     "steps": ["c1", "c3", "c4"], "downstream": ["c2", "j1"]}
    assert session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0] == before
    nobody = engine.impact(session.conn, state, key="unit_price", old="999")
    assert nobody == {"inputs": ["in:unit_price"], "runs": [], "steps": [], "downstream": ["c1", "c2", "c3", "c4", "j1"]}


def test_numbers_written_as_text_in_another_form_are_matched_and_a_json_number_keeps_its_type(session):
    total = run(session, "total", {"unit_count": 40, "unit_price": 100})
    doubled = run(session, "double", {"total": "4,000.00"})
    answer(session, total, doubled)
    result = engine.rerun(Work(session), key="unit_count", old="40", new="45", label="Unit count")
    new_total = row(session, result["replaced"][f"r{total['run_id']}"])
    assert new_total["inputs"] == {"unit_count": 45, "unit_price": 100}
    assert row(session, result["replaced"][f"r{doubled['run_id']}"])["inputs"] == {"total": "4500"}


def test_in_a_range_only_the_runs_that_used_the_old_value_run_again(session):
    low = run(session, "total", {"unit_count": "40", "unit_price": "100"})
    high = run(session, "total", {"unit_count": "60", "unit_price": "100"})
    low_doubled = run(session, "double", {"total": low["output"]})
    high_doubled = run(session, "double", {"total": high["output"]})
    answer(session, low, high, low_doubled, high_doubled)
    found = engine.impact(session.conn, session.state(), key="unit_count", old="60")
    assert found["runs"] == [f"r{high['run_id']}", f"r{high_doubled['run_id']}"]
    result = engine.rerun(Work(session), key="unit_count", old="60", new="70", label="Unit count")
    assert list(result["replaced"]) == found["runs"]
    assert row(session, result["replaced"][f"r{high_doubled['run_id']}"])["output"] == "14000"
    kept = [low["run_id"], low_doubled["run_id"]]
    assert result["runs"] == sorted(kept + [int(each[1:]) for each in result["replaced"].values()])


def test_a_run_the_gate_refuses_fails_and_so_do_the_runs_that_needed_its_output(session):
    total, split, summed = chain(session, first="500")
    answer(session, total, split, summed)
    result = engine.rerun(Work(session), key="unit_count", old="40", new="2", label="Unit count")
    assert list(result["replaced"]) == [f"r{total['run_id']}"]
    assert [(each["run"], each["step"]) for each in result["failed"]] == [(f"r{split['run_id']}", "c3"),
                                                                          (f"r{summed['run_id']}", "c4")]
    assert "split" in result["failed"][0]["reason"] and result["failed"][1]["reason"] == engine.UPSTREAM_FAILED
    new_total = int(result["replaced"][f"r{total['run_id']}"][1:])
    assert result["runs"] == sorted([new_total, split["run_id"], summed["run_id"]])


def test_a_value_mapped_to_two_new_values_is_ambiguous_and_that_run_is_not_run_again(session):
    split = run(session, "split", {"total": "1500", "first": "500"})        # 500, 500, 500
    payments = [{"name": name, "amount": amount} for name, amount in split["output"].items()]
    summed = run(session, "sum_up", {"payments": payments, "extra": {"amount": "0"}})
    answer(session, split, summed)
    result = engine.rerun(Work(session), key="first", old="500", new="300", label="First")   # 300, 600, 600
    assert list(result["replaced"]) == [f"r{split['run_id']}"]
    assert result["failed"] == [{"run": f"r{summed['run_id']}", "step": "c4", "reason": engine.AMBIGUOUS}]


def test_a_rerun_carries_its_own_assumptions_less_those_about_the_old_value_and_says_what_it_expects(session):
    total = run(session, "total", {"unit_count": "40", "unit_price": "100"},
                ["The unit count stays as it is.", "We expect 40 of them.", "Units cost 100 each.",
                 "Nothing else changes."])
    answer(session, total)
    result = engine.rerun(Work(session), key="unit_count", old="40", new="50", label="Unit count",
                          drop=["Nothing else changes."])
    new = row(session, result["replaced"][f"r{total['run_id']}"])
    assert new["assumptions"] == ["Units cost 100 each."]
    assert new["expected"] == engine.RERUN_EXPECTED.format(label="Unit count", new="50", old="40")


def test_a_run_whose_inputs_come_out_unchanged_is_not_run_again(session):
    total = run(session, "total", {"unit_count": "40", "unit_price": "100"})
    split = run(session, "split", {"total": "900", "first": "100"})
    answer(session, total, split)
    before = session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0]
    result = engine.rerun(Work(session), key="unit_count", old="40", new="50", label="Unit count")
    assert list(result["replaced"]) == [f"r{total['run_id']}"] and result["failed"] == []
    assert session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0] == before + 1
    assert split["run_id"] in result["runs"]


def test_a_value_no_run_used_runs_nothing_and_with_no_old_value_every_run_with_the_key_runs(session):
    low = run(session, "total", {"unit_count": "40", "unit_price": "100"})
    high = run(session, "total", {"unit_count": "60", "unit_price": "100"})
    answer(session, low, high)
    nothing = engine.rerun(Work(session), key="unit_count", old="99", new="50", label="Unit count")
    assert nothing == {"replaced": {}, "failed": [], "runs": [low["run_id"], high["run_id"]]}
    every = engine.rerun(Work(session), key="unit_count", old=None, new="50", label="Unit count")
    assert list(every["replaced"]) == [f"r{low['run_id']}", f"r{high['run_id']}"]
    assert row(session, every["replaced"][f"r{low['run_id']}"])["expected"].endswith("(was none).")


# --- Several values at once (12.4, a bundle) ---

def test_a_bundle_of_changes_runs_again_once_with_every_value_replaced(session):
    total, split, summed = chain(session)
    answer(session, total, split, summed)
    work = Work(session)
    changes = [{"key": "unit_count", "old": "40", "new": "50", "label": "Unit count"},
               {"key": "first", "old": "500", "new": "600", "label": "First"}]
    result = engine.rerun(work, changes=changes)
    assert result["failed"] == []
    assert list(result["replaced"]) == [f"r{each['run_id']}" for each in (total, split, summed)]
    new_total, new_split, new_sum = (row(session, result["replaced"][f"r{each['run_id']}"])
                                     for each in (total, split, summed))
    assert new_total["inputs"] == {"unit_count": "50", "unit_price": "100"}
    assert new_split["inputs"] == {"total": "5000", "first": "600"}
    assert new_split["output"] == {"first": "600", "rest": "2200", "last": "2200"}
    assert new_sum["inputs"]["payments"][1] == {"name": "rest", "amount": "2200"}
    assert new_sum["expected"] == engine.RERUN_EXPECTED.format(label="Unit count", new="50", old="40") + " " + \
        engine.RERUN_EXPECTED.format(label="First", new="600", old="500")
    assert session.conn.execute("SELECT COUNT(*) FROM calc_runs").fetchone()[0] == 6     # each run once


def test_the_impact_of_a_bundle_is_the_union_and_names_every_plan_input(session):
    total, split, summed = chain(session)
    answer(session, total, split, summed)
    found = engine.impact(session.conn, session.state(), changes=[{"key": "first", "old": "500"},
                                                                  {"key": "unit_price", "old": "100"}])
    assert found == {"inputs": ["in:first", "in:unit_price"],
                     "runs": [f"r{each['run_id']}" for each in (total, split, summed)],
                     "steps": ["c1", "c3", "c4"], "downstream": ["c2", "j1"]}


# --- Lineage follows the plan's needs, not bare equality (12.4) ---

def test_a_value_equal_to_a_result_of_a_step_the_run_does_not_need_is_not_remapped(session):
    total = run(session, "total", {"unit_count": "40", "unit_price": "100"})            # 4000
    split = run(session, "split", {"total": "4000", "first": "500"})                     # 500, 1750, 1750
    doubled = run(session, "double", {"total": "1750"})          # c2 needs c1 only; 1750 is c3's, by chance
    answer(session, total, split, doubled)
    found = engine.impact(session.conn, session.state(), key="first", old="500")
    assert found["runs"] == [f"r{split['run_id']}"]
    result = engine.rerun(Work(session), key="first", old="500", new="300", label="First")
    assert list(result["replaced"]) == [f"r{split['run_id']}"] and result["failed"] == []
    assert doubled["run_id"] in result["runs"]


def test_an_old_value_mapped_two_ways_is_read_from_the_step_the_run_needs(session):
    total = run(session, "total", {"unit_count": "5", "unit_price": "100"})             # 500, from c1
    split = run(session, "split", {"total": "1500", "first": "500"})                     # 500, 500, 500 from c3
    doubled = run(session, "double", {"total": "500"})                                   # c2 needs c1
    answer(session, total, split, doubled)
    result = engine.rerun(Work(session), key="unit_count", old="5", new="6", label="Unit count")
    assert result["failed"] == []
    assert row(session, result["replaced"][f"r{doubled['run_id']}"])["inputs"] == {"total": "600"}
    assert row(session, result["replaced"][f"r{doubled['run_id']}"])["output"] == "1200"
