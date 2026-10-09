"""Side conversations (SPEC 8.5).

At any question the person can type `/aside` and talk it through with a side
assistant that has its own prompt, context and messages. It cannot run a
module, save an input, ask for a build or record a decision. Only the words
the person types at `ASIDE_CARRY` cross back to the main conversation.
"""
import json
from pathlib import Path

from .. import db
from ..grounding.interview import LOOK_UP
from ..grounding.research import MAX_QUERY_LENGTH, ResearchDesk, as_lookup, get_researcher
from .added import step_label
from .agent import EMPTY_REPLY, TOO_MANY, WITHHELD, WITHHELD_NOTE
from .builder import format_sections, plan_words
from .decisions import list_decisions
from .provenance import unbacked
from .registry import list_modules

MAX_ASIDE_TURNS = 6
MAX_ASIDE_CALLS = 5
MAX_ASIDE_LOOKUPS = 3
ASIDE_MARK = "aside | "
ASIDE_PROMPT = "aside> "
NOTHING_WORDS = ("no", "n", "nothing", "no.")
ASIDE_OPEN = ("---- Side conversation. The main conversation waits, and will not see what is said here. "
              "Type /back to go back to it. ----")
ASIDE_CLOSE = "---- Back to the main conversation. ----"
ASIDE_FIRST = "What would you like to talk through?"
ASIDE_NESTED = "You are already in a side conversation. Type /back to go back to the main one."
ASIDE_THINKING = "(thinking)"
ASIDE_LOOKING_UP = "(looking up: {query})"
ASIDE_LIMIT = "That is as far as one side conversation goes: {limit} messages."
ASIDE_CARRY = ("Before you go back: is there anything the main conversation should know? Type it in your own "
               "words, and it is passed on exactly as you write it. Type no to pass on nothing.")
ASIDE_CARRIED = ("[harness] The person stepped aside for a side conversation that you did not see. They asked "
                 "for this to be passed on, in their own words:\n{text}")
ASIDE_NUMBERS = ("[harness] Your reply was not shown. These numbers are not in what you were given, the person's "
                 "messages here or a lookup: {numbers}. Do not work numbers out yourself. Leave the number out, "
                 "or tell the person the main conversation can work it out with a tested module. Then reply again.")
LOOKUP_TERM = "Send only the term to look up, at most {limit} characters."
LOOKUP_FAILED = "The lookup failed: {error}"
ASIDE_LOOKUP_LIMIT = "No more lookups in this side conversation. Answer with what you have."


def marked(text: str) -> str:
    """`ASIDE_MARK` before every line of the text (SPEC 8.5)."""
    return "\n".join(ASIDE_MARK + line for line in text.split("\n"))


def _opens_aside(answer: str) -> bool:
    """Is this answer `/aside`, with or without words after it?"""
    low = answer.strip().lower()
    return low == "/aside" or (low.startswith("/aside") and low[len("/aside"):][:1].isspace())


class _KeptDesk:
    """A research desk made at the first lookup and kept for the conversation (SPEC 8.5)."""

    def __init__(self, conn):
        self.conn = conn
        self.desk = None

    def look_up(self, query: str) -> dict:
        if self.desk is None:
            self.desk = ResearchDesk(get_researcher(), self.conn)
        return self.desk.look_up(query)


class Asides:
    """The `ask` and `say` of a conversation, with `/aside` at every question (SPEC 8.5)."""

    def __init__(self, *, model, conn, brief, ask, say, session_id, today: str, desk=None):
        self.model, self.conn, self.brief = model, conn, brief
        self.session_id, self.today = session_id, today
        self.desk = desk if desk is not None else _KeptDesk(conn)
        self._ask, self._say = ask, say
        self.carried: list[str] = []        # every text carried back in this session, oldest first
        self._given = 0                     # how many of them the agent has been given
        self._shown: list[str] = []         # shown since the last answer
        self._opened = 0                    # side conversations opened so far

    def say(self, text: str) -> None:
        self._say(text)
        if not text.startswith("  ("):      # a progress line is not something the person looked at
            self._shown.append(text)

    def ask(self, text: str) -> str:
        looking_at = "\n".join(self._shown) if self._shown else None
        while True:
            answer = self._ask(text)
            self._shown = []
            if not _opens_aside(answer):
                return answer
            self._opened += 1
            how, carried = run_aside(model=self.model, conn=self.conn, brief=self.brief, ask=self._ask,
                                     say=self._say, session_id=self.session_id, aside=self._opened,
                                     looking_at=looking_at, first=answer.strip()[len("/aside"):].strip(),
                                     today=self.today, desk=self.desk)
            if carried is not None:
                self.carried.append(carried)
            if how == "quit":
                return "/quit"
            if looking_at is not None:
                self._say(looking_at)

    def take_carried(self) -> list[str]:
        """The texts carried back that the agent has not been given yet, oldest first."""
        fresh = self.carried[self._given:]
        self._given = len(self.carried)
        return fresh


def aside_context(conn, brief: dict, *, session_id: str, today: str, looking_at: str | None) -> str:
    """The side assistant's context, made when the side conversation opens (SPEC 8.5)."""
    plans = {module["name"]: {"steps": [step_label(step) for step in module["steps"]],
                              "plan": plan_words(module["spec"])}
             for module in list_modules(conn)}
    runs = [{"run": row["id"], "module": row["module"], "inputs": json.loads(row["inputs"]),
             "output": json.loads(row["output"])}
            for row in conn.execute("SELECT * FROM calc_runs WHERE session_id = ? ORDER BY id", (session_id,))]
    decisions = [{key: value for key, value in decision.items() if key not in ("ts", "session_id")}
                 for decision in list_decisions(conn, session_id=session_id)]
    return format_sections({"today": today, "goal": brief["goal"], "glossary": brief["glossary"],
                            "particulars": brief["particulars"], "process": brief["process"],
                            "plans": plans, "runs in this conversation": runs,
                            "decisions in this conversation": decisions, "looking at": looking_at})


def run_aside(*, model, conn, brief, ask, say, session_id, aside: int, looking_at: str | None,
              first: str, today: str, desk=None) -> tuple[str, str | None]:
    """One side conversation. Returns (how it ended: back, limit or quit, the text to carry back or None)."""
    def record(kind, actor, payload):
        db.record_event(conn, session_id=session_id, kind=kind, actor=actor, payload={"aside": aside, **payload})

    record("aside.opened", "person", {"first": first, "looking_at": looking_at})
    say(ASIDE_OPEN)
    context = aside_context(conn, brief, session_id=session_id, today=today, looking_at=looking_at)
    system = Path(__file__).with_name("aside.md").read_text(encoding="utf-8").replace("{context}", context)
    typed, lookups, messages = [], [], []       # the sources besides the context, and the messages
    kept = {"desk": desk, "count": 0}

    def look_up(call) -> dict:
        query = str(call.arguments.get("query", "")).strip()
        if not query or len(query) > MAX_QUERY_LENGTH:
            return _result(call, LOOKUP_TERM.format(limit=MAX_QUERY_LENGTH), True)
        if kept["count"] >= MAX_ASIDE_LOOKUPS:
            return _result(call, ASIDE_LOOKUP_LIMIT, True)
        say(marked(ASIDE_LOOKING_UP.format(query=query)))
        if kept["desk"] is None:
            kept["desk"] = ResearchDesk(get_researcher(), conn)
        entry = kept["desk"].look_up(query)
        kept["count"] += 1
        if entry["status"] == "failed":
            record("aside.lookup", "agent", {"query": entry["query"], "error": entry["error"]})
            return _result(call, LOOKUP_FAILED.format(error=entry["error"]), True)
        content = json.dumps(as_lookup(entry))
        record("aside.lookup", "agent", as_lookup(entry))
        lookups.append(content)
        return _result(call, content, False)

    def work() -> tuple[str, str]:
        """Work on the last message. Returns what to show, and a note for the next message."""
        calls, corrected = 0, False
        while True:
            if calls == MAX_ASIDE_CALLS:
                record("aside.stopped", "harness", {"reason": "too many steps"})
                return TOO_MANY, ""
            say(marked(ASIDE_THINKING))
            response = model.complete(system=system, messages=messages, tools=(LOOK_UP,))
            calls += 1

            if response.tool_calls:         # its text is not shown
                results = [look_up(call) if call.name == "look_up"
                           else _result(call, f"There is no tool called {call.name} here.", True)
                           for call in response.tool_calls]
                messages.append({"role": "assistant", "content": response.text, "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in response.tool_calls]})
                messages.extend(results)
                continue

            text = response.text.strip()
            if not text:
                messages.append({"role": "user", "content": EMPTY_REPLY})
                continue
            numbers = unbacked(text, [context, *typed, *lookups])
            if numbers and not corrected:
                corrected = True
                record("aside.correction", "harness", {"numbers": numbers, "text": text})
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": ASIDE_NUMBERS.format(numbers=", ".join(numbers))})
                continue
            messages.append({"role": "assistant", "content": text})
            if numbers:
                record("aside.withheld", "harness", {"numbers": numbers, "text": text})
                joined = ", ".join(numbers)
                return WITHHELD.format(numbers=joined), "\n\n" + WITHHELD_NOTE.format(numbers=joined)
            record("aside.reply", "agent", {"text": text})
            return text, ""

    def read(shown: str, message: str | None) -> tuple[str, str]:
        """Read a message as in SPEC 8.5, step 4. Returns ("turn", text), ("back", "") or ("quit", "")."""
        while True:
            if message is None:
                message = ask(shown)
            message = message.strip()
            if not message:
                message = None
            elif _opens_aside(message):
                say(marked(ASIDE_NESTED))
                message = None
            elif message.lower() == "/back":
                return "back", ""
            elif message.lower() == "/quit":
                return "quit", ""
            else:
                return "turn", message

    turns, how, note = 0, "back", ""
    kind, text = read(marked(ASIDE_FIRST), first or None)
    while kind == "turn":
        turns += 1
        typed.append(text)
        record("aside.message", "person", {"text": text})
        messages.append({"role": "user", "content": text + note})
        shown, note = work()
        if turns == MAX_ASIDE_TURNS:
            say(marked(shown))
            say(marked(ASIDE_LIMIT.format(limit=MAX_ASIDE_TURNS)))
            kind, how = "limit", "limit"
            break
        kind, text = read(marked(shown), None)
    else:
        how = kind

    carried = None
    if how != "quit":
        said = ask(marked(ASIDE_CARRY)).strip()
        if said.lower() == "/quit":
            how = "quit"
        elif said and said.lower() not in NOTHING_WORDS and not said.startswith("/"):
            carried = said
    record("aside.closed", "person", {"turns": turns, "how": how, "carried": carried})
    say(ASIDE_CLOSE)
    return how, carried


def _result(call, content: str, is_error: bool) -> dict:
    result = {"role": "tool", "tool_call_id": call.id, "content": content}
    if is_error:
        result["is_error"] = True
    return result
