# Step 2: consistency

Paste everything below the line into your coding agent, from the root of
this repository.

---

You are building step 2 of a small agent harness. Steps 0 and 1 are already
built under `harness/`. The repository holds the contract, the tests, and the
given files for this step. Your job is to write the code that makes the
step 2 tests pass without breaking the earlier steps.

Passages of `SPEC.md` marked "(step M)" for a step later than this one do not apply yet.

Read these first, in this order:

1. `SPEC.md`, section 1 (the ground rules) and section 5 (step 2). Section 5
   is the contract for this step. Follow its names, signatures, messages and
   behaviour exactly.
2. `harness/`, to see what steps 0 and 1 built and how it is written. Read
   the given files in `harness/calc/` as well: `values.py`, `safety.py`,
   `runner.py` and the five `.md` files.
3. `tests/step2/`. These tests are the definition of done.

Then build what section 5 describes.

Build these files (new):

- `harness/calc/__init__.py` (a docstring only)
- `harness/calc/registry.py` (module folders, the spec check, fingerprints, registering)
- `harness/calc/notes.py` (the notes kept during a build)
- `harness/calc/added.py` (the steps the agent adds to the plan, 5.5)
- `harness/migrations/0004_notes.sql` (the notes table, exactly as in 5.5)
- `harness/migrations/0005_added_steps.sql` (the added steps table, exactly as in 5.5)
- `harness/calc/gate.py` (running tests, and the one way a calculation runs)
- `harness/calc/builder.py` (the phases: spec and plan check, worked examples checked by the person, code)
- `harness/calc/provenance.py` (the number check)
- `harness/calc/agent.py` (the agent that answers questions with tested modules)

Change these files (they exist already):

- `harness/config.py` (the `modules_dir` setting, 5.4)
- `harness/__main__.py` (the `build`, `modules` and `ask` commands)
- `harness/calc/safety.py` (given in a starting form: the one change that section 5.2 asks for)
- `harness/calc/runner.py` (given in a starting form: the one change that section 5.3 asks for)

Given files (do not edit):

- `SPEC.md`
- `tests/step2/` (the definition of done)
- `harness/calc/values.py`
- `harness/calc/spec_writer.md`
- `harness/calc/example_writer.md`
- `harness/calc/example_helper.md`
- `harness/calc/module_writer.md`
- `harness/calc/analyst.md`
- `harness/migrations/0003_calc.sql`

Rules:

- Do not edit `SPEC.md`, anything under `tests/`, `workshop/` or `reference/`, or the given files above. In
  the files you change, make only the changes section 5 specifies. If you believe a given file is wrong, stop and
  say so instead of changing it.
- Build only step 2. Do not start on anything in section 6 of `SPEC.md`.
- Use only the Python standard library.
- Do not run the `claude` command yourself, and do not make any network
  call. Every test runs offline.
- Keep it small and readable. People will read this code on a projector.
  No abstractions beyond what the contract asks for.

When you think you are done, run:

```
python -m pytest tests/step2
python -m pytest -q
```

(Put `uv run` in front if the project is set up with uv, or use `python3` in
place of `python` if that is what your machine has.)

Every test must pass, including those of steps 0 and 1. Then report, briefly:
the files you created or changed, the test result, and anything in the
contract you found unclear or had to guess.
