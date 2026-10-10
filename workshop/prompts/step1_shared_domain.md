# Step 1: shared domain

Paste everything below the line into your coding agent, from the root of
this repository.

---

You are building step 1 of a small agent harness. Step 0 is already built
under `harness/`. The repository holds the contract, the tests, and the
given files for this step. Your job is to write the code that makes the
step 1 tests pass without breaking step 0.

Read these first, in this order:

1. `SPEC.md`, section 1 (the ground rules) and section 4 (step 1). Section 4
   is the contract for this step. Follow its names, signatures, messages and
   behaviour exactly.
2. `harness/`, to see what step 0 built and how it is written.
3. `tests/step1/`. These tests are the definition of done.

Then build what section 4 describes:

- three new settings in `harness/config.py`
- `harness/grounding/__init__.py`
- `harness/grounding/research.py` (lookups, the researchers and their table, the research desk, the research plan)
- `harness/migrations/0002_lookups.sql`
- `harness/grounding/claude_code_research.py` (web lookups through Claude Code)
- `harness/grounding/brief.py` (the brief's shape, checks and output)
- `harness/grounding/interview.py` (the interview loop)
- `harness/ui/__init__.py`, `harness/ui/session.py` and `harness/ui/server.py` (the web interface's backend)
- the `ground` and `ui` commands in `harness/__main__.py`
- the small change to `harness/model/claude_code_provider.py` that section 4.2 asks for

Rules:

- Do not edit `SPEC.md`, anything under `tests/`, `workshop/` or
  `reference/`, or the given files: the three `.md` files in
  `harness/grounding/` and `harness/ui/grounding.html`. If you believe one of them is wrong,
  stop and say so instead of changing it.
- Build only step 1. Do not start on anything in section 5 of `SPEC.md`.
- Use only the Python standard library.
- Do not run the `claude` command yourself, and do not make any network
  call. Every test runs offline.
- Keep it small and readable. People will read this code on a projector.
  No abstractions beyond what the contract asks for.

When you think you are done, run:

```
python -m pytest -q
```

(Put `uv run` in front if the project is set up with uv, or use `python3` in
place of `python` if that is what your machine has.)

Every test must pass, including the step 0 tests. Then report, briefly: the
files you created or changed, the test result, and anything in the contract
you found unclear or had to guess.
