"""The number check (SPEC 5.8): a tripwire for numbers the agent made up.

Every number in what the agent sends out must already be known: it must
appear in a source (a module result, a saved input, the brief, the person's
own words). Small whole numbers are never checked. This is not a proof.
"""
import json
import re
from decimal import Decimal

SMALL = 12      # a bare whole number from 0 to this is never checked
SOURCE_LABELS = ("run", "input", "note", "brief", "person", "today")     # where a number may come from (SPEC 7.1)
SMALL_LABEL = "small"
NONE_LABEL = "none"

DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER = re.compile(r"(?<![\w.])([$€£]?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(k|K|%)?(?![\w%])")


def _read(text: str) -> list[dict]:
    """Every date and number in the text, in order of appearance.

    Each item has `written` (as in the text), `position`, `parts` (a date's
    year, month and day, else None), and for a number its `value`,
    `precision`, `percent` and `exempt`.
    """
    items = []
    for match in DATE.finditer(text):
        year, month, day = (int(part) for part in match.group().split("-"))
        items.append({"written": match.group(), "position": match.start(), "parts": (year, month, day)})
    blanked = DATE.sub(lambda match: " " * len(match.group()), text)       # dates are not read again
    for match in NUMBER.finditer(blanked):
        sign, whole, decimals, suffix = match.groups()
        value = Decimal(whole.replace(",", "") + ("." + decimals if decimals else ""))
        precision = Decimal(1).scaleb(-len(decimals)) if decimals else Decimal(1)
        if suffix in ("k", "K"):
            value, precision = value * 1000, precision * 1000
        items.append({"written": match.group(), "position": match.start(), "parts": None,
                      "value": value, "precision": precision, "percent": suffix == "%",
                      "exempt": not sign and not decimals and not suffix and value <= SMALL})
    return sorted(items, key=lambda item: item["position"])


def _known(source) -> list[Decimal]:
    """Every value a source makes known: its numbers, the parts of its dates, and percentages as fractions."""
    text = source if isinstance(source, str) else json.dumps(source, ensure_ascii=False)
    known = []
    for item in _read(text):
        if item["parts"]:
            known.extend(Decimal(part) for part in item["parts"])
        else:
            known.append(item["value"])
            if item["percent"]:
                known.append(item["value"] / 100)
    return known


def _near(known: list[Decimal], value: Decimal, precision: Decimal) -> bool:
    return any(abs(each - value) <= precision / 2 for each in known)


def unbacked(text: str, sources: list) -> list[str]:
    """The numbers in `text` that no source backs, as written, in order, each once."""
    known = []
    for source in sources:
        known.extend(_known(source))
    missing = []
    for item in _read(text):
        if item["parts"]:
            backed = all(part <= SMALL or _near(known, Decimal(part), Decimal(1)) for part in item["parts"])
        elif item["exempt"]:
            backed = True
        else:
            backed = _near(known, item["value"], item["precision"])
            if item["percent"]:
                backed = backed or _near(known, item["value"] / 100, item["precision"] / 100)
        if not backed and item["written"] not in missing:
            missing.append(item["written"])
    return missing


def trace(text: str, sources: list[tuple[str, int | None, object]]) -> list[dict]:
    """Where each date and number in `text` came from (SPEC 7.1), with the reading of `unbacked`.

    `sources` holds `(label, ref, value)`, the label one of `SOURCE_LABELS`, `ref` a run id or None.
    """
    known = [(label, ref, _known(value)) for label, ref, value in sources]

    def label_of(value: Decimal, precision: Decimal, percent: bool) -> tuple[str, int | None]:
        for label in SOURCE_LABELS:
            refs = [ref for each, ref, values in known if each == label
                    and (_near(values, value, precision) or (percent and _near(values, value / 100, precision / 100)))]
            if refs:
                return label, refs[-1]          # the latest source of that label wins
        return NONE_LABEL, None

    items = []
    for item in _read(text):
        if item["parts"]:
            parts = [label_of(Decimal(part), Decimal(1), False) for part in item["parts"] if part > SMALL]
            if not parts:                       # a year of 12 or below: nothing was ever checked
                label, run_id = SMALL_LABEL, None
            elif any(label == NONE_LABEL for label, _ in parts):
                label, run_id = NONE_LABEL, None
            else:
                label = max((found for found, _ in parts), key=SOURCE_LABELS.index)
                run_id = next(ref for found, ref in parts if found == label)
        elif item["exempt"]:
            label, run_id = SMALL_LABEL, None
        else:
            label, run_id = label_of(item["value"], item["precision"], item["percent"])
        written = item["written"]
        items.append({"text": written, "start": item["position"], "end": item["position"] + len(written),
                      "source": label, "run_id": run_id if label == "run" else None})
    return items
