"""The core (ARCHITECTURE.md section 4, SPEC 2.3): one Session owns the conversation, the waiting
slot, the three lanes and the plan state document. It knows no layer by name.

Front ends (the server, the terminal, replay) use `state()`, `act()`, `settle()` and `close()`.
Layers use the rest: `queue`, `answer`, `post`, `hook`, `new_conversation`, `conn`, `model()`,
and, inside a job, the `Work` object they are given.
"""
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

from .. import db
from ..layers import enabled
from ..model import get_model
from . import state as plan_state
from .lanes import LANES, Job, Lane

NO_ROUTE = "Nothing here can answer that yet."
NOTHING_WAITS = "Nothing is waiting for an answer."
ACTORS = {"you": "person", "assistant": "agent", "reviewer": "agent", "harness": "harness"}
WHO = tuple(ACTORS)
KINDS = ("text", "plan", "decision", "notice", "withheld")


class NotNow(Exception):
    """An action that is not allowed now. Its text is the reason the person or the page is given."""


class BadAction(ValueError):
    """An unknown action, or a payload that is not what the action takes."""


class Closed(BaseException):
    """The session closed while a job waited on the person. Not an Exception, so a job does not catch it."""


@dataclass
class View:
    """What a layer's `contribute(view, state)` reads from."""
    conn: sqlite3.Connection
    config: object
    conversation: str
    session: "Session"
    memory: dict


def one_line(error) -> str:
    text = " ".join(str(error).split())
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


def number_of(ref, prefix: str) -> int:
    """'m12' -> 12. ValueError for anything else."""
    if not isinstance(ref, str) or not ref.startswith(prefix) or not ref[len(prefix):].isdigit():
        raise ValueError(f"not a {prefix} id: {ref!r}")
    return int(ref[len(prefix):])


# --- Messages and threads in the database. Each takes a connection of the calling thread. ---

def add_message(conn, conversation: str, text: str, *, who: str = "assistant", kind: str = "text",
                step: str | None = None, thread: str | None = None, data: dict | None = None) -> str:
    """Store one message and its `core.message` event. Returns its id, 'm<n>'."""
    if who not in WHO:
        raise ValueError(f"who must be one of {', '.join(WHO)}, not {who!r}")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}")
    cursor = conn.execute(
        "INSERT INTO messages (ts, conversation, thread, who, text, step, kind, data)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (db.now(), conversation, number_of(thread, "t") if thread else None, who, text, step, kind,
         json.dumps(data or {})))
    conn.commit()
    message_id = f"m{cursor.lastrowid}"
    db.record_event(conn, session_id=conversation, kind="core.message", actor=ACTORS[who],
                    payload={"id": message_id, "who": who, "kind": kind, "step": step, "thread": thread,
                             "text": text})
    return message_id


def update_message(conn, message_id: str, changes: dict) -> None:
    """Merge `changes` into a message's data (a notice confirmed, a decision answered)."""
    row = conn.execute("SELECT data FROM messages WHERE id = ?", (number_of(message_id, "m"),)).fetchone()
    if row is None:
        raise ValueError(f"there is no message {message_id}")
    conn.execute("UPDATE messages SET data = ? WHERE id = ?",
                 (json.dumps({**json.loads(row["data"]), **changes}), number_of(message_id, "m")))
    conn.commit()


def get_message(conn, message_id: str) -> dict | None:
    try:
        number = number_of(message_id, "m")
    except ValueError:
        return None
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (number,)).fetchone()
    return _message(row) if row is not None else None


def list_messages(conn, conversation: str, thread: str | None = None) -> list[dict]:
    """The main chat (thread None) or one thread of a conversation, oldest first."""
    if thread is None:
        rows = conn.execute("SELECT * FROM messages WHERE conversation = ? AND thread IS NULL ORDER BY id",
                            (conversation,))
    else:
        rows = conn.execute("SELECT * FROM messages WHERE conversation = ? AND thread = ? ORDER BY id",
                            (conversation, number_of(thread, "t")))
    return [_message(row) for row in rows]


def _message(row) -> dict:
    """A Message of the state document. Keys of `data` starting with '_' are the harness's own."""
    message = {"id": f"m{row['id']}", "ts": row["ts"], "who": row["who"], "text": row["text"],
               "step": row["step"], "queued": False, "kind": row["kind"]}
    message.update({key: value for key, value in json.loads(row["data"]).items() if not key.startswith("_")})
    return message


def add_thread(conn, conversation: str, *, kind: str, title: str, step: str | None = None,
               after: str | None = None) -> str:
    """Store a thread. It follows the main-chat message `after`; by default the last one there is now."""
    if after is None:
        last = conn.execute("SELECT MAX(id) FROM messages WHERE conversation = ? AND thread IS NULL",
                            (conversation,)).fetchone()[0]
    else:
        last = number_of(after, "m")
    cursor = conn.execute(
        "INSERT INTO threads (ts, conversation, kind, step, after, title, status)"
        " VALUES (?, ?, ?, ?, ?, ?, 'open')", (db.now(), conversation, kind, step, last, title))
    conn.commit()
    return f"t{cursor.lastrowid}"


def set_thread_status(conn, thread: str, status: str) -> None:
    conn.execute("UPDATE threads SET status = ? WHERE id = ?", (status, number_of(thread, "t")))
    conn.commit()


def list_threads(conn, conversation: str) -> list[dict]:
    """The threads of a conversation with their messages ({"who", "text", and the keys of data})."""
    threads = []
    for row in conn.execute("SELECT * FROM threads WHERE conversation = ? ORDER BY id", (conversation,)):
        thread_id = f"t{row['id']}"
        messages = [{key: value for key, value in message.items() if key not in ("id", "ts", "queued", "kind",
                                                                                  "step")}
                    for message in list_messages(conn, conversation, thread_id)]
        threads.append({"id": thread_id, "kind": row["kind"], "step": row["step"],
                        "after": f"m{row['after']}" if row["after"] is not None else None,
                        "title": row["title"], "status": row["status"], "messages": messages})
    return threads


# --- The session ---

class Session:
    def __init__(self, config, *, model_factory=get_model, desk_factory=None, layers=None, memory=None):
        """Open the database, apply the enabled layers' schemas, load the current conversation,
        start the lanes and run each layer's `loaded` hook.

        `layers` replaces discovery (tests); by default it is `layers.enabled(config)`. `memory` is what
        `self.memory` starts with (replay sets `today` there before any `loaded` hook runs).
        """
        self.config = config
        self.layers = list(layers) if layers is not None else enabled(config)
        self.desk_factory = desk_factory
        self.memory: dict = dict(memory or {})              # in-memory state layers keep for the life of the session
        self._model_factory = model_factory
        self._model = None
        self._local = threading.local()
        self._cond = threading.Condition(threading.RLock())
        self._closed = False
        self._version = 1
        self._error = None
        self._actions = {"say": Session._say}
        for layer in self.layers:
            for name, action in layer.actions.items():
                if name in self._actions:
                    raise ValueError(f"layer {layer.number} registers the action '{name}' a second time")
                self._actions[name] = action

        conn = self.conn
        db.apply_schemas(conn, self.layers)
        row = conn.execute("SELECT value FROM meta WHERE key = 'conversation'").fetchone()
        self._conversation = row["value"] if row is not None else self._store_conversation(conn)

        self.lanes = {name: Lane(name, self) for name in LANES}
        for lane in self.lanes.values():
            lane.thread.start()
        try:
            self.hook("loaded", self)
        except Exception as error:
            self._failed(conn, "loaded", None, None, error)

    # --- For front ends ---

    def state(self) -> dict:
        """The plan state document, rebuilt now (ARCHITECTURE.md section 3)."""
        with self._cond:
            version, error, conversation = self._version, self._error, self._conversation
            lanes = {name: lane.state for name, lane in self.lanes.items()}
            activity = self._activity()
            waiting = dict(self.lanes["main"].waiting) if self.lanes["main"].waiting is not None else None
        with self._connection() as conn:
            document = plan_state.start(version=version, layers=[layer.number for layer in self.layers],
                                        error=error, lanes=lanes, activity=activity, waiting=waiting,
                                        chat=list_messages(conn, conversation))
            view = View(conn=conn, config=self.config, conversation=conversation, session=self,
                        memory=self.memory)
            for layer in self.layers:
                if layer.contribute is not None:
                    layer.contribute(view, document)
        return plan_state.finish(document)

    def act(self, action: str, payload: dict | None = None) -> tuple[bool, str]:
        """Apply one action. (True, "") when applied; (False, reason) when not allowed now.
        Raises BadAction (a ValueError) for an unknown action or a bad payload."""
        payload = {} if payload is None else payload
        if not isinstance(action, str) or action not in self._actions:
            raise BadAction(f"there is no action {action!r}")
        if not isinstance(payload, dict):
            raise BadAction("the payload must be an object")
        with self._cond:
            self._error = None
            self._changed_locked()
        with self._connection() as conn:
            try:
                self._actions[action](self, payload)
            except NotNow as refused:
                return False, str(refused)
            db.record_event(conn, session_id=self.conversation, kind="core.action", actor="person",
                            payload={"action": action, "payload": payload})
        self.changed()
        return True, ""

    def settle(self, timeout: float | None = None) -> dict:
        """Wait until every lane is idle or waiting on the person (or `timeout` seconds pass).
        Returns the state."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while not self._closed and any(lane.state == "working" for lane in self.lanes.values()):
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    break
                self._cond.wait(remaining)
        return self.state()

    def wait_for_change(self, version: int, timeout: float | None = None) -> int:
        """Sleep until `version` is no longer the current one (or `timeout` passes). Returns the current."""
        with self._cond:
            self._cond.wait_for(lambda: self._version != version or self._closed, timeout)
            return self._version

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        for lane in self.lanes.values():
            if lane.thread is not threading.current_thread():
                lane.thread.join(timeout=2)
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # --- For layers ---

    @property
    def conversation(self) -> str:
        with self._cond:
            return self._conversation

    @property
    def version(self) -> int:
        with self._cond:
            return self._version

    @property
    def conn(self) -> sqlite3.Connection:
        """A database connection for the calling thread (inside a job: the job's own)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._local.conn = db.connect(self.config.db_path)
        return conn

    @property
    def waiting(self) -> dict | None:
        """What the main lane waits on the person for, or None."""
        with self._cond:
            waiting = self.lanes["main"].waiting
            return dict(waiting) if waiting is not None else None

    def lane(self, name: str) -> str:
        """'idle', 'working' or 'waiting'."""
        with self._cond:
            return self.lanes[name].state

    def model(self):
        """The model, made on first use and shared by every lane."""
        with self._cond:
            if self._model is None:
                self._model = self._model_factory()
            return self._model

    def queue(self, lane: str, run, *, what: str, step: str | None = None, text: str = "",
              key: str | None = None, thread: str | None = None) -> bool:
        """Queue `run(work)` on a lane. With `key`, nothing is queued while a job with the same key
        waits in that lane's queue (not yet running). Returns whether it was queued."""
        with self._cond:
            found = self.lanes[lane]
            if key is not None and any(job.key == key for job in found.queue):
                return False
            found.queue.append(Job(what=what, run=run, step=step, text=text, key=key, thread=thread))
            self._changed_locked()
        return True

    def answer(self, answer: dict) -> None:
        """Answer what the main lane waits for. Raises NotNow when nothing waits."""
        with self._cond:
            if self.lanes["main"].waiting is None:
                raise NotNow(NOTHING_WAITS)
            self._answer_locked(answer)

    def post(self, text: str, **options) -> str:
        """Add a message to the current conversation (see `add_message`). Returns its id."""
        message_id = add_message(self.conn, self.conversation, text, **options)
        self.changed()
        return message_id

    def update_message(self, message_id: str, changes: dict) -> None:
        update_message(self.conn, message_id, changes)
        self.changed()

    def new_conversation(self) -> str:
        """Start a new conversation (layer 1 does, when an interview starts). Returns its id."""
        conversation = self._store_conversation(self.conn)
        with self._cond:
            self._conversation = conversation
            self._changed_locked()
        return conversation

    def hook(self, name: str, *args) -> None:
        """Call each enabled layer's hook `name`, in layer order, on the calling thread."""
        for layer in self.layers:
            function = layer.hooks.get(name)
            if function is not None:
                function(*args)

    def record(self, kind: str, payload: dict, actor: str = "harness") -> int:
        return db.record_event(self.conn, session_id=self.conversation, kind=kind, actor=actor, payload=payload)

    def changed(self) -> None:
        """Say the state changed (a layer wrote to the database): `version` goes up."""
        with self._cond:
            self._changed_locked()

    # --- Inside the core ---

    def _say(self, payload: dict) -> None:
        """The `say` action (SPEC 2.3): store the person's message, then answer the waiting job,
        or queue it behind the running one, or route it."""
        text, step, notice = payload.get("text"), payload.get("step"), payload.get("notice")
        if not isinstance(text, str) or not text.strip():
            raise BadAction("text must be a non-empty string")
        if step is not None and not isinstance(step, str):
            raise BadAction("step must be a string or null")
        if notice is not None and not isinstance(notice, str):
            raise BadAction("notice must be a string or null")
        text = text.strip()
        busy = self.lane("main") == "working"
        message_id = self.post(text, who="you", step=step, data={"queued": busy, "_notice": notice})
        message = {"id": message_id, "text": text, "step": step, "notice": notice}
        with self._cond:
            main = self.lanes["main"]
            now = main.state
            if now == "waiting":
                self._answer_locked(message)
            elif now == "working":
                main.queue.append(Job(what="answer", step=step, message=message))
                self._changed_locked()
        if now != "working" and busy:
            self.update_message(message_id, {"queued": False})
        if now == "idle":
            self._dispatch(message)

    def _dispatch(self, message: dict) -> None:
        """Give a person's message to the highest layer that routes it, or say nothing can answer."""
        for layer in reversed(self.layers):
            handler = layer.route(self, message) if layer.route is not None else None
            if handler is not None:
                self.queue("main", lambda work: handler(work, message),
                           what=getattr(handler, "what", "answer"), step=message["step"])
                return
        self.post(NO_ROUTE, who="harness")

    def _store_conversation(self, conn) -> str:
        conversation = uuid.uuid4().hex
        conn.execute("INSERT INTO meta (key, value) VALUES ('conversation', ?)"
                     " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (conversation,))
        conn.commit()
        return conversation

    @contextmanager
    def _connection(self):
        """The calling thread's connection; opened here and closed at the end if it had none."""
        if getattr(self._local, "conn", None) is not None:
            yield self._local.conn
            return
        conn = self._local.conn = db.connect(self.config.db_path)
        try:
            yield conn
        finally:
            conn.close()
            self._local.conn = None

    def _changed_locked(self) -> None:
        self._version += 1
        self._cond.notify_all()

    def _answer_locked(self, answer: dict) -> None:
        main = self.lanes["main"]
        main.answer, main.waiting = answer, None
        self._changed_locked()

    def _activity(self) -> list[dict]:
        running = [(name, lane.running) for name, lane in self.lanes.items()
                   if lane.running is not None and lane.waiting is None]
        return [{"lane": name, "what": job.what, "step": job.step, "thread": job.thread, "text": job.text,
                 "since": job.since}
                for name, job in sorted(running, key=lambda pair: pair[1].since)]

    def _started(self, job: Job) -> None:
        job.since = db.now()
        self._changed_locked()

    def _run(self, lane: Lane, job: Job) -> None:
        """Run one job on its lane's thread, with a connection of its own. A job that raises sets
        `error` and records `core.job_failed`; the lane goes on."""
        conn = self._local.conn = db.connect(self.config.db_path)
        work = Work(self, lane, job, conn)
        try:
            run = job.run
            if job.message is not None:          # a person's message that waited for the lane
                self.update_message(job.message["id"], {"queued": False})
                run = self._routed(job)
            if run is not None:
                run(work)
        except Closed:
            pass
        except Exception as error:
            self._failed(conn, job.what, lane.name, job.step, error)
        finally:
            conn.close()
            self._local.conn = None

    def _routed(self, job: Job):
        message = job.message
        for layer in reversed(self.layers):
            handler = layer.route(self, message) if layer.route is not None else None
            if handler is not None:
                job.what = getattr(handler, "what", "answer")
                return lambda work: handler(work, message)
        self.post(NO_ROUTE, who="harness")
        return None

    def _failed(self, conn, what, lane, step, error) -> None:
        line = one_line(error)
        with self._cond:
            self._error = line
            self._changed_locked()
        try:
            db.record_event(conn, session_id=self.conversation, kind="core.job_failed", actor="harness",
                            payload={"lane": lane, "what": what, "step": step, "error": line})
        except sqlite3.Error:
            pass


class Work:
    """What a job gets: its own connection, the model, and ways to report and to wait."""

    def __init__(self, session: Session, lane: Lane, job: Job, conn: sqlite3.Connection):
        self.session, self.conn, self.lane = session, conn, lane.name
        self.config = session.config
        self._lane, self._job = lane, job

    @property
    def model(self):
        return self.session.model()

    @property
    def conversation(self) -> str:
        return self.session.conversation

    def progress(self, text: str, step: str | None = None, what: str | None = None,
                 thread: str | None = None) -> None:
        """Set this job's activity entry (`thread`: the thread being answered)."""
        with self.session._cond:
            self._job.text = text
            if step is not None:
                self._job.step = step
            if what is not None:
                self._job.what = what
            if thread is not None:
                self._job.thread = thread
            self.session._changed_locked()

    def post(self, text: str, **options) -> str:
        """Add a message to the main chat, or to a thread with `thread=`. Returns its id."""
        return self.session.post(text, **options)

    def wait(self, kind: str, **data) -> dict:
        """Main lane only: wait on the person. Sets `waiting` to {"kind": kind, **data} and blocks
        until a message or an action answers. A message typed while this job worked answers at once.
        A message's answer is {"message", "text", "step", "notice"}."""
        if self.lane != "main":
            raise RuntimeError("only a main-lane job waits on the person")
        session = self.session
        with session._cond:
            queued = self._lane.take_message()
            if queued is None:
                self._lane.waiting, self._lane.answer = {"kind": kind, **data}, None
                session._changed_locked()
                while self._lane.answer is None and not session._closed:
                    session._cond.wait()
                if self._lane.answer is None:
                    raise Closed()
                answer, self._lane.answer = self._lane.answer, None
                return answer
            session._changed_locked()
        session.update_message(queued.message["id"], {"queued": False})
        return queued.message

    def queue(self, lane: str, run, **options) -> bool:
        return self.session.queue(lane, run, **options)

    def hook(self, name: str, *args) -> None:
        self.session.hook(name, *args)

    def record(self, kind: str, payload: dict, actor: str = "harness") -> int:
        return db.record_event(self.conn, session_id=self.conversation, kind=kind, actor=actor, payload=payload)

    def changed(self) -> None:
        self.session.changed()

    def desk(self):
        """The research desk on this job's connection, or None when the session was given none."""
        factory = self.session.desk_factory
        return factory(self.conn) if factory is not None else None
