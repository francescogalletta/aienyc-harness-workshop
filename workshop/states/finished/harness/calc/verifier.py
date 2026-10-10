"""The verifier (SPEC 9.6): a sub-agent that checks the figures a person gives against references.

It has its own prompt (`verifier.md`) and its own context, and never sees the
conversation. It cannot run a module, save an input or talk to the person.
The harness checks every finding it reports, part by part, and drops what
fails.
"""
import json
import re
from pathlib import Path

from .. import db
from ..model import ToolSpec
from ..sources.summaries import MEASURES, SummaryRefused, accounts, describe, full_months, run_summary
from .builder import format_sections
from .decisions import one_line
from .findings import JUDGMENT_WORDS, MAX_FINDINGS, brief_texts, disagree, figure, list_findings, open_finding
from .provenance import _read, unbacked

DATA_SUMMARY_SCHEMA = {"type": "object", "properties": {
    "measure": {"type": "string", "enum": ["money_in", "money_out", "net", "balance"]},
    "account": {"type": "string"},
    "months": {"type": "integer"}, "month": {"type": "string"}},
    "required": ["measure", "account"]}
REPORT_SCHEMA = {"type": "object", "properties": {
    "findings": {"type": "array", "items": {"type": "object", "properties": {
        "claim": {"type": "string"}, "kind": {"type": "string", "enum": ["data", "brief"]},
        "quote": {"type": "string"}, "summary": {"type": "integer"}, "difference": {"type": "string"}},
        "required": ["claim", "kind", "difference"]}}},
    "required": ["findings"]}

DATA_SUMMARY = ToolSpec(
    name="data_summary",
    description=("Summarise the person's loaded account files with tested code. Give the measure and the account "
                 "(or all). For money in, money out and net give months (the latest full months) or month "
                 "(YYYY-MM). The result gives the summary's number and its value."),
    input_schema=DATA_SUMMARY_SCHEMA)
REPORT = ToolSpec(
    name="report",
    description=("End the check. Give findings: a list, empty when nothing differs. Each finding has the claim "
                 "copied from the person's message, its kind, a quote (brief) or a summary number (data), and one "
                 "neutral sentence saying what the reference shows."),
    input_schema=REPORT_SCHEMA)
TOOLS = (DATA_SUMMARY, REPORT)

MAX_VERIFY_CALLS = 4
MAX_VERIFY_SUMMARIES = 6
VERIFY_PROGRESS = "  (checking your figures)"
VERIFY_FAILED = "  (the check of your figures did not finish: {reason})"
VERIFY_NO_REPORT = "[harness] Call report now, with an empty list of findings when nothing differs."
NO_REPORT_REASON = "the verifier gave no report"
SUMMARY_LIMIT = "No more summaries in this check. Call report."
REPORT_SHAPE = "report needs findings: a list, empty when nothing differs."
DROP_SHAPE = "it needs a claim, a kind (data or brief), a difference, and a quote (brief) or a summary (data)"
DROP_NOT_QUOTED = "the claim is not quoted from the person's message"
DROP_CLAIM_FIGURE = "the claim does not hold exactly one figure"
DROP_NOT_IN_BRIEF = "the quote is not in the brief's particulars or inputs"
DROP_NO_SUMMARY = "there is no data summary {summary} in this conversation"
DROP_REFERENCE_FIGURE = "the quote does not hold exactly one figure"
DROP_NOT_COMPARABLE = "one figure is a date and the other is not"
DROP_WITHIN_TOLERANCE = "the two figures are within 5% of each other"
DROP_DIFFERENCE_NUMBERS = "the difference has numbers that are not in the message, the brief or the summary: {numbers}"
DROP_TONE = "the difference uses the word '{word}'"
DROP_ALREADY = "finding {id} already raised this"
DROP_LIMIT = "only 2 findings are raised per message"

TONE = re.compile(r"\b(?:" + "|".join(JUDGMENT_WORDS) + r")\b", re.IGNORECASE)


def _has_figure(text: str) -> bool:
    return any(item["parts"] or not item["exempt"] for item in _read(text))


def needs_check(conn, brief: dict, message: str) -> bool:
    """Is there a figure to check in the message, and something to check it against? (SPEC 9.6)"""
    if not _has_figure(message):
        return False
    return (conn.execute("SELECT 1 FROM transactions LIMIT 1").fetchone() is not None
            or any(_has_figure(text) for text in brief_texts(brief))
            or conn.execute("SELECT 1 FROM inputs LIMIT 1").fetchone() is not None)


def verifier_context(conn, brief: dict, *, today: str) -> str:
    """The sections the verifier is given, made afresh at each check (SPEC 9.6)."""
    saved = {row["name"]: {"value": json.loads(row["value"]), "note": row["note"]}
             for row in conn.execute("SELECT * FROM inputs ORDER BY name")}
    return format_sections({"today": today, "particulars": brief["particulars"], "inputs": brief["inputs"],
                            "saved inputs": saved, "accounts": accounts(conn),
                            "all accounts": {"full_months": full_months(conn, "all")}, "measures": MEASURES})


def _result(call, content: str, is_error: bool) -> dict:
    result = {"role": "tool", "tool_call_id": call.id, "content": content}
    if is_error:
        result["is_error"] = True
    return result


def verify(*, model, conn, brief: dict, message: str, session_id: str, today: str, say) -> list[dict]:
    """Check one person message. Returns the findings it opened, in order. It never raises (SPEC 9.6)."""
    try:
        system = Path(__file__).with_name("verifier.md").read_text(encoding="utf-8").replace(
            "{context}", verifier_context(conn, brief, today=today))
        messages = [{"role": "user", "content": message}]
        summaries = 0       # data_summary calls handled in this check
        for _ in range(MAX_VERIFY_CALLS):
            say(VERIFY_PROGRESS)
            response = model.complete(system=system, messages=messages, tools=TOOLS)
            if not response.tool_calls:
                if response.text.strip():
                    messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": VERIFY_NO_REPORT})
                continue
            results = []
            for call in response.tool_calls:
                if call.name == "data_summary":
                    if summaries >= MAX_VERIFY_SUMMARIES:
                        results.append(_result(call, SUMMARY_LIMIT, True))
                        continue
                    summaries += 1
                    try:
                        results.append(_result(call, json.dumps(
                            run_summary(conn, call.arguments, session_id=session_id)), False))
                    except SummaryRefused as refused:
                        results.append(_result(call, str(refused), True))
                elif call.name == "report":
                    findings = call.arguments.get("findings")
                    if not isinstance(findings, list):
                        results.append(_result(call, REPORT_SHAPE, True))
                        continue
                    return _handle_report(conn, brief, findings, message=message, session_id=session_id)
                else:
                    results.append(_result(call, f"There is no tool called {call.name} here.", True))
            messages.append({"role": "assistant", "content": response.text, "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.tool_calls]})
            messages.extend(results)
        reason = NO_REPORT_REASON
    except Exception as error:
        reason = f"{type(error).__name__}: {' '.join(str(error).split())}"
    db.record_event(conn, session_id=session_id, kind="verify.failed", actor="harness", payload={"reason": reason})
    say(VERIFY_FAILED.format(reason=reason))
    return []


def _handle_report(conn, brief: dict, findings: list, *, message: str, session_id: str) -> list[dict]:
    """Record the report, then open or drop each entry in order (SPEC 9.6)."""
    db.record_event(conn, session_id=session_id, kind="verify.report", actor="agent",
                    payload={"findings": findings})
    opened = []
    for index, entry in enumerate(findings, start=1):
        reason = _drop_reason(conn, brief, entry, message=message, session_id=session_id, opened=opened)
        if isinstance(reason, str):
            db.record_event(conn, session_id=session_id, kind="verify.dropped", actor="harness",
                            payload={"index": index, "reason": reason, "finding": entry})
            continue
        opened.append(open_finding(conn, session_id=session_id, **reason))
    return opened


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _drop_reason(conn, brief: dict, entry, *, message: str, session_id: str, opened: list):
    """Why an entry is dropped (a string), or the arguments to open it (a dict). The rules of SPEC 9.6, in order."""
    if not (isinstance(entry, dict) and _text(entry.get("claim")) and _text(entry.get("difference"))
            and entry.get("kind") in ("data", "brief")
            and (_text(entry.get("quote")) if entry["kind"] == "brief"
                 else isinstance(entry.get("summary"), int) and not isinstance(entry.get("summary"), bool))):
        return DROP_SHAPE
    kind, claim, difference = entry["kind"], one_line(entry["claim"]), entry["difference"]
    if claim not in one_line(message):
        return DROP_NOT_QUOTED
    claimed = figure(claim)
    if claimed is None:
        return DROP_CLAIM_FIGURE
    extra = [message, brief]
    if kind == "brief":
        quote = one_line(entry["quote"])
        if not any(quote in one_line(text) for text in brief_texts(brief)):
            return DROP_NOT_IN_BRIEF
        referred = figure(quote)
        if referred is None:
            return DROP_REFERENCE_FIGURE
        about = {"reference": quote, "reference_figure": referred["written"]}
    else:
        row = conn.execute("SELECT * FROM data_summaries WHERE id = ? AND session_id = ?",
                           (entry["summary"], session_id)).fetchone()
        if row is None:
            return DROP_NO_SUMMARY.format(summary=entry["summary"])
        output = json.loads(row["output"])
        referred = figure(output["value"])
        if referred is None:
            return DROP_REFERENCE_FIGURE
        extra.append(output)
        about = {"reference": describe(output), "reference_figure": output["value"], "summary_id": row["id"]}
    differs = disagree(claimed, referred)
    if differs is None:
        return DROP_NOT_COMPARABLE
    if not differs:
        return DROP_WITHIN_TOLERANCE
    numbers = unbacked(difference, extra)
    if numbers:
        return DROP_DIFFERENCE_NUMBERS.format(numbers=", ".join(numbers))
    tone = TONE.search(difference)
    if tone:
        return DROP_TONE.format(word=tone.group().lower())
    for each in list_findings(conn, session_id=session_id):
        before, now = figure(each["claim_figure"]), figure(each["reference_figure"])
        if (each["kind"] == kind and before is not None and now is not None
                and before["value"] == claimed["value"] and now["value"] == referred["value"]):
            return DROP_ALREADY.format(id=each["id"])
    if len(opened) >= MAX_FINDINGS:
        return DROP_LIMIT
    return {"kind": kind, "claim": claim, "claim_figure": claimed["written"], "difference": one_line(difference),
            **about}
