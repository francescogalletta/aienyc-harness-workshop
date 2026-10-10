# The six steps

Generated from `manifest.json` by `uv run python -m workshop steps --write`; `python -m workshop check` fails when this file is out of date.

| Step | Principle | Package | You build | Given | Test | Then you can run |
|---|---|---|---|---|---|---|
| 0 | 0 the core, which knows no layer | `harness/` | nothing, the core is given | 21 files: `harness/*.py`, `harness/core/`, `harness/model/`, `harness/ui/` | `uv run pytest tests/layer0 -q` | python -m harness check, events, ui |
| 1 | 1 shared domain: an interview agrees the plan | `harness/grounding/` | `__init__.py`, `brief.py`, `claude_code_research.py`, `interview.py`, `layer.py`, `research.py`, `revise.py`, `schema.sql` | `interviewer.md`, `planner.md`, `researcher.md` | `uv run pytest tests/layer1 -q` | python -m harness ground, then ui |
| 2 | 2 consistency: every number comes from a tested module | `harness/calc/` | `__init__.py`, `added.py`, `adopt.py`, `builder.py`, `checker.py`, `gate.py`, `helper.py`, `layer.py`, `notes.py`, `provenance.py`, `registry.py`, `runner.py`, `safety.py`, `schema.sql`, `values.py` | `checker.md`, `example_writer.md`, `module_writer.md`, `spec_writer.md`, `step_helper.md` | `uv run pytest tests/layer2 -q` | python -m harness build, then ui |
| 3 | 3 evidence: answers with figures traced to a step | `harness/answers/` | `__init__.py`, `agent.py`, `figures.py`, `layer.py`, `schema.sql` | `analyst.md` | `uv run pytest tests/layer3 -q` | python -m harness ask, then ui |
| 4 | 4 human in the loop: marks, decisions, side threads | `harness/needs_you/` | `__init__.py`, `calls.py`, `layer.py`, `marks.py`, `requests.py`, `schema.sql`, `side.py` | `analyst.md`, `side.md` | `uv run pytest tests/layer4 -q` | ui: marks, decisions, side threads |
| 5 | 5 verification: a reviewer challenges the figures | `harness/review/` | `__init__.py`, `layer.py`, `reviewer.py`, `schema.sql` | `analyst.md`, `reviewer.md` | `uv run pytest tests/layer5 -q` | ui: the Review view and challenges |
