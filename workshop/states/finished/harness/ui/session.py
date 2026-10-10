"""One grounding interview, driven from a web page (SPEC 4.7).

`run_interview` blocks while it waits for the person. Here it runs on a
background thread: its `ask` hands the question to the page and sleeps until
an answer arrives, and `snapshot()` tells the page what to draw. Nothing in
the snapshot is written by a model at display time: it is the interview
state and the brief.
"""
import json
import queue
import threading
import uuid
from pathlib import Path

from .. import db
from ..grounding import ResearchDesk, get_researcher, new_state, run_interview
from ..grounding.interview import CONFIRM, NOT_CONFIRMED, ONE_QUESTION
from ..model import get_model

CAN_START = ("start", "saved", "stopped", "failed")
HARNESS_LINE = "[harness]"


class GroundingSession:
    """The interview behind the page.

    `model_factory()` returns the model. `desk_factory(conn)` returns the
    research desk for a database connection; by default it is a desk on the
    configured researcher. Both are called on the interview thread, so a
    model or researcher that cannot be set up ends in phase `failed`.

    An SQLite connection belongs to the thread that opened it. `conn` is
    used here, on the caller's thread, to bring the database up to date;
    each interview thread opens its own connection to `config.db_path`.
    """

    def __init__(self, config, conn, model_factory=get_model, desk_factory=None, max_questions: int = 12):
        self.config = config
        self.max_questions = max_questions
        self.state_path = Path(config.db_path).parent / "grounding_state.json"
        self._model_factory = model_factory
        self._desk_factory = desk_factory or (lambda conn: ResearchDesk(get_researcher(config.researcher), conn))
        db.migrate(conn)

        # Everything below is shared with the interview thread and guarded by _changed.
        self._changed = threading.Condition()
        self._phase = "start"
        self._note = ""
        self._transcript: list[dict] = []
        self._pending = None
        self._error = None
        self._state: dict = {}              # the interview state; the interview thread writes it
        self._saved = None                  # {"status", "json", "page"} once a brief is saved
        self._brief = None                  # the saved brief
        self._brief_research: list = []     # the saved brief's lookups, when no interview ran here
        self._desk = None
        self._answers: queue.Queue = queue.Queue()

        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                transcript = _transcript(state["messages"])
            except (ValueError, KeyError, TypeError) as error:
                self._phase, self._error = "failed", f"the saved interview cannot be read: {_one_line(error)}"
            else:
                self._begin(state, transcript)
        else:
            self._show_saved_brief()

    # What the page reads.

    def snapshot(self) -> dict:
        """The state the page draws. Safe to call from any thread, at any time."""
        with self._changed:
            state = self._state
            research = [dict(entry) for entry in list(state.get("research", []))] or list(self._brief_research)
            for query in self._desk.looking() if self._desk else []:
                research.append({"query": query, "status": "looking", "name": "", "definition": "",
                                 "sources": [], "origin": "", "cached": False,
                                 "planned": self._note.startswith("reading up on")})
            proposed = state.get("proposed")
            if proposed is not None:
                brief, brief_status = proposed, "proposed"
            elif self._phase == "saved":
                brief, brief_status = self._brief, self._saved["status"]
            else:
                brief, brief_status = None, None
            return {
                "phase": self._phase,
                "note": self._note if self._phase == "working" else "",
                "transcript": [dict(line) for line in self._transcript],
                "pending": self._pending,
                "research": research,
                "brief": brief,
                "brief_status": brief_status,
                "saved": dict(self._saved) if self._phase == "saved" else None,
                "questions": state.get("questions", 0),
                "max_questions": self.max_questions,
                "error": self._error,
                "session_id": state.get("session_id", ""),
            }

    def wait(self, timeout: float | None = 5) -> dict:
        """Sleep until the harness stops being busy (or `timeout` seconds pass). Returns the snapshot."""
        with self._changed:
            self._changed.wait_for(lambda: self._phase != "working", timeout)
        return self.snapshot()

    # What the page sends. Each returns True if it applied, False if nothing was waiting for it.

    def start(self, opening: str) -> bool:
        """Begin a new interview with the person's opening statement."""
        opening = opening.strip()
        with self._changed:
            if self._phase not in CAN_START or not opening:
                return False
            state = new_state(uuid.uuid4().hex, opening)
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")   # resumable from here on
            self._begin(state, [{"who": "you", "text": opening}], opening=opening)
        return True

    def answer(self, text: str) -> bool:
        """Answer the waiting question."""
        return self._send("question", text.strip(), shown=True)

    def accept(self) -> bool:
        """Accept the brief awaiting confirmation."""
        return self._send("confirm", "/accept")

    def request_changes(self, text: str) -> bool:
        """Say what should change in the brief awaiting confirmation."""
        return self._send("confirm", text.strip(), shown=True)

    def wrap(self) -> bool:
        """Finish now, with what there is."""
        return self._send("question", "/wrap")

    def stop(self) -> bool:
        """Stop for now. The interview resumes the next time a session is created."""
        return self._send("question", "/quit") or self._send("confirm", "/quit")

    def _send(self, phase: str, text: str, shown: bool = False) -> bool:
        with self._changed:
            if self._phase != phase or not text:
                return False
            if shown:
                self._transcript.append({"who": "you", "text": text})
            self._phase, self._pending, self._note = "working", None, ""
            self._answers.put(text)
            self._changed.notify_all()
        return True

    # The interview thread.

    def _begin(self, state: dict, transcript: list, opening: str | None = None) -> None:
        """Start the interview thread on `state`. The caller holds the lock, or is the constructor."""
        self._state, self._transcript = state, transcript
        self._phase, self._note, self._pending, self._error = "working", "", None, None
        self._saved, self._brief, self._brief_research, self._desk = None, None, [], None
        self._answers = queue.Queue()       # a fresh one: no answer meant for an earlier interview
        threading.Thread(target=self._run, args=(state, self._answers, opening),
                         name="grounding-interview", daemon=True).start()

    def _run(self, state: dict, answers: queue.Queue, opening: str | None) -> None:
        conn = None
        try:
            conn = db.connect(self.config.db_path)
            if opening is not None:
                db.record_event(conn, session_id=state["session_id"], kind="grounding.answer",
                                actor="person", payload={"text": opening})
            desk = self._desk_factory(conn)
            with self._changed:
                self._desk = desk
            saved = run_interview(
                model=self._model_factory(), researcher=desk, conn=conn, state=state,
                ask=lambda text: self._ask(text, answers), say=self._say,
                brief_dir=self.config.brief_dir, state_path=self.state_path,
                max_questions=self.max_questions)
            brief = _read_brief(saved["json"]) if saved else None
        except Exception as error:      # the state file stays, so the interview can be resumed
            self._finish("failed", error=f"{type(error).__name__}: {_one_line(error)}")
        else:
            if saved is None:
                self._finish("stopped")
            else:
                self._finish("saved", saved=saved, brief=brief)
        finally:
            if conn is not None:
                conn.close()

    def _finish(self, phase: str, error=None, saved=None, brief=None) -> None:
        with self._changed:
            self._phase, self._error, self._saved, self._brief = phase, error, saved, brief
            self._pending, self._note = None, ""
            self._changed.notify_all()

    def _ask(self, text: str, answers: queue.Queue) -> str:
        """Hand a question to the page, and sleep until its answer arrives."""
        with self._changed:
            if text == CONFIRM:
                self._phase = "confirm"         # the brief is in state["proposed"]
            else:
                line = {"who": "harness", "text": text}
                if self._transcript[-1:] != [line]:     # on resume the waiting question is already there
                    self._transcript.append(line)
                self._phase, self._pending = "question", text
            self._note = ""
            self._changed.notify_all()
        return answers.get()

    def _say(self, text: str) -> None:
        with self._changed:
            words = text.strip()
            if words.startswith("(") and words.endswith(")"):
                self._note = words[1:-1]        # "(thinking)", "(looking up: x)", "(reading up on: a, b)"
            elif self._state.get("proposed") is None:       # else: the terminal summary of the brief
                self._transcript.append({"who": "harness", "text": text})

    def _show_saved_brief(self) -> None:
        """With no interview under way, show the brief saved earlier, if there is one."""
        json_path = Path(self.config.brief_dir) / "domain_brief.json"
        try:
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            meta = saved.pop("meta")
            self._saved = {"status": meta["status"], "json": str(json_path),
                           "page": str(json_path.with_suffix(".md"))}
        except (OSError, ValueError, KeyError, AttributeError):
            return          # no brief, or not one this harness wrote
        self._brief, self._phase = saved, "saved"
        self._state = {"session_id": meta.get("session_id", "")}
        self._brief_research = [
            {"query": lookup.get("query", ""), "status": "found" if lookup.get("found") else "not_found",
             "name": lookup.get("name", ""), "definition": lookup.get("definition", ""),
             "sources": lookup.get("sources", []), "origin": lookup.get("origin", ""),
             "planned": False, "cached": False}
            for lookup in meta.get("lookups", []) if isinstance(lookup, dict)]


def _read_brief(json_path) -> dict:
    """The saved brief, without the details of how it was saved."""
    brief = json.loads(Path(json_path).read_text(encoding="utf-8"))
    brief.pop("meta", None)
    return brief


def _transcript(messages: list[dict]) -> list[dict]:
    """What the person and the harness said to each other, rebuilt from saved messages.

    Left out: `[harness]` lines, tool calls, and a reply the person never
    saw because it was sent back for holding more than one question.
    """
    lines = []
    for message, following in zip(messages, [*messages[1:], {}]):
        content = message.get("content") or ""
        if message["role"] == "user":
            text = content.split("\n\n" + HARNESS_LINE)[0]
            if text.strip() and not text.startswith(HARNESS_LINE):
                lines.append({"who": "you", "text": text})
        elif message["role"] == "assistant" and not message.get("tool_calls"):
            if content.strip() and following.get("content") != ONE_QUESTION:
                lines.append({"who": "harness", "text": content})
        elif message["role"] == "tool" and content.startswith(NOT_CONFIRMED):
            lines.append({"who": "you", "text": content[len(NOT_CONFIRMED):]})
    return lines


def _one_line(error) -> str:
    return " ".join(str(error).split())
