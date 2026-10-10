# Step 3: evidence

Paste everything below the line into your coding agent, from the root of
this repository.

---

You are building step 3 of a small agent harness. Steps 0, 1 and 2 are
already built under `harness/`. The repository holds the contract, the
tests, and the given files for this step. Your job is to write the code that
makes the step 3 tests pass without breaking the earlier steps.

Read these first, in this order:

1. `SPEC.md`, section 1 (the ground rules), section 6 (seeded examples and
   replay) and section 7 (step 3: evidence). Sections 6 and 7 are the
   contract for this step. Follow their names, signatures, messages and
   behaviour exactly. Section 6 changes some things from section 5, and says
   so (6.6).
2. `harness/`, to see what steps 0, 1 and 2 built and how it is written.
   Read the given files as well: `harness/ui/evidence.html` (the page you
   will serve) and `examples/` (the data you will load, adopt and replay).
3. `tests/step3/`. These tests are the definition of done.

Then build what sections 6 and 7 describe:

- the `example` setting and `EXAMPLES_DIR` in `harness/config.py` (6.2)
- `harness/calc/adopt.py` (registering module folders that are already on disk, 6.3)
- `harness/replay.py` (scenarios, their checks, and running them in a scratch folder, 6.4 and 6.5)
- the change to `harness/calc/added.py`: `add_step` can keep a given id (6.6)
- the changes to `harness/calc/agent.py`: `says_yes` for a build request (6.6) and the `ask.started` event (7.2)
- the change to `harness/calc/provenance.py`: `trace` (7.1)
- `harness/ui/evidence.py` (reading the evidence, 7.3)
- the changes to `harness/ui/server.py`: the evidence API and `/work` (7.4 and 7.5)
- the `adopt`, `replay` and `work` commands, the check for an unknown example, the check for unregistered module folders before `build` and `ask`, and the extra line from `ui`, all in `harness/__main__.py` (6.2, 6.6, 6.7 and 7.7)
- the `adopt` reason of a test run (6.6), wherever the code checks the reason

Rules:

- Do not edit `SPEC.md`, anything under `tests/`, `workshop/`,
  `reference/` or `examples/`, or the given files: `harness/ui/evidence.html`
  and `harness/ui/grounding.html`, and the earlier given files. The only
  edits allowed in earlier files are the ones sections 6 and 7 specify. If
  you believe a given file is wrong, stop and say so instead of changing it.
- Build only step 3. Do not start on anything in section 8 of `SPEC.md`.
- Use only the Python standard library.
- Do not run the `claude` command yourself, and do not make any network
  call. Every test runs offline, with the scripted model. `replay` and the
  seeded scenarios call a real model: leave them to a person.
- No model writes any part of the evidence page or reads it. `work` never
  calls a model.
- Nothing under `harness/` may name an example. The examples are data.
- Keep it small and readable. People will read this code on a projector.
  No abstractions beyond what the contract asks for.

When you think you are done, run:

```
python -m pytest tests/step3
python -m pytest -q
```

(Put `uv run` in front if the project is set up with uv, or use `python3` in
place of `python` if that is what your machine has.)

Every test must pass, including those of steps 0, 1 and 2. Then report,
briefly: the files you created or changed, the test result, and anything in
the contract you found unclear or had to guess.
