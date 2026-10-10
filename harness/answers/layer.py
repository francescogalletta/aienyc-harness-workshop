"""Layer 3, answers with evidence (SPEC 5). A skeleton: package A3 fills it in."""
from pathlib import Path

from ..layers import Layer

LAYER = Layer(number=3, name="answers", schema=Path(__file__).with_name("schema.sql"))
