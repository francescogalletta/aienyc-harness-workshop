# Build plan

The harness is built in six steps. Step 0 is setup. Steps 1 to 5 each take
one design principle and extend the harness so that it enforces it, then
prove the change on the same example.

Every step has the same four parts:

- **Prompt**: the file in `workshop/prompts/` that a coding agent runs.
- **Builds**: what the prompt adds to `harness/`.
- **Proof**: a before and after on the example that an audience can see.
- **Done when**: a test command that passes.

To move a copy there, run `python -m workshop start N` (the start of step N)
or `finish N` (its end). `next` installs the following step's tests and leaves
your code alone. The reference for each step is stored in `workshop/states/`.

| Step | Principle | Builds | Proof on the example | Done when | Move there |
| --- | --- | --- | --- | --- | --- |
| 0 | (setup) | Model connection with swappable providers (Claude API, Claude Code, scripted), local database | `python -m harness check` talks to a model and leaves one record in the database | `pytest tests/step0` | `start 0`, `finish 0` |
| 1 | Shared domain | Grounding interview in a local web page, a research desk that reads up front and never repeats a lookup, the brief's checks, the example selector (`HARNESS_EXAMPLE`, on the seeded examples' briefs), the domain brief | Before: a vague goal. After: a confirmed brief with a glossary, the person's particulars, a plan and a definition of done | `pytest tests/step1` | `start 1`, `finish 1` |
| 2 | Consistency | Module builder from the brief, worked examples checked by the person, registry with fingerprints, test gate before every run, run agent with a number check, `adopt` for module folders that are already on disk (the seeded examples') | Before: the model adds up the numbers in its reply. After: it can only call a tested module, and a module with a failing test will not run | `pytest tests/step2` | `start 2`, `finish 2` |
| 3 | Evidence | The show-your-work page (`work`) that follows each number to its run, module and tests; seeded example scenarios and `replay` (built) | One number on screen is followed back to its inputs, assumptions and passing tests, with the model switched off | `pytest tests/step3` | `start 3`, `finish 3` |
| 4 | Human in the loop | Built: a gate on unconfirmed assumptions, `ask_decision` for judgment calls, side conversations (`/aside`, `/back`) with their own assistant, decision records | At a gate the person steps aside to ask what a term means; the main conversation receives only the sentence they choose to pass back | `pytest tests/step4` | `start 4`, `finish 4` |
| 5 | Verification | Built: a fixed adapter that reads account files into one table (`data add`, `data list`, `data clear`), data summaries, a verifier sub-agent whose findings the harness checks, findings the person decides in a fixed block before the figure is used | The person says they spend about 5,000 a month and have 10,000 saved; their loaded files show about 5,640 and 9,230. The harness notices, asks, and calculates only with what they decide | `pytest tests/step5` | `start 5`, `finish 5` |

## Status

| Step | Contract | Tests | Prompt | Built and stored |
| --- | --- | --- | --- | --- |
| 0 | Fixed (SPEC 3) | Written | Written | Yes |
| 1 | Fixed (SPEC 4) | Written | Written | Yes |
| 2 | Fixed (SPEC 5) | Written | Written | Yes |
| 3 | Fixed (SPEC 6 and 7) | Written | Written | Yes |
| 4 | Fixed (SPEC 8) | Written | Written | Yes: gates, `ask_decision`, side conversations, decision records, new seeded scenarios |
| 5 | Fixed (SPEC 9) | Written | Written | Yes: account files and their adapter, data summaries, the verifier, findings and their decisions, the Data view, wedding account files and four new scenarios |

Examples are part of three steps: two seeded examples in `examples/`. Their
briefs come with step 1 (with `HARNESS_EXAMPLE`, SPEC 4.8), their modules with
step 2 (with `adopt`, SPEC 5.13, to register them on a fresh clone), and their
scenarios with step 3 (SPEC 6), with `replay` to run them against a real model. Built; see `examples/README.md`, which also lists the
step 4 and step 5 scenarios. The worked examples in `examples/` were
recomputed by an AI agent, not yet by a person.

## How a step is prepared

Each step is prepared in this order, and the order matters:

1. Fix that step's section of `SPEC.md`.
2. Write its acceptance tests in `tests/stepN/`.
3. Write its prompt in `workshop/prompts/`.
4. Hand the prompt to a coding agent that has seen nothing else, and check
   that it reaches green tests on its own. If it cannot, the prompt or the
   contract is at fault, not the agent.
5. Store the result as the reference for step N (`python -m workshop store`, see `DESIGN.md`) and run `python -m workshop check`.

Step 1 leaves one task for a person: running the grounding interview for
real on the example. Its output, the domain brief, decides which
calculations step 2 has to provide.

Step 2 leaves one task for a person: running `build` for real on that brief,
checking each worked example by hand, and committing `my/modules/` with the
brief. Source adapters are not part of step 2; they came in step 5.

## Running without a live model

Set `HARNESS_MODEL_PROVIDER=scripted` and the harness replays prepared
responses from the file named by `HARNESS_SCRIPT`. Every test uses this, so
the whole suite runs offline, and a demo can fall back to it if the API is
slow on the day.
