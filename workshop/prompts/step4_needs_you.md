# Step 4: when the harness needs you

Paste everything below the line into your coding agent, from the root of this repository.

---

You are building layer 4 of a small agent harness, the Financial Advisor Harness. Steps 0 to 3 are built. The repository holds the contract, the tests and the given files for this layer. Write the code that makes the layer 4 tests pass without breaking the earlier layers.

What this layer does:

Nothing blocks unless the call is the person's. An assumption is run and marked; the person confirms or changes it. A call that is the person's stops and asks, with options. A calculation the plan lacks is built automatically and shown as not in the plan. A side thread is a branch about one thing in the plan: the side assistant answers there and may propose a change to a figure or to the plan, but nothing changes until the person says yes. Then the branch joins the trunk of decisions, the runs the value reaches are run again through the gate, and the analyst is told. A branch that changes nothing dies and stays on the page, dimmed.

Read these first, in this order:

1. `SPEC.md`: section 1 (ground rules), then section 6 (when the harness needs the person, 6.1 to 6.6). Follow its names, signatures, templates and behaviour exactly.
2. `ARCHITECTURE.md`: section 2 (files and layers), then 3.3 to 3.5 (`unconfirmed`, `calls`, decisions, threads, the decision history and proposals), 4, 12.2, 12.3, 12.5 and 12.6, and the notes marked A4a, A4b, B2, D4a and D4b in section 9.
3. `harness/core/` and `harness/layers.py`, to see what the core offers a layer, and the earlier layers' packages, to see how they are written.
4. `tests/layer4/`. These tests are the definition of done.

Build these files, all in `harness/needs_you/`:

- `__init__.py`: a docstring only
- `calls.py`: decisions that wait for the person
- `join.py`: proposals and their checks, the actions `accept_proposal`, `decline_proposal` and `close_branch`, the join job and the death of a branch
- `layer.py`: `LAYER`: the state contribution, the tools, the actions `choose`, `confirm_assumptions`, `side` and the three of `join.py`, hooks, replay expectations
- `marks.py`: assumptions, notices, confirm and correct
- `requests.py`: `request_module`, the automatic build of a missing calculation
- `schema.sql`: the `assumptions`, `run_assumptions`, `decisions` and `proposals` tables
- `side.py`: the side assistant, the `side` action and the tool `propose_change`

Given files (do not edit; read them):

- `harness/needs_you/analyst.md`
- `harness/needs_you/side.md`
- `harness/ui/page.html` and everything else in the core

Rules:

- Edit only the files listed above. Do not edit `SPEC.md`, `ARCHITECTURE.md`, anything under `tests/`, `design/`, `examples/`, `workshop/` or `my/`, the given files, or the core (`harness/core/`, `harness/model/`, `harness/ui/` and the top-level files). If you believe one of them is wrong, stop and say so.
- Layer 4 imports only layers below 4. It never reads `config.layers`, never writes another layer's tables, and never names an example (no "wedding").
- A number reaches the person only from a tested module, a saved input, the plan, their own words or today's date. Do not add a path around the test gate or the number check.
- Use only the Python standard library. Do not run the `claude` command or make a network call: every test runs offline with the scripted model.
- Do not read the git history of `harness/`: it holds the finished code.
- Keep it small and readable. People will read this code on a projector.

Done means this layer's tests pass and the earlier layers still pass. Run each folder on its own (two `tests/layer*` folders in one run share the name `conftest`):

```
uv run pytest tests/layer4 -q
uv run pytest tests/layer3 -q
uv run pytest tests/layer2 -q
uv run pytest tests/layer1 -q
uv run pytest tests/layer0 -q
```

Tests of layers above this one fail until they are built; that is expected. Then try it on the main example. An answer on an unsaid split is marked `◌`; confirm it, then change it to 40/60. Then open a branch from the Guest count chip, say "We will get no fewer than 150 guests", and say yes to the proposal; `examples/wedding/scenarios/branch_that_joins.json` is that run.

When you think you are done, report briefly: the files you created, the test results, and anything in the contract you found unclear or had to guess.
