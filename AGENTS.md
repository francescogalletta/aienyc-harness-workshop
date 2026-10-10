# Notes for coding agents working in this repository

This is a small agent harness for personal finance, built contract-first for a
two-hour workshop. Read this file first, then `SPEC.md` for the part you are
changing.

## What the repository must serve

Every change is judged against these four uses. Do not make one better by
breaking another.

1. **Presenting.** The facilitator builds the harness live, one principle at a
   time, on the main example (`examples/wedding`), showing what each step
   adds. Each step must run on its own, without the later ones.
2. **Following along.** An attendee runs each step on the main example,
   changes figures and choices, and sees the consequences. They can catch up
   to the current step at any time.
3. **A variation of the main example.** An attendee keeps the same kind of
   plan with their own figures, dates and account files. Their work lives in
   `my/` and nothing we ship may overwrite it.
4. **Their own plan or harness from scratch.** Supported by the contract and
   tests, but not what the session is optimised for: say so plainly rather
   than adding machinery for it.

Everyone leaves with a working harness: `harness/` plus their `my/`, with no
workshop scaffolding mixed in. Deleting `workshop/` must leave a harness whose
tests pass.

## The five principles the harness enforces

1. **Shared domain**: an interview produces a brief (goal, standard terms with
   sources, the person's particulars, steps).
2. **Consistency**: every number comes from a tested module. Modules are built
   only by the explicit build (plan check, worked examples the person
   confirms, code written without seeing them), never while answering.
3. **Evidence**: everything is recorded in the local database, and the
   evidence page reads only from it.
4. **Human in the loop**: gates only on unconfirmed assumptions and judgment
   calls, never on computed numbers; side conversations with their own
   context; decision records.
5. **Verification**: figures the person states are checked against their own
   account files, the brief and their earlier words; the person decides.

## Where things live

| Place | Holds | Who changes it |
| --- | --- | --- |
| `harness/`, `tests/`, `reference/`, `examples/`, `SPEC.md` | The harness, its contract, tests and seeded examples | You, following the contract |
| `my/` | A person's brief, modules and working files | Only the person. Never write here from a build task |
| `workshop/` | Teaching material and step machinery | Only the maintainers |

## Rules that hold everywhere

- `SPEC.md` is the contract. Change the contract first, then tests, then code.
- A number reaches a person only from a tested module, a saved input, the
  brief, their own words or their loaded files. Never add a path around the
  test gate or the number check.
- Nothing under `harness/` names an example domain (no "wedding").
- Only `harness/model/` imports a provider SDK. Standard library first.
- `harness/` never imports `workshop/`. The harness writes only under `my/`.
- Files marked "given" in `SPEC.md` (the `.md` prompts the models read, the
  HTML pages) are not rewritten by a build task.
- Tests run offline with the scripted model: `uv run pytest -q`.
- To check behaviour with the real model, replay a seeded scenario:
  `uv run python -m harness replay wedding`.

## Commands

```
uv run pytest -q                              # all offline tests
uv run python -m harness check                # model access works
uv run python -m harness ui                   # the interview, in the browser
uv run python -m harness build                # build the calculation modules
uv run python -m harness ask "..."            # ask about the plan
uv run python -m harness work                 # show your work
HARNESS_EXAMPLE=wedding uv run python -m harness adopt   # play with a seeded example
```
