# Financial Analyst Harness

A small agent harness for (personal) finance, built one layer at a time, and extensible. 

You describe a money goal and the harness draws the plan as a diagram, builds and tests the calculations, and answers your questions with every number traced to a step. 

The running example is a plan to pay for a wedding on time (`examples/wedding/`)

This was built for a workshop for AI Engineer NYC 2026. The five principles behind it, and how each builds on the last: [`workshop/README.md`](workshop/README.md#the-five-principles).

**Taking part in the workshop?** Start at [`workshop/README.md`](workshop/README.md): what to install before you arrive, the five principles and the two ways to follow along. Get the code first:

```
git clone https://github.com/francescogalletta/aienyc-harness-workshop
cd aienyc-harness-workshop
```

The rest of this page describes the harness itself.

## What this is for

The repository serves four uses.

1. **Presenting.** Show the complete harness on the main example, one principle at a time, and what each layer adds.
2. **Following along.** Run the harness on the main example from a fresh clone, change figures and choices, and see what changes.
3. **A variation of the main example.** The same kind of plan with your own figures and dates, kept in `my/`.
4. **Your own plan or harness from scratch.** Supported by the contract and tests, but not what the workshop is made for.

Whichever you choose, you leave with a working harness: the code in `harness/`, your own plan in `my/`, and nothing from the workshop mixed in. Everyone needs model access on their own machine.

## What is here

| Path | What it is |
| --- | --- |
| `SPEC.md`, `ARCHITECTURE.md` | The contract (behaviour, state document, actions) and how it is built |
| `HISTORY.md` | Notes made while the harness was built: history, not contract |
| `design/` | The product design, the design system and the source of the page (`design/page/`) |
| `harness/` | The harness: the core, and one package per layer |
| `tests/` | Offline tests, one folder per layer (`tests/layer0` to `tests/layer5`) |
| `reference/` | Saved finance terms with checked sources, for offline lookups |
| `examples/` | Two seeded examples, `wedding` and `moving`: plan, built modules, scenarios. See `examples/README.md` |
| `my/` | Yours: `my/brief/` (your plan), `my/modules/` (your tested calculations) and `my/var/` (database and working files, never committed) |
| `workshop/` | The workshop guides, exercises, build prompts and slides. Optional: the harness never uses it |

## Set up

Install [uv](https://docs.astral.sh/uv/), a small tool that fetches a suitable Python and keeps everything in a `.venv` folder in the repository. Deleting `.venv` undoes it.

```
curl -LsSf https://astral.sh/uv/install.sh | sh     # macOS or Linux (or: brew install uv)
```

On Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Then you need model access, one of:

- **Claude Code** installed and signed in with your Claude plan. Check with `claude auth status`. Usage counts against your plan. If `ANTHROPIC_API_KEY` is set in your shell, unset it, or it is used instead.
- **An Anthropic API key**: `export ANTHROPIC_API_KEY=...`, and run with `uv run --extra claude`.

`HARNESS_MODEL_PROVIDER` can force `claude_code`, `anthropic` or `scripted` (prepared replies, used by every test). The default `auto` picks `anthropic` when a key and the package are present, else `claude_code`. `HARNESS_MODEL` picks the model; the default is `claude-sonnet-5-5`.

```
uv run python -m harness check
```

It sends the model a one-line test and should end with `Setup works: the model replied and the check was saved as event 1.` It takes a few seconds, up to a minute on a first run.

## Use it

```
uv run python -m harness ui                             # your own plan
HARNESS_EXAMPLE=wedding uv run python -m harness ui     # the main example
```

The page opens in your browser, served from your machine. It has two parts that never change: the plan as a diagram on the left, and on the right the decision graph. Its trunk lists only the decisions that changed the plan (you, the assistant, the harness or the reviewer decided them); beside the trunk are branches, and below it the conversation. Click a step to attach it to your next message, or open its details. Add `--port N` or `--no-browser` if you need to.

Each element on the page takes the colour of the principle that produced it. The legend at the foot of the plan names the five; hover an entry to see only that principle, click to keep it. The table in [`workshop/README.md`](workshop/README.md#the-five-principles) says what to look for under each.

1. **Describe a goal.** On an empty page, say what you want help with. The harness reads up on the finance terms you use, asks one question at a time, and draws a plan. Or open the main example, which starts with an accepted plan.
2. **Accept the plan.** Click a step and say what is wrong to correct it; the diagram redraws. A plan with open questions can still be accepted.
3. **Build.** One button builds every calculation step without stopping, which takes one to four minutes. Each step shows how many worked examples it has and how many tests pass. Examples are checked by a second model pass and are marked "checked by a second pass" until you confirm them.
4. **Ask.** Ask about your plan in the chat. The reply is short; the values it used, what it assumed and what it found are chips under it. Every number leads to the step that produced it, and a number no tested step produced is held back. Hover a chip for a small menu: see it in the diagram, challenge or correct it, or open a branch about it.
5. **Marks and your calls.** An answer that rests on something you did not confirm carries a mark: confirm it or change it. A call that is yours to make stops and asks, with options as buttons or in your own words. A calculation the plan lacks is built for you and shows as "not in the plan".
6. **Branches.** A branch is a side conversation about one thing in the plan: open it from a chip ("challenge or correct", "talk about it") or with "New branch" after clicking a step. If you say something that would change one of your figures ("we will get no fewer than 150 guests"), the branch proposes the change and shows what it touches. Nothing changes until you say yes; then the branch joins the trunk as a decision and the steps it reaches run again through the same test gate, with no model call. A branch that changes nothing (a question about a term) stays on the page, dimmed, and never joins.
7. **Review.** After the plan is accepted a reviewer looks for weak assumptions and challenges them, each as a branch on a step. Choose "use this" (the branch joins the trunk) or "dismiss" (it stays, dimmed). It never blocks. The **Review** toggle shows the challenged steps.

Your work is kept in `my/` (or, with `HARNESS_EXAMPLE`, in a copy under `my/var/examples/<name>/`; delete that folder to start the example again). Do not type account numbers or passwords into the chat.

**In a terminal instead.** The same actions, as text:

```
uv run python -m harness ground          # the interview; /accept, /wrap, /quit
uv run python -m harness build           # build the calculation steps of the accepted plan
uv run python -m harness ask "..."       # ask; /confirm, /side TEXT, /reply TEXT, /yes, /no, /close, /quit
uv run python -m harness events          # everything recorded
```

## For maintainers

**Lookups.** The harness checks `reference/terms.json` first and asks Wikipedia only for terms the file does not know. Only a short general term is sent, never your figures. Set `HARNESS_RESEARCHER=reference` to stay offline. The reviewer's outside lookups also need Wikipedia to be reachable.

### Check a change

Tests run offline with the scripted model: `uv run pytest -q` (about 700 tests, about a minute). They are in `tests/layer0` to `tests/layer5`, and the tests of layer K pass with layers above K off.

To see a change with the real model, replay a seeded scenario, a scripted person playing against it:

```
uv run python -m harness replay wedding                       # every scenario of the example
uv run python -m harness replay wedding cover_each_payment    # one; add --keep to keep the scratch copy
```

It prints a line per expectation and exits 0 only when all pass. A scenario takes 30 seconds to two minutes, a whole example 2 to 7 minutes. The model varies between runs, so run a failure twice before believing it. `examples/README.md` lists the scenarios.

## The three places

- `harness/` is the product. Nothing under it names an example, and it never imports `workshop/`.
- `my/` is yours. The harness writes only there. Nothing we ship overwrites it.
- `workshop/` is teaching material. Delete it and the harness's tests still pass.

To add another model provider, add one file under `harness/model/` and one line in `harness/model/providers.py`.
