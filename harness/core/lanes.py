"""Work lanes (ARCHITECTURE.md 4.2): main, side and review, one job at a time each.

A lane is a thread with a FIFO queue. Its state is `idle` (nothing running or
queued), `working`, or `waiting` (main lane only: the running job waits on the
person). Every field here is guarded by the session's condition; the session
runs each job, outside that lock.
"""
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

LANES = ("main", "side", "review")


@dataclass
class Job:
    """One job on a lane. `run(work)` does the work. A job made for a person's message typed while
    the main lane was busy has `message` set instead: it is routed when the lane comes to it, unless
    a waiting job takes the message first."""
    what: str
    run: Callable | None = None
    step: str | None = None
    thread: str | None = None           # the thread a side job answers, once it has one
    text: str = ""
    since: str = ""
    key: str | None = None              # at most one job with this key waits in the queue
    message: dict | None = None
    data: dict = field(default_factory=dict)


class Lane:
    def __init__(self, name: str, session):
        self.name = name
        self.queue: deque[Job] = deque()
        self.running: Job | None = None
        self.waiting: dict | None = None    # what the running job waits on the person for
        self.answer = None              # what the person (or an action) answered, until the job takes it
        self._session = session
        self.thread = threading.Thread(target=self._loop, name=f"harness-{name}", daemon=True)

    @property
    def state(self) -> str:
        if self.waiting is not None:
            return "waiting"
        return "working" if self.running is not None or self.queue else "idle"

    def take_message(self) -> Job | None:
        """Remove and return the oldest queued person message, if there is one."""
        for job in self.queue:
            if job.message is not None:
                self.queue.remove(job)
                return job
        return None

    def _loop(self) -> None:
        session = self._session
        while True:
            with session._cond:
                while not self.queue and not session._closed:
                    session._cond.wait()
                if session._closed:
                    return
                job = self.queue.popleft()
                self.running = job
                session._started(job)
            try:
                session._run(self, job)
            finally:
                with session._cond:
                    self.running, self.waiting, self.answer = None, None, None
                    session._changed_locked()
