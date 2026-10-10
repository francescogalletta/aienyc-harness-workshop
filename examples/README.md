# Examples

Two seeded examples. Each is one folder with a confirmed version 2 brief,
built and tested modules, and scenarios (SPEC sections 2.6 and 3.1):

```
examples/<name>/
  brief/domain_brief.json     the confirmed brief, version 2 (an origin on every item)
  modules/<module>/           spec.json, golden.json, module.py, tests.py
  scenarios/<scenario>.json   a scripted person and what the harness must see
```

`brief/domain_brief.md` is not kept: the harness writes the page when it
saves a brief, and it is written again when the example is loaded.

| Example | Domain | Modules | Worked examples |
| --- | --- | --- | --- |
| `wedding` | Paying a wedding on time from income, savings and a family gift. | 6: the five calculation steps `s1`, `s2`, `s3`, `s5`, `s6`, and `cost_per_guest_all_in`, a step added in a conversation that is not in the brief | 24 |
| `moving` | Saving for a move to another city: deposit, van hire, months of overlapping rent. | 3: `m1`, `m2`, `m3` | 13 |

Nothing under `harness/` names an example. They are data.

## How they were made, and how far to trust them

The briefs were converted by hand from the version 1 briefs, without changing
their substance. Every item has an origin. Where the old brief quoted the
person, the origin is that quote; a source the old brief cited is `looked_up`;
everything else is `proposed` by the assistant. Particulars and open questions
name the step they concern, or none for the whole plan. The wedding brief
is the one the first real interview wrote; the moving brief was written by hand.

The modules were built by the version 1 pipeline with a real model. Every
worked example (24 and 13) was recomputed by an AI agent in a separate
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

A scenario is a scripted person (SPEC 2.6). Each carries a `layer`. The
scenario files are still written for version 1 and package A6 rewrites them.

| Example | Scenario | Layer | Kind |
| --- | --- | --- | --- |
| `wedding` | `cover_each_payment` | 3 | ask |
| `wedding` | `no_family_contribution` | 3 | ask |
| `wedding` | `build_monthly_surplus` | 2 | build |
| `wedding` | `decide_what_to_update` | 4 | ask |
| `wedding` | `aside_before_asking` | 4 | ask |
| `moving` | `upfront_and_monthly` | 3 | ask |
| `moving` | `months_at_current_saving` | 3 | ask |
| `moving` | `build_months_to_save` | 2 | build |
| `moving` | `keep_or_move_date` | 4 | ask |
| `moving` | `aside_before_asking` | 4 | ask |
