"""Layer 2, build and tested calculations (SPEC 4). A skeleton: packages A2a and A2b fill it in."""
from pathlib import Path

from ..layers import Layer

LAYER = Layer(number=2, name="build", schema=Path(__file__).with_name("schema.sql"))
