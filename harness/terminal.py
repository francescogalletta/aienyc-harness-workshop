"""The terminal driver (SPEC 2.5): a thin front end on a Session, using the same actions as the page.

It prints each new message once, a decision with its options numbered, a
notice with how to answer it, thread messages indented, and the activity text
when it changes. It reads a line whenever the main and side lanes are not
working.
"""
from .core import BadAction

ACTIONS = {"/accept": "accept_plan", "/wrap": "wrap", "/build": "build"}
NOTICE_PROMPT = "Type /confirm, or say what is different."
NOT_HERE = "That is not available here."
NOTHING_TO_CONFIRM = "There is nothing to confirm."
PROMPT = "> "


class Terminal:
    def __init__(self, session, *, read=input, write=print, wait: float = 0.5):
        """`read(prompt)` returns a typed line (EOFError ends the driver); `write(text)` prints one."""
        self.session, self.read, self.write, self.wait = session, read, write, wait
        self._printed: set[str] = set()         # message ids
        self._notices: set[str] = set()         # message ids whose open notice was shown
        self._thread_counts: dict[str, int] = {}
        self._activity: list[str] = []
        self._error = None

    def run(self, stop=None) -> dict:
        """Drive the session until /quit, the end of input, or `stop(state)` is true. Returns the last state."""
        while True:
            state = self.session.state()
            self.show(state)
            if stop is not None and stop(state):
                return state
            if state["lanes"]["main"] == "working" or state["lanes"]["side"] == "working":
                self.session.wait_for_change(state["version"], self.wait)
                continue
            try:
                line = self.read(PROMPT).strip()
            except EOFError:
                return state
            if line == "/quit":
                return state
            if line:
                self.send(line, state)

    def send(self, line: str, state: dict) -> None:
        """Map a typed line to an action and apply it."""
        if line in ACTIONS:
            action, payload = ACTIONS[line], {}
        elif line == "/confirm":
            notice = next((message["id"] for message in reversed(state["chat"])
                           if (message.get("notice") or {}).get("status") == "open"), None)
            if notice is None:
                self.write(NOTHING_TO_CONFIRM)
                return
            action, payload = "confirm_assumptions", {"message": notice}
        elif line == "/side" or line.startswith("/side "):
            action, payload = "side", {"text": line[len("/side"):].strip()}
        else:
            action, payload = "say", {"text": line}
        try:
            applied, reason = self.session.act(action, payload)
        except BadAction:
            self.write(NOT_HERE)
            return
        if not applied:
            self.write(f"harness: {reason}")

    def show(self, state: dict) -> None:
        """Print what is new in `state`."""
        for message in state["chat"]:
            if message["id"] not in self._printed:
                self._printed.add(message["id"])
                self._message(message)
            notice = message.get("notice") or {}
            if notice.get("status") == "open" and message["id"] not in self._notices:
                self._notices.add(message["id"])
                for assumption in notice.get("assumptions", []):
                    self.write(f"  ◌ {assumption['text']}")
                self.write(NOTICE_PROMPT)
        for thread in state.get("threads", []):
            shown = self._thread_counts.get(thread["id"], 0)
            for message in thread["messages"][shown:]:
                self.write(f"  {thread['kind']} | {message['who']}: {message['text']}")
            self._thread_counts[thread["id"]] = len(thread["messages"])
        activity = [entry["text"] for entry in state["activity"] if entry["text"]]
        if activity != self._activity:
            self._activity = activity
            for text in activity:
                self.write(f"  ({text})")
        if state["error"] != self._error:
            self._error = state["error"]
            if self._error:
                self.write(f"error: {self._error}")

    def _message(self, message: dict) -> None:
        self.write(f"{message['who']}: {message['text']}")
        decision = message.get("decision")
        if message["kind"] == "decision" and decision:
            for n, option in enumerate(decision.get("options", []), start=1):
                self.write(f"  {n}. {option}")


def drive(session, *, stop=None, read=input, write=print) -> dict:
    """Run the terminal driver on `session`. Returns the last state."""
    return Terminal(session, read=read, write=write).run(stop)
