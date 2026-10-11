"""Run and mark (SPEC 6.1): what a run took as given is stored, shown under the answer and on the step,
and the person confirms it with one action or corrects it in their own words.

"Unconfirmed" means exactly: an assumption of a run whose status is not `confirmed`. A step shows it for its
last run (a `corrected` assumption used again counts), so a mark goes away only by confirming, or by a run
that no longer rests on it.
"""
import json
import re
from decimal import Decimal, InvalidOperation

from .. import db
from ..answers.agent import Turn, person_words, saved_inputs, step_of_module, without_meta
from ..calc.added import process_steps
from ..calc.builder import plan_of
from ..calc.provenance import SMALL, unbacked
from ..core import NotNow, get_message, number_of

UNCONFIRMED, CONFIRMED, CORRECTED = "unconfirmed", "confirmed", "corrected"
UNLISTED = ("These values are not ones the person gave (in their words, a saved input, a confirmed assumption or an "
            "earlier result): {values}. Each is an assumption: give it in `assumptions`, with its value, in plain "
            "words. Then run again.")
AUTO_ASSUMED = "{input} is taken to be {value}, which you did not give."
CORRECTED_LINE = ("[harness] The person says this is not right: {assumptions}. Their words follow. "
                  "Run again the steps that rested on it.")
NOTHING_TO_CONFIRM = "Nothing under that answer is waiting to be confirmed."


def one_line(text: str) -> str:
    return " ".join(str(text).split())


def key_of(text: str) -> str:
    return one_line(text).casefold()


def _assumption(row) -> dict:
    return {"id": f"a{row['id']}", "text": row["text"], "status": row["status"], "words": row["words"]}


def link_run(conn, run_id: int, sentences) -> list[dict]:
    """Store each sentence a run assumed (a new key is `unconfirmed`) and link it to the run. Idempotent.
    Returns the run's assumptions, in the order they were given."""
    found, seen = [], set()
    for sentence in sentences or []:
        text = one_line(sentence)
        if not text or key_of(text) in seen:
            continue
        seen.add(key_of(text))
        row = conn.execute("SELECT * FROM assumptions WHERE key = ?", (key_of(text),)).fetchone()
        if row is None:
            conn.execute("INSERT INTO assumptions (key, text, status, words, ts) VALUES (?, ?, ?, '', ?)",
                         (key_of(text), text, UNCONFIRMED, db.now()))
            row = conn.execute("SELECT * FROM assumptions WHERE key = ?", (key_of(text),)).fetchone()
        if conn.execute("SELECT 1 FROM run_assumptions WHERE run_id = ? AND assumption_id = ?",
                        (run_id, row["id"])).fetchone() is None:
            conn.execute("INSERT INTO run_assumptions (run_id, assumption_id) VALUES (?, ?)", (run_id, row["id"]))
        found.append(_assumption(row))
    conn.commit()
    return found


def of_run(conn, run_id: int, sentences) -> list[dict]:
    """The assumptions of a run with their status now. Stores them first if they are not stored yet."""
    wanted = {key_of(each) for each in sentences or [] if one_line(each)}
    known = conn.execute(
        "SELECT a.* FROM run_assumptions r JOIN assumptions a ON a.id = r.assumption_id WHERE r.run_id = ?"
        " ORDER BY a.id", (run_id,)).fetchall()
    if {row["key"] for row in known} != wanted:
        return link_run(conn, run_id, sentences)
    order = {key_of(each): n for n, each in enumerate(sentences or [])}
    return [_assumption(row) for row in sorted(known, key=lambda row: order.get(row["key"], 0))]


def unconfirmed_of_run(conn, run_id: int, sentences) -> list[dict]:
    return [each for each in of_run(conn, run_id, sentences) if each["status"] != CONFIRMED]


def get(conn, assumption_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM assumptions WHERE id = ?", (number_of(assumption_id, "a"),)).fetchone()
    return _assumption(row) if row else None


def set_status(conn, ids: list[str], status: str, words: str = "") -> None:
    for each in ids:
        conn.execute("UPDATE assumptions SET status = ?, words = ?, ts = ? WHERE id = ?",
                     (status, words, db.now(), number_of(each, "a")))
    conn.commit()


# --- The notice under an answer ---

def notice_status(conn, notice: dict) -> str:
    """A notice's status now: open, but with every assumption since confirmed (maybe under another answer),
    reads as confirmed."""
    if notice["status"] != "open":
        return notice["status"]
    rows = [get(conn, each["id"]) for each in notice["assumptions"]]
    return "open" if any(row and row["status"] != CONFIRMED for row in rows) else "confirmed"


def make_notice(turn: Turn) -> dict | None:
    """The notice of a finished turn: the unconfirmed assumptions of its runs and the steps of those runs."""
    conn = turn.conn
    brief = plan_of(turn.work.config)
    step_ids = {step["id"] for step in process_steps(conn, brief)} if brief else set()
    assumptions, steps = {}, []
    for run_id in turn.runs:
        row = conn.execute("SELECT module, assumptions FROM calc_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            continue
        loose = unconfirmed_of_run(conn, run_id, json.loads(row["assumptions"]))
        if not loose:
            continue
        for each in loose:
            assumptions.setdefault(each["id"], {"id": each["id"], "text": each["text"]})
        step = step_of_module(conn, row["module"], step_ids)
        if step and step not in steps:
            steps.append(step)
    if not assumptions:
        return None
    return {"assumptions": list(assumptions.values()), "steps": steps, "status": "open"}


def turn_finished(work, turn: Turn) -> None:
    """Hook: a turn that ran modules on unconfirmed assumptions gets a notice on its final message. A reply
    that was withheld gets none: the person never saw what the assumptions were for (the steps keep the mark)."""
    if not turn.runs or not turn.reply or turn.withheld:
        return
    notice = make_notice(turn)
    if notice is not None:
        work.session.update_message(turn.reply, {"notice": notice})


# --- The person's two answers ---

def confirm(core, message_id: str) -> None:
    """The `confirm_assumptions` action (NotNow is raised by the caller's checks)."""
    message = get_message(core.conn, message_id)
    notice = (message or {}).get("notice")
    if not notice or notice_status(core.conn, notice) != "open":
        raise NotNow(NOTHING_TO_CONFIRM)
    ids = [each["id"] for each in notice["assumptions"]]
    set_status(core.conn, ids, CONFIRMED)
    core.update_message(message_id, {"notice": {**notice, "status": "confirmed"}})
    core.record("you.assumptions_confirmed", {"message": message_id, "assumptions": ids}, "person")


def correct(work, message_id: str, words: str) -> list[str]:
    """The person says in their own words that a notice's assumptions are not right. Those of the notice not
    yet confirmed become `corrected` (all of them when none is open any more: they changed their mind).
    Returns the corrected assumptions' texts."""
    notice = get_message(work.conn, message_id)["notice"]
    rows = [get(work.conn, each["id"]) for each in notice["assumptions"]]
    targets = [row for row in rows if row and row["status"] != CONFIRMED] or [row for row in rows if row]
    ids = [row["id"] for row in targets]
    set_status(work.conn, ids, CORRECTED, words)
    work.session.update_message(message_id, {"notice": {**notice, "status": "changed"}})
    work.record("you.assumptions_corrected", {"message": message_id, "assumptions": ids, "words": words}, "person")
    return [row["text"] for row in targets]


def correction_text(texts: list[str], words: str) -> str:
    return CORRECTED_LINE.format(assumptions=" ".join(texts)) + "\n\n" + words


def route(core, message: dict):
    """A message with a notice reference is the person's "Change it": the analyst turn that corrects it."""
    from ..answers.agent import answer
    from ..grounding.layer import phase_of

    notice_message = message.get("notice")
    if not notice_message or phase_of(core) != "accepted":
        return None
    found = get_message(core.conn, notice_message)
    if not found or not found.get("notice"):
        return None

    def handler(work, message: dict) -> None:
        texts = correct(work, notice_message, message["text"])
        answer(work, {**message, "text": correction_text(texts, message["text"])})

    handler.what = "answer"
    return handler


# --- Unlisted assumptions (SPEC 6.1): a run input the person did not give, left out of `assumptions` ---

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLAIN_NUMBER = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?$")
MONTHS = {name: n for n, name in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                             "august", "september", "october", "november", "december"], start=1)}
MONTH = r"(january|february|march|april|may|june|july|august|september|october|november|december|" \
        r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\.?"
DAY_MONTH_YEAR = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + MONTH + r",?\s+(\d{4})\b", re.IGNORECASE)
MONTH_DAY_YEAR = re.compile(r"\b" + MONTH + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.IGNORECASE)
ANY_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
WORDS = {"half": "0.5", "halves": "0.5", "third": "0.333333333333", "thirds": "0.333333333333",
         "quarter": "0.25", "quarters": "0.25", "fifth": "0.2", "tenth": "0.1",
         **{word: str(n) for n, word in enumerate(
             ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
              "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"])}}
EVEN = {"equal", "equally", "evenly", "even"}          # only for reading an assumption sentence: "split evenly"
WORD = re.compile(r"[a-z]+")


def _month(name: str) -> int:
    name = name.casefold().rstrip(".")
    return next(n for full, n in MONTHS.items() if full.startswith(name[:3]))


def dates_in(text: str) -> set[str]:
    """The dates a text holds whole, as ISO dates: written as ISO, `12 June 2027` or `June 12, 2027`."""
    found = set(ANY_ISO.findall(text))
    for day, month, year in DAY_MONTH_YEAR.findall(text):
        found.add(f"{int(year):04d}-{_month(month):02d}-{int(day):02d}")
    for month, day, year in MONTH_DAY_YEAR.findall(text):
        found.add(f"{int(year):04d}-{_month(month):02d}-{int(day):02d}")
    return found


def spelled(text: str, even: bool = False) -> str:
    """The numbers a text says in words (`half` is 0.5, `three` is 3), written as numbers."""
    words = WORD.findall(text.casefold())
    found = [WORDS[word] for word in words if word in WORDS]
    if even and EVEN & set(words):
        found.append("0.5")
    return " ".join(found)


def given_texts(texts) -> list[str]:
    """Sources of what the person gave, from texts: each text, its numbers said in words and its dates."""
    found = []
    for text in texts:
        text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
        found += [text, spelled(text), " ".join(sorted(dates_in(text)))]
    return found


def _persons_items(value) -> list:
    """The items of the plan whose origin is the person."""
    if isinstance(value, list):
        return [found for each in value for found in _persons_items(each)]
    if not isinstance(value, dict):
        return []
    if (value.get("origin") or {}).get("kind") == "person":
        return [value]
    return [found for each in value.values() for found in _persons_items(each)]


def given_sources(turn: Turn) -> list[str]:
    """What the person gave (SPEC 6.1): their messages, saved inputs, the plan's items of origin `person`, confirmed
    assumptions, today, and the outputs of the runs of this conversation."""
    conn = turn.conn
    texts = [*person_words(conn, turn.conversation), turn.today()]
    texts += [each["value"] for each in saved_inputs(conn).values()]
    texts += _persons_items(without_meta(plan_of(turn.work.config)))
    texts += [row["text"] for row in conn.execute("SELECT text FROM assumptions WHERE status = ?", (CONFIRMED,))]
    texts += [json.loads(row["output"]) for row in conn.execute(
        "SELECT output FROM calc_runs WHERE session_id = ?", (turn.conversation,))]
    return given_texts(texts)


def _leaves(value, name: str = ""):
    """(input name, value) for every value inside a run's inputs; the name is the nearest key."""
    if isinstance(value, dict):
        for key, each in value.items():
            yield from _leaves(each, str(key))
    elif isinstance(value, list):
        for each in value:
            yield from _leaves(each, name)
    else:
        yield name, value


def _checked(value) -> tuple[str, str] | None:
    """("date" | "number", the value as text) for a value the check reads; None for text, true/false and small
    whole numbers."""
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    if ISO_DATE.match(text):
        return "date", text
    if not isinstance(value, (int, float, Decimal)) and not PLAIN_NUMBER.match(text):
        return None
    try:
        number = Decimal(text.replace(",", "").rstrip("%"))
    except InvalidOperation:
        return None
    if number == number.to_integral_value() and abs(number) <= SMALL and not text.endswith("%"):
        return None
    return "number", text


def _holds(kind: str, text: str, sources: list[str]) -> bool:
    if kind == "date":
        return any(text in dates_in(source) for source in sources)
    return not unbacked(text.lstrip("-"), sources)


def unlisted(inputs, assumptions, sources: list[str]) -> list[tuple[str, str]]:
    """The (input, value) of a run's inputs that the person did not give (`sources`, from `given_sources`) and that
    no sentence of `assumptions` lists: by its value, or by the input's name in words."""
    sentences = [one_line(each) for each in assumptions or [] if isinstance(each, str)]
    listed = [*sentences, *(spelled(each, even=True) for each in sentences),
              *(" ".join(sorted(dates_in(each))) for each in sentences)]
    named = " ".join(sentences).casefold()
    found = []
    for name, value in _leaves(inputs):
        checked = _checked(value)
        if checked is None or _holds(*checked, sources):
            continue
        words = name.replace("_", " ").strip().casefold()
        if (words and words in named) or (sentences and _holds(*checked, listed)):
            continue
        if (name, checked[1]) not in found:
            found.append((name, checked[1]))
    return found


def run_ready(work, turn: Turn, arguments: dict) -> None:
    """Hook: the first run of a turn with an unlisted assumption is refused; on a later run of the turn the harness
    adds the sentence itself, so the run carries a mark either way (SPEC 6.1)."""
    assumptions = arguments.get("assumptions")
    assumptions = assumptions if isinstance(assumptions, list) else []
    found = unlisted(arguments.get("inputs"), assumptions, given_sources(turn))
    if not found:
        return
    values = [{"input": name, "value": value} for name, value in found]
    if not turn.extra.get("unlisted_refused"):
        turn.extra["unlisted_refused"] = True
        turn.record("you.assumption_unlisted", {"module": arguments.get("module"), "values": values,
                                                "outcome": "refused"})
        turn.send_back = UNLISTED.format(values=", ".join(f"{name} = {value}" for name, value in found))
        return
    added = [AUTO_ASSUMED.format(input=(name.replace("_", " ").strip() or "A value").capitalize(), value=value)
             for name, value in found]
    arguments["assumptions"] = [*assumptions, *added]
    turn.record("you.assumption_unlisted", {"module": arguments.get("module"), "values": values,
                                            "outcome": "marked"})

