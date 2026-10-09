# Build plan

The harness is built in six steps. Step 0 is setup. Steps 1 to 5 each take
one design principle and extend the harness so that it enforces it, then
prove the change on the same example.

Every step has the same four parts:

- **Prompt**: the file in `prompts/` that a coding agent runs.
- **Builds**: what the prompt adds to `harness/`.
- **Proof**: a before and after on the example that an audience can see.
- **Done when**: a test command that passes. Each step has two branches:
  `step-N-start` before it is built and `step-N` after, so anyone can jump to
  either side of any step.

| Step | Principle | Builds | Proof on the example | Done when | Branch |
| --- | --- | --- | --- | --- | --- |
| 0 | (setup) | Model connection with swappable providers (Claude API, Claude Code, scripted), local database | `python -m harness check` talks to a model and leaves one record in the database | `pytest tests/step0` | `step-0` |
| 1 | Shared domain | Grounding interview in a local web page, a research desk that reads up front and never repeats a lookup, the brief's checks, the domain brief | Before: a vague goal. After: a confirmed brief with a glossary, the person's particulars, a plan and a definition of done | `pytest tests/step1` | `step-1` |
| 2 | Consistency | Module builder from the brief, worked examples checked by the person, registry with fingerprints, test gate before every run, run agent with a number check | Before: the model adds up the numbers in its reply. After: it can only call a tested module, and a module with a failing test will not run | `pytest tests/step2` | `step-2` |
| 3 | Evidence | Event recording everywhere, the evidence interface | One number on screen is followed back to its inputs, assumptions and passing tests, with the model switched off | `pytest tests/step3` | `step-3` |
| 4 | Human in the loop | Gates, the side-conversation sub-agent, decision records | An ambiguous input opens a side conversation; the main session receives only the decision | `pytest tests/step4` | `step-4` |
| 5 | Verification | Reference checks at decision points | The budget says one figure and the bank says another; the harness notices and asks | `pytest tests/step5` | `step-5` |

## Status

| Step | Contract | Tests | Prompt | Built and saved |
| --- | --- | --- | --- | --- |
| 0 | Fixed (SPEC 3) | Written | Written | Yes |
| 1 | Fixed (SPEC 4) | Written | Written | Yes |
| 2 | Fixed (SPEC 5) | Written | Written | Yes |
| 3 | Draft (SPEC 6) | Not yet | Not yet | No |
| 4 | Draft (SPEC 6) | Not yet | Not yet | No |
| 5 | Draft (SPEC 6) | Not yet | Not yet | No |

## How a step is prepared

Each step is prepared in this order, and the order matters:

1. Fix that step's section of `SPEC.md`.
2. Write its acceptance tests in `tests/stepN/`.
3. Write its prompt in `prompts/`.
4. Hand the prompt to a coding agent that has seen nothing else, and check
   that it reaches green tests on its own. If it cannot, the prompt or the
   contract is at fault, not the agent.
5. Save the result as the branch `step-N`.

Step 1 leaves one task for a person: running the grounding interview for
real on the example. Its output, the domain brief, decides which
calculations step 2 has to provide.

Step 2 leaves one task for a person: running `build` for real on that brief,
checking each worked example by hand, and committing `modules/` with the
brief. Source adapters are not part of step 2; they come in a later step.

## Running without a live model

Set `HARNESS_MODEL_PROVIDER=scripted` and the harness replays prepared
responses from the file named by `HARNESS_SCRIPT`. Every test uses this, so
the whole suite runs offline, and a demo can fall back to it if the API is
slow on the day.
