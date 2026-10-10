"""Helpers for the layer 0 tests: made-up layers."""
from harness.layers import Layer

SETTLE = 5      # seconds; far more than any job here takes


def fake_layer(number: int = 1, **fields) -> Layer:
    return Layer(number=number, name=f"fake {number}", **fields)


def routes_all(handler):
    """A route that hands every message to `handler`."""
    return lambda core, message: handler
