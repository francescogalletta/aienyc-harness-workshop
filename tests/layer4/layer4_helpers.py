"""Helpers for the layer 4 tests: layer 3's small plan (two built modules, a calculation without one, a
judgment step), scripted analyst turns, and the turns of a scripted build."""
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "layer3"))      # layer3_helpers
sys.path.append(str(Path(__file__).resolve().parents[1] / "layer0"))      # state_shape

from layer3_helpers import (SETTLE, assistant, call, events, number, reply, run, save,  # noqa: E402,F401
                            small_plan, step_of, write_world)
from state_shape import problems  # noqa: E402,F401

WAIT = 5


def say(session, text, step=None, notice=None):
    applied, why = session.act("say", {"text": text, "step": step, "notice": notice})
    assert applied, why
    return session.settle(SETTLE)


def act(session, action, **payload):
    applied, why = session.act(action, payload)
    assert applied, why
    return session.settle(SETTLE)


def refused(session, action, **payload):
    applied, why = session.act(action, payload)
    assert not applied
    return why


def ask(step, question, options, runs=(), **more):
    return call("ask_decision", step=step, question=question, options=list(options), runs=list(runs), **more)


def request(case, **more):
    base = {"works_out": "three times an amount", "from_what": "an amount", "gives": "the tripled amount",
            "formula": "amount x 3", "why": "the person asked for it"}
    return call("request_module", case=case, **{**base, **more})


def chat_of(state, who):
    return [message for message in state["chat"] if message["who"] == who]


def notices(state):
    return [message for message in state["chat"] if message.get("notice")]


# --- A scripted build of one more calculation: "triple" ---

TRIPLE_SPEC = {"name": "triple", "description": "triples an amount", "method": "arithmetic", "formula": "amount x 3",
               "inputs": [number("amount")], "output": {"type": "number", "description": "three times the amount"}}
TRIPLE_CODE = ("def calculate(amount):\n    return amount * 3\n",
               "from decimal import Decimal\nfrom module import calculate\n\n\ndef test_triples():\n"
               "    assert calculate(amount=Decimal('4')) == Decimal('12')\n")
TRIPLE_EXAMPLES = [{"inputs": {"amount": str(n)}, "expected": str(n * 3), "working": f"{n} x 3 = {n * 3}"}
                   for n in (5, 0, 50)]
TAX_SPEC = {"name": "tax", "description": "tax on the double", "method": "arithmetic", "formula": "double x 2",
            "inputs": [number("double")], "output": {"type": "number", "description": "the tax"}}
TAX_CODE = ("def calculate(double):\n    return double * 2\n",
            "from decimal import Decimal\nfrom module import calculate\n\n\ndef test_tax():\n"
            "    assert calculate(double=Decimal('4')) == Decimal('8')\n")
TAX_EXAMPLES = [{"inputs": {"double": str(n)}, "expected": str(n * 2), "working": f"{n} x 2 = {n * 2}"}
                for n in (5, 0, 50)]


def build_turns(spec, examples, code):
    """What the builder asks of the model for one step: spec, examples, second pass, code."""
    checked = [{"n": n, "answer": each["expected"], "working": f"{each['working']}; so {each['expected']}"}
               for n, each in enumerate(examples, start=1)]
    return [call("propose_spec", **spec, departures=[]), call("propose_examples", examples=examples),
            call("answer_examples", answers=checked), call("write_module", module_py=code[0], tests_py=code[1])]


def triple_turns():
    return build_turns(TRIPLE_SPEC, TRIPLE_EXAMPLES, TRIPLE_CODE)


def tax_turns():
    return build_turns(TAX_SPEC, TAX_EXAMPLES, TAX_CODE)


def until(session, condition, timeout=SETTLE):
    """Wait (polling) until `condition(state)` holds; returns the state."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = session.state()
        if condition(state):
            return state
        session.wait_for_change(state["version"], 0.2)
    raise AssertionError("timed out waiting")
