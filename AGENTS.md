# Notes for coding agents working in this repository

This is a small agent harness for personal finance (the Financial Advisor Harness,
version 2), built contract-first for a two-hour workshop. Read this file
first, then `SPEC.md` and `ARCHITECTURE.md` for the part you are changing.

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
   plan with their own figures and dates. Their work lives in
   `my/` and nothing we ship may overwrite it.
4. **Their own plan or harness from scratch.** Supported by the contract and
   tests, but not what the session is optimised for: say so plainly rather
   than adding machinery for it.

Everyone leaves with a working harness: `harness/` plus their `my/`, with no
workshop scaffolding mixed in. Deleting `workshop/` must leave a harness whose
tests pass.

## Who does what

When a planning model (Claude Fable) is driving a session, it plans, decides
and reviews. It does not make the changes itself.

- **Fable**: sets the direction, makes the top-level design decisions, reviews
  results, and talks with the maintainer. It edits files directly only for a
  change of a few lines.
- **Opus 5.5, as a sub-agent**: turns a direction into a precise contract
  (`SPEC.md`, design documents, the prompts the models read), and takes the
  harder implementation or debugging work.
- **Sonnet 5.5, as a sub-agent**: implementation, tests, documents, data and
  dry runs, working from the contract.

Anything larger than a few lines goes to a sub-agent with a written brief. Use
separate sub-agents for the implementation and for its tests when the change
is to behaviour, so each checks the other against the contract.

## One core, five layers

One core (`harness/core/`) owns the conversation, three work lanes (main, side,
review) and the plan state document. It knows no layer by name. Five layers
plug into it, each one package, each importing only the layers below it.

| Layer | Package | Adds |
| --- | --- | --- |
| 1 the plan | `harness/grounding/` | An interview agrees the plan: goal, standard terms with sources, the person's particulars, steps, each item with an origin |
| 2 build | `harness/calc/` | Every number comes from a tested module. The build runs unattended; a second model pass checks the worked examples; the code writer never sees them |
| 3 answers | `harness/answers/` | Each number in an answer leads to the step that produced it; a number no step produced is held back |
| 4 needs you | `harness/needs_you/` | Assumptions run and are marked; calls that are the person's stop and ask; missing calculations are built; side threads |
| 5 review | `harness/review/` | A reviewer challenges the plan; the person uses or dismisses each challenge |

## Where things live

| Place | Holds | Who changes it |
| --- | --- | --- |
| `SPEC.md`, `ARCHITECTURE.md`, `design/` | The contract, how it is built, the product design and the page source (`design/page/`) | The maintainers, contract first |
| `harness/`, `tests/`, `reference/`, `examples/` | The harness, its tests (`tests/layer0` to `tests/layer5`), saved terms and seeded examples | You, following the contract |
| `my/` | A person's plan, modules and working files | Only the person. Never write here from a build task |
| `workshop/` | Teaching material and the `workshop` command | Only the maintainers |

## Rules that hold everywhere

- `SPEC.md` is the contract, with `ARCHITECTURE.md` sections 3 to 5 (state
  document, core, actions). Change the contract first, then tests, then code.
  Where the design in `design/` differs, the design wins; tell the maintainer.
- The plan state document is the only thing the page and the terminal draw
  from. A feature a layer adds reaches the screen as keys in that document.
- A number reaches a person only from a tested module, a saved input, the
  plan, their own words or today's date. Never add a path around the test gate
  or the number check.
- Layer N imports only layers below N. A test of layer K sets `HARNESS_LAYERS=K`
  and must pass with every later layer off or absent, and never asserts that a
  later layer's key, tool, table or event is missing. Check with
  `uv run python -m workshop check`.
- Nothing under `harness/` names an example domain (no "wedding").
- Only `harness/model/` imports a provider SDK. Standard library first.
- `harness/` never imports `workshop/`. The harness writes only under `my/`.
- Given files are not rewritten by a build task: the `.md` prompts the models
  read, `harness/ui/page.html`, and `reference/`. The page is rebuilt from
  `design/page/` with `python design/page/build_page.py`, never edited by hand.
- Tests run offline with the scripted model: `uv run pytest -q`.
- To check behaviour with the real model, replay a seeded scenario:
  `uv run python -m harness replay wedding`.

## Commands

```
uv run pytest -q                              # all offline tests
uv run pytest tests/layer3 -q                 # one layer's tests (run each folder on its own)
uv run python -m harness check                # model access works
uv run python -m harness ui                   # the page: plan diagram and chat
uv run python -m harness ground               # the interview, in the terminal
uv run python -m harness build                # build the calculation steps of the accepted plan
uv run python -m harness ask "..."            # ask about the plan, in the terminal
uv run python -m harness replay wedding       # play the scripted scenarios against the real model
uv run python -m harness events               # print the recorded events
HARNESS_EXAMPLE=wedding uv run python -m harness ui      # play with a seeded example
HARNESS_LAYERS=3 uv run python -m harness ui             # the harness with layers above 3 off
uv run python -m workshop at 3                # the same, saved in my/var/layers
uv run python -m workshop check               # every step's tests with later layers off (about five minutes)
```
