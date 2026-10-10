"""The second pass (SPEC 4.5): an independent model call works out each example's answer.

It is given the spec's name, description, method, formula, inputs and output,
and each example's number and inputs. It is never given the expected answers,
the working, the example writer's messages, the brief, the notes, the person's
words, other modules or any code. The comparison with the expected answers is
made here, after the call.
"""
import json
from pathlib import Path

from ..model import ToolSpec
from .provenance import unbacked
from .values import from_json, same

GIVEN_SPEC = ("name", "description", "method", "formula", "inputs", "output")
ANSWER_EXAMPLES = ToolSpec(
    name="answer_examples",
    description="Give your own answer to every example, each with its working, worked out from the spec alone.",
    input_schema={"type": "object", "properties": {"answers": {"type": "array", "items": {
        "type": "object", "properties": {"n": {"type": "integer"}, "answer": {}, "working": {"type": "string"}},
        "required": ["n", "answer", "working"]}}}, "required": ["answers"]})


def checker_request(spec: dict, examples: list[dict]) -> str:
    """The one user message the checker gets: the spec and the examples' numbers and inputs, nothing else."""
    shown_spec = {key: spec[key] for key in GIVEN_SPEC if key in spec}
    shown = [{"n": each["n"], "inputs": each["inputs"]} for each in examples]
    return (f"[spec]\n{json.dumps(shown_spec, indent=2, ensure_ascii=False)}\n\n"
            f"[examples]\n{json.dumps(shown, indent=2, ensure_ascii=False)}")


NO_ANSWER = "no answer"
NO_FIT = "does not fit the output type"
UNBACKED = "numbers its working does not show: {numbers}"
DIFFERS = "a different answer"


def _problem(found, kind: str, inputs) -> str:
    """Why an answer does not count, or "": it must fit the output type, and every number in it must be in its
    working or in the example's inputs (a date or an amount copied from the inputs is not made up)."""
    if not isinstance(found, dict) or "answer" not in found or not isinstance(found.get("working"), str):
        return NO_ANSWER
    try:
        from_json(found["answer"], kind)
    except ValueError:
        return NO_FIT
    missing = unbacked(json.dumps(found["answer"], ensure_ascii=False), [found["working"], inputs])
    return UNBACKED.format(numbers=", ".join(missing)) if missing else ""


def check_examples(model, spec: dict, examples: list[dict]) -> list[dict]:
    """One model call. Returns `[{"n", "agrees", "answer", "why", "given"}]` in the order of `examples`.

    `examples` are `{"n", "inputs", "expected", ...}`; only `n` and `inputs` reach the model. `answer` is
    the checker's answer when it counts (else None); `agrees` is true when it counts and is the same as
    `expected` (`values.same`). A failed call, a reply without the tool, or a missing or malformed answer
    leaves an example out. `why` says why an example is left out ("" when it agrees); `given` is what the
    checker sent for it, as it came, for the record."""
    answers = {}
    try:
        response = model.complete(system=Path(__file__).with_name("checker.md").read_text(encoding="utf-8"),
                                  messages=[{"role": "user", "content": checker_request(spec, examples)}],
                                  tools=[ANSWER_EXAMPLES])
        calls = [call for call in response.tool_calls if call.name == ANSWER_EXAMPLES.name]
        given = calls[0].arguments.get("answers") if calls else None
    except Exception:           # a failed call checks nothing: every example is left out
        given = None
    for each in given if isinstance(given, list) else []:
        n = each.get("n") if isinstance(each, dict) else None
        n = int(n) if isinstance(n, str) and n.strip().isdigit() else n     # "2" is taken as 2
        if isinstance(n, int) and not isinstance(n, bool) and n not in answers:
            answers[n] = each
    kind = spec["output"]["type"]
    results = []
    for example in examples:
        found = answers.get(example["n"])
        problem = _problem(found, kind, example["inputs"])
        if problem:
            results.append({"n": example["n"], "agrees": False, "answer": None, "why": problem, "given": found})
            continue
        agrees = same(example["expected"], found["answer"])
        results.append({"n": example["n"], "agrees": agrees, "answer": found["answer"],
                        "why": "" if agrees else DIFFERS, "given": found})
    return results
