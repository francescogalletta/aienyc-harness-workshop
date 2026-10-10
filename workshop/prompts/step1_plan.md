# Step 1: the plan

Paste everything below the line into your coding agent, from the root of this repository.

---

You are building layer 1 of a small agent harness, the Financial Advisor Harness. Step 0 (the core, the model interface, the database, the terminal, replay and the page) is given. The repository holds the contract, the tests and the given files for this layer. Write the code that makes the layer 1 tests pass without breaking the earlier layers.

What this layer does:

An interview that agrees the plan with the person, and draws it. The plan is a brief: goal, standard terms with sources, the person's particulars, inputs and steps, each item with an origin. The layer reads up on terms through a research desk, proposes the plan, takes corrections that carry a step, and revises an accepted plan.

Read these first, in this order:

1. `SPEC.md`: section 1 (ground rules), then section 3 (the plan, 3.1 to 3.5). Follow its names, signatures, templates and behaviour exactly.
2. `ARCHITECTURE.md`: section 2 (files and layers), then 3.1, 3.2 and 3.5 (the state document), 4.3 (the Layer object) and the notes marked A0 and A1 in section 11.
3. `harness/core/` and `harness/layers.py`, to see what the core offers a layer, and the earlier layers' packages, to see how they are written.
4. `tests/layer1/`. These tests are the definition of done.

Build these files, all in `harness/grounding/`:

- `__init__.py`: a docstring only
- `brief.py`: the plan's shape and checks, `draw` (the layer's keys of the state document), `load_brief`, the step fingerprint, input ids
- `claude_code_research.py`: web lookups through Claude Code
- `interview.py`: the interview loop on the main lane
- `layer.py`: `LAYER`: the state contribution, the actions `start`, `accept_plan` and `wrap`, routing, the `ground` command, hooks
- `research.py`: lookups, the researchers, the research desk, `look_up_general`
- `revise.py`: `revise_plan`
- `schema.sql`: the `lookups` table

Given files (do not edit; read them):

- `harness/grounding/interviewer.md`
- `harness/grounding/planner.md`
- `harness/grounding/researcher.md`
- `harness/ui/page.html` and everything else in the core

Rules:

- Edit only the files listed above. Do not edit `SPEC.md`, `ARCHITECTURE.md`, anything under `tests/`, `design/`, `examples/`, `workshop/` or `my/`, the given files, or the core (`harness/core/`, `harness/model/`, `harness/ui/` and the top-level files). If you believe one of them is wrong, stop and say so.
- Layer 1 imports only layers below 1. It never reads `config.layers`, never writes another layer's tables, and never names an example (no "wedding").
- A number reaches the person only from a tested module, a saved input, the plan, their own words or today's date. Do not add a path around the test gate or the number check.
- Use only the Python standard library. Do not run the `claude` command or make a network call: every test runs offline with the scripted model.
- Do not read the git history of `harness/`: it holds the finished code.
- Keep it small and readable. People will read this code on a projector.

Done means this layer's tests pass and the earlier layers still pass. Run each folder on its own (two `tests/layer*` folders in one run share the name `conftest`):

```
uv run pytest tests/layer1 -q
uv run pytest tests/layer0 -q
```

Tests of layers above this one fail until they are built; that is expected. Then try it on the main example. `HARNESS_EXAMPLE=wedding uv run python -m harness ui` draws the seeded plan. If you are stuck, `uv run python -m workshop finish 1` restores the finished layer from git (your files are set aside first).

When you think you are done, report briefly: the files you created, the test results, and anything in the contract you found unclear or had to guess.
