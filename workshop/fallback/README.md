# Fallbacks: every block with no model and no network

Each folder is a kept run in the form the harness opens: `harness.db`, `brief/`, `modules/` and `LAYER` (the step to run at). They hold no absolute paths and are about 400 KB each. Open one:

```
workshop/fallback/open.sh 3-answers            # then browse to http://127.0.0.1:8765/ ; Ctrl+C stops it
workshop/fallback/open.sh 5-review 8765 4      # the same run one layer lower: the "before" (steps without the challenges)
```

`open.sh` copies the folder to `my/var/fallback/<block>` and runs `harness ui` on the copy with `HARNESS_LAYERS`, `HARNESS_DB`, `HARNESS_BRIEF_DIR` and `HARNESS_MODULES_DIR` set, `HARNESS_REVIEW=off` and `HARNESS_MODEL_PROVIDER=scripted`, so nothing calls a model. The page can be read and clicked; typing a new question has no model to answer it. A lower layer hides that layer's marks, but the chat text stays.

| Folder | Block | What the page shows | Made by |
| --- | --- | --- | --- |
| `0-setup` | 0 | Empty shell | nothing to keep |
| `1-plan` | 1 | The seeded wedding plan, accepted | `examples/wedding/brief` and `modules` |
| `2-build` | 2 | `All 6 built`, examples and tests per step; step 3 rebuilt | `harness replay wedding build_monthly_surplus --keep` |
| `3-answers` | 3 | Answer with underlined numbers, 43,000 and 54,500, shortfall 5,250 (the scenario fixes today at 15 January 2027) | `replay wedding cover_each_payment --keep` |
| `4-marks` | 4 | The `◌` notice open, with Confirm and Change it | a live page run of the block 4 sentence (not a replay) |
| `4-marks-corrected` | 4 | After confirming and changing to 40/60: 14,800 and 22,200 | `replay wedding confirm_and_correct --keep` |
| `4-branch-proposal` | 4 | A branch from the Guest count chip, open: "We will get no fewer than 150 guests." with "Change guest count to 150?", the steps it would re-run, **Yes, change it** and **Keep 120**; trunk still 36,100 | kept in a live page run of the block 4 branch sentences, before pressing Yes |
| `4-branch-joined` | 4 | The same run after Yes: 43,000 on step 1 with `re-ran` on steps 1, 2 and 5, old figures struck through, a trunk node, and the dimmed dead branch "What is a sinking fund?" | the same live run, after Yes and after closing the second branch (`replay wedding branch_that_joins --keep` makes the join without the dead branch) |
| `4-call` | 4 | Step 7 `Decided` with the record | `replay wedding decide_what_to_update --keep` (it does not pass every run; keep a passing one) |
| `5-review` | 5 | `Review · 3`, `▲` on steps, one used and one dismissed thread | `replay wedding review_the_plan --keep` |

To remake one: run the replay, copy `brief`, `modules` and `harness.db` from the `kept:` folder it prints (under `my/var/replay/`) into `workshop/fallback/<folder>/`, and write the layer in `LAYER`. For a kept run taken from a live page, first run `python3 -c "import sqlite3; sqlite3.connect('harness.db').execute('pragma wal_checkpoint(TRUNCATE)')"` on its database, or the copy lacks the last messages. If `harness/` changes the way a run is stored, remake them and check each one opens and shows what the table says.
