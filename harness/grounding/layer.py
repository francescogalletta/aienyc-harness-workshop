"""Layer 1, the plan (SPEC 3). A skeleton: package A1 fills in contribute, route, actions and `ground`."""
from pathlib import Path

from ..layers import Layer

LAYER = Layer(number=1, name="the plan", schema=Path(__file__).with_name("schema.sql"))
