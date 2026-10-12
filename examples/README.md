# Examples

One seeded example. It is one folder with a confirmed brief, built and
tested modules, and scenarios (SPEC sections 2.6 and 3.1):

```
examples/<name>/
  brief/domain_brief.json     the confirmed brief (an origin on every item)
  modules/<module>/           spec.json, golden.json, module.py, tests.py
  scenarios/<scenario>.json   a scripted person and what the harness must see
```

`brief/domain_brief.md` is not kept: the harness writes the page when it
saves a brief, and it is written again when the example is loaded.

| Example | Domain | Modules | Worked examples |
| --- | --- | --- | --- |
| `wedding` | Paying a wedding on time from income, savings and a family gift. | 6: the five calculation steps `s1`, `s2`, `s3`, `s5`, `s6`, and `cost_per_guest_all_in`, a step added in a conversation that is not in the brief | 24 |

Nothing under `harness/` names an example. It is data.

## How it was made, and how far to trust it

The brief was brought to the current shape by hand from an earlier format,
without changing its substance. Every item has an origin. Where the earlier
brief quoted the person, the origin is that quote; a source it cited is
`looked_up`; everything else is `proposed` by the assistant. Particulars and open questions
name the step they concern, or none for the whole plan. The wedding brief
is the one the first real interview wrote.

The modules were built by an earlier version of the build pipeline, with a
real model. Every
worked example (24) was recomputed by an AI agent in a separate
throwaway script that does not import the module's code, and every example
matched. So each `golden.json` entry says `"checked_by": "second_pass"`.
**No person has confirmed them.** A person should still go through every
`golden.json` with a calculator before relying on them.

## Play with one

`HARNESS_EXAMPLE=<name>` points the harness at the example. The harness never
writes into `examples/`: it copies the example's `brief/` and `modules/` to
`my/var/examples/<name>/` and works on the copy. Delete that folder to start
again.

## Scenarios

A scenario is a scripted person (SPEC 2.6): lines said to the main chat and actions (confirm, correct, choose, side,
branch, accept, decline, close, use, dismiss), played against the configured model in a scratch copy under `my/var/replay/`, at the scenario's layer.
`uv run python -m harness replay wedding` (or one scenario: `replay wedding review_the_plan`) prints one
line per expectation and exits 0 only when all pass; `--keep` keeps the scratch copy. Each run uses the real model:
expect about 30 seconds for a build and one to two minutes for a conversation (a whole example takes 2 to 7 minutes).
Figures are worked out by hand, not with the modules.

| Example | Scenario | Layer | What it plays |
| --- | --- | --- | --- |
| `wedding` | `build_monthly_surplus` | 2 | the module of step `s3` removed; an unattended build makes it again, the others are kept |
| `wedding` | `cover_each_payment` | 3 | 150 to 200 guests: totals 43,000 and 54,500, the 200-guest shortfall 5,250 at the second payment |
| `wedding` | `no_family_contribution` | 3 | no gift: shortfalls 24,500 (200 guests) and 13,000 (150) at the third payment |
| `wedding` | `confirm_and_correct` | 4 | an answer resting on an unsaid split is marked; the person confirms, then changes it (40/60: 14,800 and 22,200) and it is run again |
| `wedding` | `decide_what_to_update` | 4 | the review step `s7` is the person's call; they answer by option |
| `wedding` | `branch_that_joins` | 4 | 120 guests (first payment "due 21 days from today"): total 36,100. From the Guest count chip a branch says "no fewer than 150"; the proposal is accepted, the branch joins as a `value` decision and steps 1 and 2 run again (43,000; 18,500 each) |
| `wedding` | `branch_that_dies` | 4 | a branch on step 5 asks what a sinking fund is; nothing is proposed, the person closes it: dead, no decision recorded |
| `wedding` | `review_the_plan` | 5 | review passes (the first on load, a second after an answer that rests on an unsaid split) raise challenges; one is used, the next dismissed (counts and states only) |

The reviewer and the analyst vary between runs, so a scenario that fails once deserves a second run before it is
believed; one that fails every time points at the harness.
