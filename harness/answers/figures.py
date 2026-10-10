"""Figures (SPEC 5.2, ARCHITECTURE.md 3.4): where each number or date in a reply came from.

`figures` reads a text with the number check's own reading (`provenance.trace`) and maps what it finds
to the Figure of the state document. Only a figure whose source is a module run gets a `step`; the page
draws those as numbers that lead to their step.
"""
from ..calc.provenance import trace, unbacked


def figures(text: str, sources: list[tuple], *, step_of_run=None, input_of=None) -> list[dict]:
    """One Figure per number or date the number check reads in `text`, in order of appearance.

    `sources` are as `trace` takes them, in order of preference (the first of a label wins).
    `step_of_run(run_id)` gives the step id a run's module carries out, or None; `input_of(written)` gives
    the brief input id a saved input backs a figure for, or None. Without them a figure has no step or input.
    """
    found = []
    for item in trace(text, sources):
        step = run = input_id = None
        if item["source"] == "run" and item["run_id"] is not None:
            step = step_of_run(item["run_id"]) if step_of_run else None
            run = f"r{item['run_id']}"
        elif item["source"] == "input" and input_of is not None:
            input_id = input_of(item["text"])
        found.append({"start": item["start"], "end": item["end"], "text": item["text"],
                      "step": step, "run": run, "input": input_id})
    return found


def input_backing(written: str, saved: list[tuple[str | None, object]]) -> str | None:
    """The brief input id of the latest saved input with an id whose value backs `written`, else None.
    `saved` is `(input id or None, value)`, in the order the inputs were saved."""
    backing = [input_id for input_id, value in saved if input_id and not unbacked(written, [value])]
    return backing[-1] if backing else None
