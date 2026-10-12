# Build plan

The harness is a core and five layers. `STEPS.md` lists the files of each step.

| Step | Principle | Built | Proof on the main example | Command | Fallback (no model) |
| --- | --- | --- | --- | --- | --- |
| 0 | The core knows no layer | Nothing: the core, the model interface, the database and the page are given | `harness check` talks to a model; the page opens empty | `HARNESS_LAYERS=0` | `fallback/open.sh 0-setup` |
| 1 | An interview agrees the plan | `harness/grounding/`: interview, research, the plan, corrections | A live interview proposes a plan you correct (the plan redraws); the seeded wedding plan drawn as a diagram, every item with its origin | `HARNESS_LAYERS=1` | `fallback/open.sh 1-plan` |
| 2 | Every number comes from a tested module | `harness/calc/`: the unattended build, second-pass check, test gate, registry | Delete one module: its step shows `Stale · rebuild`, the build makes it (25 to 35 s), `4 examples · 4/4` or 5 examples | `HARNESS_LAYERS=2` | `fallback/open.sh 2-build` |
| 3 | Answers with evidence | `harness/answers/`: the analyst, the number check, figures | "Can I cover each wedding payment?" gives 43,000 and 54,500; each number leads to its step | `HARNESS_LAYERS=3` | `fallback/open.sh 3-answers` |
| 4 | The harness needs you only where the call is yours | `harness/needs_you/`: marks, calls, automatic builds, side threads | An answer on an unsaid split is marked `◌`; confirm, then change it to 40/60 (14,800 and 22,200) | `HARNESS_LAYERS=4` | `fallback/open.sh 4-marks`, `4-marks-corrected`, `4-call` |
| 5 | A reviewer challenges the plan | `harness/review/`: the reviewer, challenges | Challenges on steps; use one, dismiss one | `HARNESS_LAYERS=5` | `fallback/open.sh 5-review` |

`HARNESS_LAYERS=N` shows the finished harness at step N; stop the page and start it again with the new value, a reload keeps the old step. To build a step yourself, use `start N`, the prompt `prompts/stepN_*.md` and `uv run pytest tests/layerN -q`; `finish N` catches up. The guide is `README.md`.
