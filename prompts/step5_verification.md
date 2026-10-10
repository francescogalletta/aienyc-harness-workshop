# Step 5: verification

Paste everything below the line into your coding agent, from the root of
this repository.

---

You are building step 5 of a small agent harness. Steps 0, 1, 2, 3 and 4 are
already built under `harness/`. The repository holds the contract, the
tests, and the given files for this step. Your job is to write the code that
makes the step 5 tests pass without breaking the earlier steps.

Read these first, in this order:

1. `SPEC.md`, section 1 (the ground rules), sections 5.8 and 5.9 (the number
   check and the agent), section 8 (decisions and side conversations) and
   section 9 (step 5: verification). Section 9 is the contract for this
   step. Follow its names, signatures, messages, events and behaviour
   exactly. It changes some things from 5.9 and 8 and says so (9.7).
2. `harness/`, to see what steps 0 to 4 built and how it is written. Read the
   given files as well: `harness/calc/verifier.md` (the instructions of the
   verifier), `harness/calc/analyst.md` (revised for this step: it now tells
   the agent how to raise a finding), `harness/ui/evidence.html` (the page you
   will serve, with its new Data view), `data/example/` (account files in two
   formats, which the adapter must read as they are) and `examples/` (the
   wedding example now has account files in `examples/wedding/data/` and
   scenarios that load them).
3. `tests/step5/`. These tests are the definition of done.

Then build what section 9 describes:

- `harness/migrations/0007_data.sql` (exactly as in 9.1)
- `harness/sources/__init__.py` and `harness/sources/adapter.py` (reading an
  account file into one table: delimiter, heading row, column roles, date and
  number formats, repeated rows, the sign convention, 9.2)
- `harness/sources/summaries.py` (the data summaries: full calendar months,
  own transfers, the four measures, 9.4)
- `harness/calc/findings.py` (a figure, when two figures disagree, the finding
  block, opening and closing a finding, 9.5)
- `harness/calc/verifier.py` (the sub-agent loop and the checks the harness
  makes on everything it reports, 9.6)
- the changes to `harness/calc/agent.py`: the verifier after each person
  message, findings kept open, `save_input` over a saved value, `ask_decision`
  with `finding`, and the sources of the number check (9.7)
- the fourth decision kind, `finding`, in `harness/calc/decisions.py` (8.1)
  and the `data` label in `harness/calc/provenance.py` (7.1)
- `data add`, `data list` and `data clear`, and `verify=True` for `ask`, in
  `harness/__main__.py` (9.3)
- the new keys and expectations of `harness/replay.py`: `verify`, `data`,
  `findings` and `max_findings` (6.4, 6.5)
- the changes to `harness/ui/evidence.py` and `harness/ui/server.py`: the
  `data` label, three summary keys and one path (9.9)

Rules:

- Do not edit `SPEC.md`, anything under `tests/`, `data/`, `prompts/`,
  `reference/` or `examples/`, or the given files: `harness/calc/verifier.md`,
  `harness/calc/analyst.md`, `harness/ui/evidence.html`, and the earlier given
  files. The only edits allowed in earlier files are the ones section 9
  specifies. If you believe a given file is wrong, stop and say so instead of
  changing it.
- Build only step 5.
- Use only the Python standard library.
- Do not run the `claude` command yourself, and do not make any network
  call. Every test runs offline, with the scripted model. `replay` and the
  seeded scenarios call a real model: leave them to a person.
- The harness enforces the five things listed at the top of section 9. The
  prompt does not: do not try to make the harness find a disagreement that
  the verifier never reported, and do not let the agent add a word to a
  finding block.
- No model ever reads an account file. Only the adapter does, and only
  tested code summarises what it read.
- Nothing under `harness/` may name an example. The examples are data.
- Keep it small and readable. People will read this code on a projector.
  No abstractions beyond what the contract asks for.

When you think you are done, run:

```
python -m pytest tests/step5
python -m pytest -q
```

(Put `uv run` in front if the project is set up with uv, or use `python3` in
place of `python` if that is what your machine has.)

Every test must pass, including those of steps 0, 1, 2, 3 and 4. Then report,
briefly: the files you created or changed, the test result, and anything in
the contract you found unclear or had to guess.
