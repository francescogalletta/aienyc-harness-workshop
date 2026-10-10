"""The number check (SPEC 5.8): a tripwire for numbers the agent made up.

Every number in what the agent sends out must already be known: it must
appear in a source (a module result, a saved input, the brief, the person's
own words). Small whole numbers are never checked. This is not a proof.
"""
import json
import re
from decimal import Decimal

SMALL = 12      # a bare whole number from 0 to this is never checked
SOURCE_LABELS = ("run", "data", "input", "note", "brief", "person", "today")     # where a number may come from (SPEC 7.1)
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


def _produced(output, given) -> tuple[list[Decimal], set[str]]:
    """What a run produced, for `trace`: the numbers in its output (never the parts of a date) and its dates
    written whole. Of an object or a list output, every number and date that is also among its inputs is left
    out: a value passed through is not produced. A single value is the result, whatever its inputs were."""
    out_text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    if not isinstance(output, (list, dict)):
        given = None
    in_text = "" if given is None else given if isinstance(given, str) else json.dumps(given, ensure_ascii=False)
    given_items = _read(in_text)
    given_numbers = {item["value"] for item in given_items if not item["parts"]}
    given_dates = {item["written"] for item in given_items if item["parts"]}
    numbers, dates = [], set()
    for item in _read(out_text):
        if item["parts"]:
            if item["written"] not in given_dates:
                dates.add(item["written"])
        elif item["value"] not in given_numbers:
            numbers.append(item["value"])
            if item["percent"]:
                numbers.append(item["value"] / 100)
    return numbers, dates


def trace(text: str, sources: list[tuple]) -> list[dict]:
    """Where each date and number in `text` came from (SPEC 5.2), with the reading of `unbacked`.

    `sources` holds `(label, ref, value)` or, for a run, `(label, ref, output, inputs)`: the label one of
    `SOURCE_LABELS`, `ref` a run id (a data summary id for `data`) or None. Labels are tried in the order of
    `SOURCE_LABELS`; of several sources of one label the first given wins, so callers give them in order of
    preference. A `run` source counts only for what its run produced (`_produced`): a number in its output that
    is not among its inputs, or a date written whole that its output holds. The parts of a date never lead to a
    run, so a year or a day is never traced to one.
    """
    known, produced = [], []
    for source in sources:
        label, ref, value = source[0], source[1], source[2]
        if label == "run":
            produced.append((ref, *_produced(value, source[3] if len(source) > 3 else None)))
        else:
            known.append((label, ref, _known(value)))

    def label_of(value: Decimal, precision: Decimal, percent: bool, *, runs: bool = True) -> tuple[str, int | None]:
        def near(values):
            return _near(values, value, precision) or (percent and _near(values, value / 100, precision / 100))
        for label in SOURCE_LABELS:
            if label == "run":
                refs = [ref for ref, numbers, _ in produced if runs and near(numbers)]
            else:
                refs = [ref for each, ref, values in known if each == label and near(values)]
            if refs:
                return label, refs[0]
        return NONE_LABEL, None

    items = []
    for item in _read(text):
        if item["parts"]:
            whole = [ref for ref, _, dates in produced if item["written"] in dates]
            parts = [label_of(Decimal(part), Decimal(1), False, runs=False) for part in item["parts"] if part > SMALL]
            if whole:
                label, run_id = "run", whole[0]
            elif not parts:                     # a year of 12 or below: nothing was ever checked
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
                      "source": label, "run_id": run_id if label in ("run", "data") else None})
    return items
