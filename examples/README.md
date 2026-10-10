# Examples

Two complete seeded examples. Each is one folder with a confirmed brief,
built and tested modules, and scenarios (SPEC section 6.1):

```
examples/<name>/
  brief/domain_brief.json     the confirmed brief
  brief/domain_brief.md       the same brief as a page
  modules/<module>/           spec.json, golden.json, module.py, tests.py
  scenarios/<scenario>.json   a scripted person and what the harness must see
```

| Example | Domain | Modules | Worked examples |
| --- | --- | --- | --- |
| `wedding` | Paying a wedding on time from income, savings and a family gift. The same brief as `brief/`. | 6: the five calculation steps `s1`, `s2`, `s3`, `s5`, `s6`, and `cost_per_guest_all_in`, a step the agent asked for in a conversation and that is not in the brief | 24 |
| `moving` | Saving for a move to another city: deposit, van hire, months of overlapping rent. | 3: `m1`, `m2`, `m3` | 13 |

Nothing under `harness/` names an example. They are data.

## How they were made, and how far to trust them

**Wedding.** The brief is a byte-for-byte copy of `brief/` as it was when
the example was made. The modules were built by the real pipeline
(`python -m harness build`) in a live run with a real model: the model wrote
each plan, made-up examples and code, and the harness ran the tests. In that
run the worked examples were accepted without being checked.

**Moving.** The brief was written by hand, then checked with `validate_brief`
and saved with `save_brief`, so the page is the project's own rendering. Its
glossary terms and sources come from `reference/terms.json`. Its modules were
built with `HARNESS_EXAMPLE=moving python -m harness build`, typing `yes` to
every plan and every example. One module, `monthly_saving_needed`, was built
again after the plan check, with the words "round up to the next whole cent",
because the first plan left an unrounded answer.

**The check that was done afterwards.** Every worked example of every module
(24 and 13) was recomputed by an AI agent, in a separate throwaway script
that does not import the module's code. The script works the answer out from
the spec's formula and the example's inputs (with `decimal`, and `datetime`
and `calendar` for dates) and compares it with `golden.json`. The same script
was also run against the modules on thousands of random inputs. Every
example matched. In the wedding modules only wording changed: the
descriptions no longer tell the person how to type a date (the project's
"never tell them how to type a value" rule), and the payment schedule's
formula now says halves round up. That changes those modules' fingerprints,
which is fine because nothing is registered yet.

**This is not a human check.** No person has yet checked these worked
examples by hand. `adopt` says "checked by hand, but not by you", which is
true of the person adopting; a person should still go through every
`golden.json` with a calculator before relying on them.

## Play with one

`HARNESS_EXAMPLE=<name>` points the harness at the example: its brief, its
modules, and a database of its own under `var/examples/<name>/`.

```
HARNESS_EXAMPLE=moving uv run python -m harness adopt     # once: register the modules
HARNESS_EXAMPLE=moving uv run python -m harness modules
HARNESS_EXAMPLE=moving uv run python -m harness ask       # needs a model
HARNESS_EXAMPLE=moving uv run python -m harness work      # the evidence page
```

`adopt` shows each module's worked examples and asks you to type `yes`. Then
it runs their tests and registers the ones that pass. The database is kept
between runs. Files are not copied: a `build` with an example set writes
into `examples/`, and git shows it.

## Replay

A scenario is a scripted person. `replay` runs it against the configured
model, in a scratch folder under `var/replay/`, and checks module runs and
numbers, never wording.

```
uv run python -m harness replay wedding                         # every scenario
uv run python -m harness replay wedding cover_each_payment      # one
uv run python -m harness replay moving --keep                   # keep the scratch folder, open it with work
```

Each model call takes 20 to 60 seconds, so an `ask` scenario takes a few
minutes and a `build` scenario about five. It prints one `PASS` or `FAIL` line
per check, with what it saw, and ends with `N of M scenarios passed.`

The seeded scenarios:

| Example | Scenario | Kind | Checks |
| --- | --- | --- | --- |
| `wedding` | `cover_each_payment` | ask | A range of 150 to 200 guests is run as two cases (43,000 and 54,500), and the 200-guest shortfall of 5,250 comes from a module |
| `wedding` | `no_family_contribution` | ask | The forecast runs with a contribution of 0, and shows shortfalls of 24,500 (200 guests) and 13,000 (150 guests) |
| `wedding` | `build_monthly_surplus` | build | A missing module for `s3` is built again; the others are kept |
| `moving` | `upfront_and_monthly` | ask | Upfront cost 4,660 and the monthly saving 308.58 over 7 months |
| `moving` | `months_at_current_saving` | ask | Upfront cost 4,430 feeds the months module |
| `moving` | `build_months_to_save` | build | A missing module for `m3` is built again; the others are kept |
| `wedding` | `decide_what_to_update` | ask | After the forecast the agent puts step `s7` (what to update first) to the person as a judgment call, and the decision is recorded |
| `wedding` | `aside_before_asking` | ask | A side conversation at the opening question (one, of one turn), then the full question: the cost still comes from a module |
| `moving` | `keep_or_move_date` | ask | After the months figure the agent puts step `m4` (keep the move date or move it) as a judgment call |
| `moving` | `aside_before_asking` | ask | A side conversation at the opening question (one, of one turn), then the full question: the upfront cost still comes from a module |

## Write a scenario

One JSON file, `scenarios/<name>.json`, with `<name>` in snake_case
(SPEC 6.4 has every rule):

```json
{"name": "upfront_cost",
 "kind": "ask",
 "description": "What it checks, in one sentence.",
 "today": "2026-10-09",
 "lines": ["How much do I need before the move? Deposit 2,000, van 450, two months of overlap at 1,100.", "yes", "yes"],
 "expect": {"runs": [{"module": "move_upfront_cost", "inputs": {"deposit": "2000"}}],
            "shown": ["4,650"], "max_withheld": 0}}
```

- `kind` is `ask` or `build`. `today` fixes the date of an `ask`, so the
  expected dates and months never change. `without` lists steps whose modules
  are left out, so a `build` has something to build.
- `lines` is what the person types, in order. Give every figure in the first
  line, so a sensible agent needs nothing more, then add plain `yes` lines
  for its say-back questions, its assumption gates and its decisions. A line
  that starts with `/aside` opens a side conversation wherever it lands. When
  the lines run out the person types `/quit`: that is a no at a gate, "something
  else" at a decision, and the end of a conversation anywhere else.
- `expect` is about module runs and numbers. `runs` lists modules and the
  inputs they must have been run with. `shown` lists numbers a reply must
  show, at the precision you write them (`"4,583"` is seen in `4,583.33`).
  `decisions` (step 4) lists what the person must have decided, each as a
  `kind` (`assumptions`, `judgment` or `build`) with, optionally, a `step`, a
  `choice` and a `count`. `asides` (step 4) gives how many side conversations
  were `opened` and how many `turns` were taken in them.
  `steps` says what a `build` did with a step: `built`, `reused`, `kept` or
  `not_built`. A bare whole number from 0 to 12 cannot be in `shown`, so
  check it through the inputs of a run instead.
- **Say a decision by its kind and step, never its choice.** Which line lands
  on a decision depends on the model, and the options are model-written. A
  `yes` that lands on a decision takes the suggestion when there is one.
  Open a side conversation at the first question, before the agent has said
  anything: it is the one place a line is sure to land.
  Give the first line everything the judgment rests on (the move is in 7
  months, for instance). An agent that has to ask for a missing figure asks
  in plain words, and a `yes` does not answer it.
- **Work out every expected number yourself**, with a script that does not
  import the modules. A scenario that copies the module's answer proves
  nothing.
- Replay it twice. If it fails because the agent wanted something your lines
  did not say, change the lines. If it fails because the harness did
  something wrong, keep the scenario honest and fix the harness.

## Add an example

1. Choose a name matching `^[a-z][a-z0-9_]*$` and make `examples/<name>/`.
2. Write the brief, either with the interview
   (`HARNESS_EXAMPLE=<name> uv run python -m harness ground`) or by hand: it
   must pass `validate_brief`, every glossary source must be a source some
   lookup returned, and the page must be what `save_brief` writes.
3. Build the modules: `HARNESS_EXAMPLE=<name> uv run python -m harness build`.
4. Check every worked example in every `golden.json` yourself, with a script
   that does not import the module's code. Fix any example that is wrong, and
   any spec whose formula was ambiguous for it, then run `adopt` again.
5. Run `HARNESS_EXAMPLE=<name> uv run python -m harness modules`: every module
   must be `unchanged` and `passed`. Delete a `_build` folder if one is left.
6. Write at least one `ask` and one `build` scenario, one `ask` scenario whose
   `decisions` names a `judgment` step of the brief, and one with `asides`.
   Replay each until it passes twice in a row.
