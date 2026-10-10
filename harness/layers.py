"""Layers and their discovery (ARCHITECTURE.md 4.3 and 7).

Each layer package has a `layer.py` whose `LAYER` is a `Layer`. The core is
the only place that knows which layers are on: `enabled(config)` imports the
layer packages in order, up to `config.layers`, and stops at the first one
that is missing. A disabled layer is never imported.
"""
import argparse
import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PACKAGES = ("harness.grounding", "harness.calc", "harness.answers", "harness.needs_you", "harness.review")


@dataclass(frozen=True)
class Command:
    """A subcommand of `python -m harness`. `run(args)` returns the exit code."""
    help: str
    run: Callable[[argparse.Namespace], int]
    arguments: Callable[[argparse.ArgumentParser], None] | None = None


@dataclass(frozen=True)
class Expect:
    """A replay expectation key (SPEC 2.6): `validate(value)` returns an error or None;
    `check(value, context)` returns {"what", "passed", "seen"}."""
    validate: Callable[[Any], str | None]
    check: Callable[[Any, Any], dict]


@dataclass(frozen=True)
class Layer:
    """What one layer plugs into the core. Every field but `number` and `name` may be left out.

    - `schema`: a .sql file of CREATE ... IF NOT EXISTS statements.
    - `contribute(view, state)`: adds this layer's keys to the state document, in layer order.
    - `actions[name](core, payload)`: applies an action; raises `NotNow(reason)` to refuse it,
      `ValueError` for a bad payload.
    - `route(core, message)`: returns a main-lane handler `handler(work, message)` for a person's
      message, or None. A handler may carry a `what` attribute for its activity entry.
    - `tools(turn)`: the analyst tools, as (ToolSpec, handle(turn, call) -> tool result) pairs.
    - `prompt`: a part of the analyst's system prompt; `context(conn)`: its "What you know" sections.
    - `hooks[name]`: `loaded(core)`, `plan_accepted(work)`, `plan_changed(work, changed_steps)`,
      `step_built(work, step_id)`, `turn_finished(work, turn)`.
    - `commands`, `expects`: added to `python -m harness` and to replay.
    """
    number: int
    name: str
    schema: Path | None = None
    contribute: Callable | None = None
    actions: dict[str, Callable] = field(default_factory=dict)
    route: Callable | None = None
    tools: Callable | None = None
    prompt: Path | None = None
    context: Callable | None = None
    hooks: dict[str, Callable] = field(default_factory=dict)
    commands: dict[str, Command] = field(default_factory=dict)
    expects: dict[str, Expect] = field(default_factory=dict)


BASE = Layer(number=0, name="base", schema=Path(__file__).with_name("schema.sql"))


def enabled(config, packages=PACKAGES) -> list[Layer]:
    """The enabled layers, base first: those up to `config.layers`, stopping at the first missing package."""
    found = [BASE]
    for number, package in enumerate(packages, start=1):
        if number > config.layers:
            break
        try:
            module = importlib.import_module(f"{package}.layer")
        except ModuleNotFoundError as error:
            if error.name in (package, f"{package}.layer"):
                break           # this package, or its layer file, is not in this tree
            raise
        layer = module.LAYER
        if layer.number != number:
            raise ValueError(f"{package}.layer says it is layer {layer.number}, not {number}")
        found.append(layer)
    return found
