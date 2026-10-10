# Build plan

The harness is a core and five layers. `STEPS.md` lists the files of each step.

| Step | Principle | Built | Proof on the main example | Command |
| --- | --- | --- | --- | --- |
| 0 | The core knows no layer | Nothing: the core, the model interface, the database and the page are given | `harness check` talks to a model; the page opens empty | `at 0` |
| 1 | An interview agrees the plan | `harness/grounding/`: interview, research, the plan, corrections | The wedding plan drawn as a diagram, every item with its origin | `at 1` |
| 2 | Every number comes from a tested module | `harness/calc/`: the unattended build, second-pass check, test gate, registry | Delete one module: its step shows `Stale · rebuild`, the build makes it, `4 examples · 4/4` | `at 2` |
| 3 | Answers with evidence | `harness/answers/`: the analyst, the number check, figures | "Can I cover each wedding payment?" gives 43,000 and 54,500; each number leads to its step | `at 3` |
| 4 | The harness needs you only where the call is yours | `harness/needs_you/`: marks, calls, automatic builds, side threads | An answer on an unsaid split is marked `◌`; confirm, then change it to 40/60 (14,800 and 22,200) | `at 4` |
| 5 | A reviewer challenges the plan | `harness/review/`: the reviewer, challenges | Challenges on steps; use one, dismiss one | `at 5` |

`at N` shows the finished harness at step N. To build a step yourself, use `start N`, the prompt `prompts/stepN_*.md` and `uv run pytest tests/layerN -q`; `finish N` catches up. The guide is `README.md`.
