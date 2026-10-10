"""SPEC 2.5: the terminal driver maps typed lines to the same actions the page sends."""
import threading

import pytest

from harness.core import NO_ROUTE
from harness.terminal import NOT_HERE, NOTHING_TO_CONFIRM, NOTICE_PROMPT, Terminal
from layer0_helpers import SETTLE, fake_layer, routes_all


class Person:
    """Types the given lines, then ends the input."""
    def __init__(self, *lines):
        self.lines, self.prompts, self.printed = list(lines), [], []

    def read(self, prompt):
        self.prompts.append(prompt)
        if not self.lines:
            raise EOFError
        return self.lines.pop(0)

    def write(self, text):
        self.printed.append(text)


def drive(session, *lines, stop=None):
    person = Person(*lines)
    state = Terminal(session, read=person.read, write=person.write, wait=0.05).run(stop)
    return person, state


def recorder(calls, name):
    return lambda core, payload: calls.append((name, payload))


def test_each_message_is_printed_once_with_who_said_it(open_session):
    session = open_session(fake_layer(1, route=routes_all(lambda work, message: work.post("an answer"))))
    person, _ = drive(session, "a question", "another")
    assert person.printed.count("you: a question") == 1
    assert person.printed.count("assistant: an answer") == 2
    assert person.printed.index("you: a question") < person.printed.index("assistant: an answer")


def test_without_a_route_the_harness_line_is_printed(open_session):
    person, _ = drive(open_session(), "hello")
    assert f"harness: {NO_ROUTE}" in person.printed


def test_quit_stops_before_the_rest_of_the_input(open_session):
    person, state = drive(open_session(), "/quit", "never sent")
    assert state["chat"] == [] and person.lines == ["never sent"]


@pytest.mark.parametrize("typed, action, payload", [
    ("/accept", "accept_plan", {}),
    ("/wrap", "wrap", {}),
    ("/build", "build", {}),
    ("/side what does this mean", "side", {"text": "what does this mean"}),
])
def test_commands_map_to_actions(open_session, typed, action, payload):
    calls = []
    session = open_session(fake_layer(1, actions={name: recorder(calls, name)
                                                  for name in ("accept_plan", "wrap", "build", "side")}))
    drive(session, typed)
    assert calls == [(action, payload)]
    assert session.state()["chat"] == []


def test_a_command_whose_layer_is_off_says_so(open_session):
    person, _ = drive(open_session(), "/build")
    assert NOT_HERE in person.printed


def test_confirm_goes_to_the_latest_open_notice(open_session):
    calls = []
    session = open_session(fake_layer(1, actions={"confirm_assumptions": recorder(calls, "confirm")}))
    person, _ = drive(session, "/confirm")
    assert NOTHING_TO_CONFIRM in person.printed and calls == []
    session.post("old", data={"notice": {"assumptions": [], "steps": [], "status": "confirmed"}})
    latest = session.post("new", data={"notice": {"assumptions": [{"id": "a1", "text": "It stays at 150."}],
                                                  "steps": ["s1"], "status": "open"}})
    person, _ = drive(session, "/confirm")
    assert calls == [("confirm", {"message": latest})]
    assert person.printed.index("  ◌ It stays at 150.") < person.printed.index(NOTICE_PROMPT)


def test_a_decision_is_printed_with_its_options_numbered(open_session):
    session = open_session()
    session.post("Only you can decide this.", kind="decision",
                 data={"decision": {"id": "d1", "options": ["Keep the date", "Move it"], "status": "open"}})
    person, _ = drive(session)
    assert person.printed[:3] == ["assistant: Only you can decide this.", "  1. Keep the date", "  2. Move it"]


def test_thread_messages_are_printed_indented(open_session):
    def threads(view, state):
        state["threads"] = [{"id": "t1", "kind": "side", "step": None, "title": "x", "status": "open",
                             "messages": [{"who": "you", "text": "why?"}, {"who": "assistant", "text": "because"}]}]

    person, _ = drive(open_session(fake_layer(1, contribute=threads)))
    assert person.printed == ["  side | you: why?", "  side | assistant: because"]


def test_activity_text_is_printed_when_it_changes(open_session):
    person, shown = Person("look"), threading.Event()
    person.write = lambda text: (person.printed.append(text), text == "  (looking things up)" and shown.set())

    def working(work, message):
        work.progress("looking things up")
        shown.wait(SETTLE)                  # the job goes on once the driver has printed its activity
        work.post("found")

    session = open_session(fake_layer(1, route=routes_all(working)))
    Terminal(session, read=person.read, write=person.write, wait=0.05).run()
    assert person.printed.index("you: look") < person.printed.index("  (looking things up)") < \
        person.printed.index("assistant: found")


def test_stop_ends_the_driver_without_reading(open_session):
    person, _ = drive(open_session(), "never read", stop=lambda state: True)
    assert person.prompts == []
