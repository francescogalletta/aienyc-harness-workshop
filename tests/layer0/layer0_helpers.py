"""Helpers for the layer 0 tests: made-up layers."""
from harness.layers import Layer

SETTLE = 5      # seconds; far more than any job here takes


def fake_layer(number: int = 1, **fields) -> Layer:
    return Layer(number=number, name=f"fake {number}", **fields)


def routes_all(handler):
    """A route that hands every message to `handler`."""
    return lambda core, message: handler


# --- A tree of made-up layers, for the tests of replay ---

def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _words(value) -> str | None:
    return None if isinstance(value, list) and all(isinstance(each, str) for each in value) else "must be a list of words"


def _said(words, session) -> dict:
    texts = [message["text"] for message in session.state()["chat"]]
    return {"what": f"said {words}", "passed": all(any(word in text for text in texts) for word in words),
            "seen": f"{len(texts)} messages"}


def _messages(count, session) -> dict:
    seen = len(session.state()["chat"])
    return {"what": f"at least {count} messages", "passed": seen >= count, "seen": f"{seen} messages"}


def _always(value, session) -> dict:
    return {"what": "always", "passed": True, "seen": "yes"}


def made_up_layers():
    """Layers 1 to 5 that stand for the real ones as far as replay can tell. Layer 1 answers every message
    with `heard: <text>` and registers the key `said`; layer 2 has a `build` action that posts `built` and the
    key `counted`; layers 3 to 5 only register a key each (`late`, `later`, `latest`)."""
    from harness.layers import Expect

    def hear(core, message):
        def answer(work, message):
            work.post(f"heard: {message['text']}")
        return answer

    def build(core, payload):
        core.queue("main", lambda work: work.post("built"), what="build")

    return [
        fake_layer(1, route=hear, expects={"said": Expect(_words, _said)}),
        fake_layer(2, actions={"build": build}, expects={"counted": Expect(
            lambda value: None if _whole(value) else "must be a whole number", _messages)}),
        fake_layer(3, expects={"late": Expect(_words, _always)}),
        fake_layer(4, expects={"later": Expect(_words, _always)}),
        fake_layer(5, expects={"latest": Expect(_words, _always)}),
    ]


def install_made_up_layers(monkeypatch, layers=None):
    """Make replay and the session find `layers` (default `made_up_layers()`) instead of the real packages,
    up to the setting HARNESS_LAYERS, as discovery would."""
    from harness.layers import BASE
    layers = made_up_layers() if layers is None else layers

    def discover(config, packages=None):
        return [BASE, *[layer for layer in layers if layer.number <= config.layers]]

    monkeypatch.setattr("harness.replay.enabled", discover)
    monkeypatch.setattr("harness.core.session.enabled", discover)
    return layers
