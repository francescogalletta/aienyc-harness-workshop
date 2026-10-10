# Step 4: human in the loop

Paste everything below the line into your coding agent, from the root of
this repository.

---

You are building step 4 of a small agent harness. Steps 0, 1, 2 and 3 are
already built under `harness/`. The repository holds the contract, the
tests, and the given files for this step. Your job is to write the code that
makes the step 4 tests pass without breaking the earlier steps.

Read these first, in this order:

1. `SPEC.md`, section 1 (the ground rules), section 5.9 (the agent) and
   section 8 (step 4: human in the loop). Section 8 is the contract for this
   step. Follow its names, signatures, messages, events and behaviour
   exactly. It changes some things from 5.9 and says so (8.6).
2. `harness/`, to see what steps 0 to 3 built and how it is written. Read the
   given files as well: `harness/calc/aside.md` (the instructions of the side
   assistant), `harness/calc/analyst.md` (revised for this step: it now tells
   the agent about assumptions, gates and `ask_decision`),
   `harness/ui/evidence.html` (the page you will serve) and `examples/` (the
   data you will run).
3. `tests/step4/`. These tests are the definition of done.

Then build what section 8 describes:

- `harness/migrations/0006_decisions.sql` (exactly as in 8.1)
- `harness/calc/decisions.py` (decision records, the gate block, the decision block and how an answer is read, 8.1 to 8.3)
- `harness/calc/aside.py` (side conversations: the wrapped `ask` and `say`, one side conversation, its context and its limits, 8.5)
- the changes to `harness/calc/agent.py`: the assumption gate, the `ask_decision` tool, the build decision, the carried texts and the wrapped `ask` and `say` (8.2 to 8.6)
- the `decisions` command, and the `aside>` prompt of the terminal `ask`, in `harness/__main__.py` (8.7)
- the two new expectations of `harness/replay.py`, `decisions` and `asides` (6.4, 6.5)
- the changes to `harness/ui/evidence.py`: the new traced kinds and the new `person` sources (8.9)

Rules:

- Do not edit `SPEC.md`, anything under `tests/`, `workshop/`,
  `reference/` or `examples/`, or the given files: `harness/calc/aside.md`,
  `harness/calc/analyst.md`, `harness/ui/evidence.html`, and the earlier given
  files. The only edits allowed in earlier files are the ones section 8
  specifies. If you believe a given file is wrong, stop and say so instead of
  changing it.
- Build only step 4. Do not start on anything in section 9 of `SPEC.md`.
- Use only the Python standard library.
- Do not run the `claude` command yourself, and do not make any network
  call. Every test runs offline, with the scripted model. `replay` and the
  seeded scenarios call a real model: leave them to a person.
- The harness enforces the five things listed at the top of section 8. The
  prompt does not: do not try to make the harness guess a judgment call the
  agent never put to the person.
- Nothing under `harness/` may name an example. The examples are data.
- Keep it small and readable. People will read this code on a projector.
  No abstractions beyond what the contract asks for.

When you think you are done, run:

```
python -m pytest tests/step4
python -m pytest -q
```

(Put `uv run` in front if the project is set up with uv, or use `python3` in
place of `python` if that is what your machine has.)

Every test must pass, including those of steps 0, 1, 2 and 3. Then report,
briefly: the files you created or changed, the test result, and anything in
the contract you found unclear or had to guess.
