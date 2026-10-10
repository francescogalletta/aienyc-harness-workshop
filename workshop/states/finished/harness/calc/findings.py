"""Findings (SPEC 9.5): a claim and a reference that disagree, with the evidence quoted.

A finding is put to the person in a block the harness builds from the
finding alone. The agent adds no words to it. Whatever found the
disagreement, the finding opens and closes the same way.
"""
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

from .. import db
from .decisions import one_line
from .provenance import _read

FINDING_KINDS = ("earlier", "data", "brief")
TOLERANCE = Decimal("0.05")
MAX_FINDINGS = 2
JUDGMENT_WORDS = ("actually", "but", "however", "wrong", "incorrect", "mistake", "mistaken", "error",
                  "should", "must", "clearly", "obviously", "really", "unfortunately")

FINDING_INTRO = "Two figures for the same thing differ. Only you can decide which one to use:"
FINDING_SAID = "You said: \"{claim}\""
FINDING_DATA = "Your loaded files show {figure}: {what}."
FINDING_BRIEF = "The brief says: \"{quote}\""
FINDING_NOW = "To save now as {name}: {value}"
FINDING_EARLIER = "Saved earlier ({when}) as {name}: {value}"
EARLIER_HERE = "in this conversation"
EARLIER_BEFORE = "in an earlier conversation"
FINDING_KEEP = "Keep what I said: {figure}"
FINDING_USE_DATA = "Use the figure from my files: {figure}"
FINDING_USE_BRIEF = "Use the figure in the brief: {figure}"
FINDING_USE_NEW = "Use the new value: {value}"
FINDING_KEEP_EARLIER = "Keep the earlier value: {value}"


def figure(text: str) -> dict | None:
    """The one date or number in the text that the number check would read, or None (SPEC 9.5)."""
    kept = [item for item in _read(text) if item["parts"] or not item["exempt"]]
    if len(kept) != 1:
        return None
    item = kept[0]
    if item["parts"]:
        return {"written": item["written"], "date": True, "value": item["written"], "percent": False}
    return {"written": item["written"], "date": False, "value": item["value"], "percent": item["percent"]}


def disagree(claim: dict, reference: dict) -> bool | None:
    """Do two figures differ by more than the tolerance? None when a date meets a number (SPEC 9.5)."""
    if claim["date"] != reference["date"]:
        return None
    if claim["date"]:
        return claim["value"] != reference["value"]
    c, r = claim["value"], reference["value"]
    if claim["percent"] != reference["percent"]:
        if claim["percent"]:
            c = c / 100
        else:
            r = r / 100
    return abs(c - r) > TOLERANCE * abs(r)


def plain(item: dict) -> str:
    """A figure as plain text: a date's text, or a number's value, with `%` for a percentage (SPEC 9.5)."""
    if item["date"]:
        return item["value"]
    return str(item["value"]) + ("%" if item["percent"] else "")


def _whole_number(text: str) -> dict | None:
    """The one number, and no date, that is the whole text once stripped; exempt numbers included."""
    text = text.strip()
    items = _read(text)
    if len(items) == 1 and not items[0]["parts"] and items[0]["written"] == text:
        return items[0]
    return None


def same_value(a: str, b: str) -> bool:
    """Are two texts the same, or the same number written differently? (SPEC 9.5)"""
    if one_line(a) == one_line(b):
        return True
    first, second = _whole_number(a), _whole_number(b)
    return (first is not None and second is not None and first["value"] == second["value"]
            and first["percent"] == second["percent"])


def brief_texts(brief: dict) -> list[str]:
    """The texts a figure may be quoted from: each particular's what and handling, each input's name and description."""
    found = []
    for item in brief.get("particulars", []):
        found += [item.get(key) for key in ("what", "handling")]
    for item in brief.get("inputs", []):
        found += [item.get(key) for key in ("name", "description")]
    return [text for text in found if isinstance(text, str)]


def _finding(row) -> dict:
    return {"id": row["id"], "ts": row["ts"], "session_id": row["session_id"], "kind": row["kind"],
            "claim": row["claim"], "claim_figure": row["claim_figure"], "reference": row["reference"],
            "reference_figure": row["reference_figure"], "summary": row["summary_id"],
            "input": row["input_name"], "earlier": json.loads(row["earlier"]) if row["earlier"] else None,
            "pending_note": row["pending_note"], "difference": row["difference"], "block": row["block"],
            "options": json.loads(row["options"]), "status": row["status"], "decision": row["decision_id"],
            "choice": row["choice"], "chosen": row["chosen"]}


def _get(conn, finding_id: int) -> dict:
    return _finding(conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone())


def _block(*, session_id, kind, claim, claim_figure, reference, reference_figure, input_name, earlier,
           difference) -> tuple[str, list[str]]:
    """The block the person is shown, and its two options (SPEC 9.5)."""
    said = FINDING_SAID.format(claim=one_line(claim))
    if kind == "data":
        lines = [said, FINDING_DATA.format(figure=one_line(reference_figure), what=one_line(reference)),
                 one_line(difference)]
        options = [FINDING_KEEP.format(figure=one_line(claim_figure)),
                   FINDING_USE_DATA.format(figure=one_line(reference_figure))]
    elif kind == "brief":
        lines = [said, FINDING_BRIEF.format(quote=one_line(reference)), one_line(difference)]
        options = [FINDING_KEEP.format(figure=one_line(claim_figure)),
                   FINDING_USE_BRIEF.format(figure=one_line(reference_figure))]
    else:
        when = EARLIER_HERE if earlier and earlier.get("session_id") == session_id else EARLIER_BEFORE
        lines = [FINDING_NOW.format(name=one_line(input_name or ""), value=one_line(claim)),
                 FINDING_EARLIER.format(when=when, name=one_line(input_name or ""), value=one_line(reference))]
        options = [FINDING_USE_NEW.format(value=one_line(claim)),
                   FINDING_KEEP_EARLIER.format(value=one_line(reference))]
    block = [FINDING_INTRO] + [f"  {line}" for line in lines]
    block += [f"    {n}. {option}" for n, option in enumerate(options, start=1)]
    return "\n".join(block), options


def open_finding(conn: sqlite3.Connection, *, session_id: str, kind: str, claim: str, claim_figure: str,
                 reference: str, reference_figure: str, summary_id=None, input_name=None, earlier=None,
                 pending_note=None, difference: str = "") -> dict:
    """Build the block and the options, write the finding as `open`, and record `finding.opened` (SPEC 9.5)."""
    if kind not in FINDING_KINDS:
        raise ValueError(f"unknown kind: {kind}")
    block, options = _block(session_id=session_id, kind=kind, claim=claim, claim_figure=claim_figure,
                            reference=reference, reference_figure=reference_figure, input_name=input_name,
                            earlier=earlier, difference=difference)
    cursor = conn.execute(
        "INSERT INTO findings (ts, session_id, kind, claim, claim_figure, reference, reference_figure,"
        " summary_id, input_name, earlier, pending_note, difference, block, options, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')",
        (datetime.now(timezone.utc).isoformat(), session_id, kind, claim, claim_figure, reference,
         reference_figure, summary_id, input_name, json.dumps(earlier) if earlier is not None else None,
         pending_note, difference, block, json.dumps(options)))
    conn.commit()
    found = _get(conn, cursor.lastrowid)
    db.record_event(conn, session_id=session_id, kind="finding.opened", actor="harness", payload=found)
    return found


def _chosen(found: dict, choice: str) -> str | None:
    if choice not in ("1", "2"):
        return None
    if found["kind"] == "earlier":
        return found["claim"] if choice == "1" else found["reference"]
    text = found["claim_figure"] if choice == "1" else found["reference_figure"]
    read = figure(text)
    return plain(read) if read is not None else text


def close_finding(conn: sqlite3.Connection, finding_id: int, *, decision_id: int, choice: str, saved: bool,
                  session_id: str) -> dict:
    """Write the person's choice on the finding and record `finding.closed` (SPEC 9.5)."""
    chosen = _chosen(_get(conn, finding_id), choice)
    conn.execute("UPDATE findings SET status = 'decided', decision_id = ?, choice = ?, chosen = ? WHERE id = ?",
                 (decision_id, choice, chosen, finding_id))
    conn.commit()
    db.record_event(conn, session_id=session_id, kind="finding.closed", actor="harness",
                    payload={"finding": finding_id, "decision": decision_id, "choice": choice, "chosen": chosen,
                             "saved": saved})
    return _get(conn, finding_id)


def list_findings(conn: sqlite3.Connection, *, session_id=None) -> list[dict]:
    """The findings of one session, or of every session, oldest first (SPEC 9.5)."""
    return [_finding(row) for row in conn.execute(
        "SELECT * FROM findings WHERE (:session_id IS NULL OR session_id = :session_id) ORDER BY id",
        {"session_id": session_id})]


def open_findings(conn: sqlite3.Connection, *, session_id: str) -> list[dict]:
    """The findings of the session that are still open, oldest first (SPEC 9.5)."""
    return [each for each in list_findings(conn, session_id=session_id) if each["status"] == "open"]
