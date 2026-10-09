"""Values that cross between the harness and a calculation module (SPEC 5.1).

Everything travels as JSON. Money and other exact numbers travel as text, so
that 0.1 + 0.2 is never 0.30000000000000004 on the way.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

TYPES = ("number", "integer", "date", "text", "boolean", "list", "object")
TOLERANCE = Decimal("0.005")        # two numbers this close count as equal


def from_json(value, kind: str):
    """Turn a JSON value into what a module's `calculate` receives for an input of this type."""
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError(f"expected a number, got {value!r}")
        try:
            return Decimal(str(value).replace(",", "").strip())
        except InvalidOperation:
            raise ValueError(f"expected a number, got {value!r}") from None
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError(f"expected a whole number, got {value!r}")
        try:
            return int(str(value).strip())
        except ValueError:
            raise ValueError(f"expected a whole number, got {value!r}") from None
    if kind == "date":
        try:
            return date.fromisoformat(str(value).strip())
        except ValueError:
            raise ValueError(f"expected a date as YYYY-MM-DD, got {value!r}") from None
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"expected true or false, got {value!r}")
        return value
    if kind == "text":
        if not isinstance(value, str):
            raise ValueError(f"expected text, got {value!r}")
        return value
    if kind == "list":
        if not isinstance(value, list):
            raise ValueError(f"expected a list, got {value!r}")
        return value
    if kind == "object":
        if not isinstance(value, dict):
            raise ValueError(f"expected an object, got {value!r}")
        return value
    raise ValueError(f"unknown type: {kind!r}")


def to_json(value):
    """Turn what a module returned into JSON: numbers as text, dates as YYYY-MM-DD."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else format(value, "f")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(Decimal(repr(value)), "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json(item) for item in value]
    raise ValueError(f"a module returned something that cannot be recorded: {value!r}")


def same(expected, actual) -> bool:
    """Are two JSON values the same answer? Numbers match within half a cent."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return expected.keys() == actual.keys() and all(same(expected[k], actual[k]) for k in expected)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(same(e, a) for e, a in zip(expected, actual))
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    left, right = _number(expected), _number(actual)
    if left is not None and right is not None:
        return abs(left - right) <= TOLERANCE
    return expected == actual


def _number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.replace(",", "").strip())
        except InvalidOperation:
            return None
    return None
