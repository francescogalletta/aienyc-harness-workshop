# Financial Analyst Harness Workshop

A workshop for [AI Engineer NYC 2026](https://ai.engineer/nyc/2026) on building agent harnesses for financial analysis that you can trust. The harness here is small and complete: you describe a money goal, it draws the plan as a diagram, builds and tests the calculations, and answers with numbers you can follow back. It is built on five principles. This page walks you through each one on a running example, a plan to pay for a wedding on time. You can follow it alone.

## 1. Set up

Install [uv](https://docs.astral.sh/uv/). It fetches a suitable Python and keeps everything in a `.venv` folder in the repository; deleting `.venv` undoes it.

```
curl -LsSf https://astral.sh/uv/install.sh | sh                          # macOS or Linux (or: brew install uv)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```

You need model access, one of:

- **Claude Code**, installed and signed in with your Claude plan (`claude auth status` says `"loggedIn": true`). Usage counts against your plan. If `ANTHROPIC_API_KEY` is set in your shell, unset it, or the key is used instead.
- **An Anthropic API key**: `export ANTHROPIC_API_KEY=...`, and add `--extra claude` after every `uv run`.
- **An OpenRouter API key**: `export OPENROUTER_API_KEY=...`. Nothing else to install.

Get the repository and check that the model answers. Every command on this page runs from the repository folder.

```
git clone https://github.com/francescogalletta/aienyc-harness-workshop
cd aienyc-harness-workshop
uv run python -m harness check
```

It should end with `Setup works: the model replied and the check was saved as event 1.` It takes a few seconds, up to a minute on a first run.

## 2. Open the example

```
HARNESS_EXAMPLE=wedding uv run python -m harness ui
```

On Windows (PowerShell): `$env:HARNESS_EXAMPLE="wedding"; uv run python -m harness ui`. Add `--port N` if the port is taken, or `--no-browser` to open the page yourself.

The page opens in your browser, served from your machine. On the left is the plan as a diagram: each box is a **step**. On the right is the decision graph: a **trunk** of the decisions that changed the plan, **branches** that leave it (side conversations about one thing in the plan), and the conversation below. Click a step to attach it to your next message, or open its details.

The example opens with everything already run: the plan is accepted, the calculations are built, and a reviewer has posted its challenges as branches. Leave those branches until principle 5.

Each element on the page takes the colour of the principle that produced it. The **legend** at the foot of the plan has one entry per principle; an entry lights up once something of its principle is on the page. Hover an entry to fade everything else; click it to keep it that way, and click again or press Escape to let go. Spotlight each principle as you reach it below.

**Start again.** The example is copied to `my/var/examples/wedding/` the first time, and your work on it stays there. Nothing touches `examples/` or the rest of `my/`. Where this page says **Reset**, stop the page with Ctrl+C, delete the copy and start the page again:

```
rm -rf my/var/examples/wedding                     # PowerShell: Remove-Item -Recurse -Force my\var\examples\wedding
HARNESS_EXAMPLE=wedding uv run python -m harness ui
```

Figures that depend on today's date, and anything the model writes, vary between days and runs. Read them off the screen. Figures stated below are the ones that do not move.

## 3. Principle 1, Shared Domain: agree the plan before any number

Look for (legend entry 1, blue): the goal, the step outlines, the input pills, and an origin mark on every item: `❝` the person's words, `✎` proposed by the assistant, `↗` looked up. `●` with a number is an open question. Step 4 is a figure from the person; step 7 (dashed) is their call. Step 8 was added in a conversation and is marked "not in the plan". The trunk has one node, "Plan accepted": the history of decisions starts there.

1. Click step 3.\
   **You see** Each item says where it came from: `❝` your words, `✎` proposed. `●` is still open.\
   **Why** The plan is agreed item by item, before any number.

2. Click step 2. Type:
   ```
   The plan is wrong: there should be two payments, not three.
   ```
   **You see** A new trunk node. Step 2: `Stale · rebuild`.\
   **Why** Only your words change the plan. Its numbers wait for a rebuild.

   **Reset.**

3. Watch an interview from an empty page. Stop the page and start it without the example: `uv run python -m harness ui`. Type `I want to pay for my wedding`. After the first question, click **Propose the plan now** under it. Once the plan appears (it can take up to a minute), click step 2 and type:
   ```
   This should also include 3,000 for the honeymoon.
   ```
   **You see** One question at a time, then a plan of four or five steps. After your correction the plan redraws with a new input, "Honeymoon cost", and "The plan is revised: changed steps …".\
   **Why** The interview turns a vague goal into a plan you both agree on. You correct it before anything is built.

   Do not accept it; stop the page. This interview lives in `my/var/`; to clear it, delete `my/var/harness.db*` and `my/var/grounding_state.json`.

## 4. Principle 2, Consistency: numbers come only from tested code

Open the example again. Look for (legend entry 2, purple): the button reads `All 6 built`, and each calculation step shows `N examples · P/P`, its worked examples and how many tests pass. Steps 4 and 7 are the person's and carry no tag.

1. Click step 1, then **Build**, then **Unit tests**, then **Run tests now**.\
   **You see** `Unit tests (4) all passing`, with the tests under it. **Code** opens the module.\
   **Why** Every number comes from code you can read, tested now.

   Under **Golden examples**, the same pop-up lists the step's worked examples: answers worked by hand before the code was written, which the code must reproduce. A second model pass checked them, not a person, until you approve them: one by one, or with **Approve all examples**. Work one out with a calculator; a mistake both passes make gets through. **Unit tests** are separate: the code writer's own tests of the code, which nobody approves.

2. Stop the page, delete one built module and start again:
   ```
   rm -rf my/var/examples/wedding/modules/monthly_surplus
   HARNESS_EXAMPLE=wedding uv run python -m harness ui
   ```
   **You see** Step 3: `Stale · rebuild`, and the button says **Rebuild 1 step**. Click it: step 3 says "Building" for under a minute, then reads `N examples · P/P` again. Only step 3 is built.\
   **Why** The build runs unattended. The code writer never sees the worked examples; a second pass checks them, and the module counts only once its tests pass.

3. Line 9: change `*` to `+`. Save.
   ```
   my/var/examples/wedding/modules/wedding_total_cost/module.py
   ```
   **You see** No restart needed. Step 1: `Stale · rebuild`.\
   **Why** Code changed after its tests passed gives no number.

   **Reset.**

## 5. Principle 3, Evidence: every number can be followed back

Look for (legend entry 3, red; it lights up with the first answer): underlined figures in replies; **chips** under them, small boxes for a value it used, something it assumed or a result (hover one for a small menu); and `→ value` on the steps an answer used.

1. Type:
   ```
   What would the wedding cost with 100 guests at 250 each for dinner, plus 6,000 for extras?
   ```
   **You see** 31,000 underlined, chips under it, step 1 lit up.\
   **Why** The answer carries its trail: which step, which inputs.

2. Click the underlined 31,000.\
   **You see** Step 1 opens: your inputs, Came out 31,000, after test run N.\
   **Why** Any number leads back to its step, its inputs and its tests.

3. Paste:
   ```
   Can I cover each wedding payment? The wedding is on 12 June 2027 and I expect between 150 and 200 guests, at 230 each for dinner. Costs that do not depend on guests: 5,000 for extras, 2,000 for the DJ and 1,500 for the bar. The first payment is 6,000, due 21 days from today, and it counts towards the total. The second is half of what remains, due 30 days before the wedding, and the third is the other half, due 14 days before. I take home 10,000 a month and spend about 8,500 a month. I have 10,000 saved for the wedding. My families will give 20,000 on 29 May 2027.
   ```
   A full answer takes up to a minute.\
   **You see** A short reply, "Not fully, in either case", with the shortfalls in the sentence. Under it, chips: the totals 43,000 and 54,500 and the monthly surplus 1,500 (results), the values it used and what it assumed. Click the chip `Estimate total wedding cost 54,500`: step 1 is selected, and the steps the answer did not use fade.\
   **Why** The analyst ran the tested modules; the number check holds back any number no step produced.

4. Type:
   ```
   What if my families give nothing?
   ```
   **You see** The third payment's shortfall grows, for both guest counts.\
   **Why** A new question runs the same modules again; the new figures carry the same trail.

   **Reset.**

## 6. Principle 4, Accountability: ask only where a person must decide

Look for (legend entry 4, orange): `◌` marks on answers that rest on something you did not confirm, with **Confirm** and **Change it**; your calls, asked with buttons; branches; `re-ran` on steps run again; "not in the plan".

1. Paste:
   ```
   Can I cover the three payments if we invite 120 guests? The wedding is on 12 June 2027. Dinner is 230 a guest, plus 5,000 for extras, 2,000 for the DJ and 1,500 for the bar. The first payment is 6,000, due 21 days from today, and it counts toward the total. The second and third payments are each half of what remains, due 30 and 14 days before the wedding.
   ```
   **You see** A two-sentence reply: with 120 guests the fund covers all three payments. Chips under it, step 1 reading 36,100, and a dashed `◌ This rests on N things you haven't confirmed` with **Confirm** and **Change it**.\
   **Why** Assumptions run and are marked. Nothing stops to ask about them.

2. Hover the chip Guest count 120 (under Rests on). Click Challenge or correct. Type:
   ```
   We will get no fewer than 150 guests.
   ```
   **You see** “Change guest count to 150?” Nothing moves until Yes, change it.\
   **Why** Your figures change only with your yes.

3. Click **Yes, change it**.\
   **You see** "Decided on a branch: Guest count is 150 (was 120). Run again: steps 1, 2 and 5." Step 1 reads 43,000; steps 1, 2 and 5 carry `re-ran`. The trunk has a node `Guest count: 150 (was 120)` with chips such as `43,000 (was 36,100)` and `18,500 (was 15,050)`. In the old reply the figures that moved are struck through.\
   **Why** The branch joins the trunk as a decision. The steps it reaches run again through the same test gate, with no model call.

4. Click step 5, then New branch. Type:
   ```
   What is a sinking fund?
   ```
   **You see** An answer. Close branch: it dims, no change.\
   **Why** Nothing to decide, so nothing is asked and nothing changes.

5. Under the `◌` line, click **Confirm**. Or click **Change it** and type:
   ```
   On second thought, the second payment is 40% of what remains, and the third is the other 60%.
   ```
   **You see** Confirm: a trunk node `Confirmed: …`. Change it: a trunk node `Corrected: …`, and the payments become 14,800 and 22,200.\
   **Why** The trunk holds only decisions you made. A value typed in the chat without one of these buttons is conversation, not a decision.

6. Type:
   ```
   Now help me decide what to update first.
   ```
   **You see** Step 7 asks, with options as buttons (the words differ each time). Pick one: a trunk node appears at once, step 7 reads "Decided", and the reply follows. Open step 7 for "You chose: …".\
   **Why** A call that is yours stops and asks. Arithmetic never does.

   **Reset.**

## 7. Principle 5, Verification: a reviewer challenges the plan

Look for (legend entry 5, green): `Review · N`, `▲` on challenged steps, and branches tagged `challenge` or `question`. The reviewer starts when the example opens; its challenges appear within about fifteen seconds. Click **Review** to see the challenged steps.

1. Open a branch tagged challenge. Click Use this.\
   **You see** It joins the trunk: Reviewer's suggestion used on step N.\
   **Why** A second look you can act on.

2. Open another. Click Dismiss.\
   **You see** It dims: dismissed. The plan stays as it was.\
   **Why** Each challenge is yours to use or dismiss.

A branch tagged `question` has no Use this: reply in its box, or pick another.

## 8. Your own figures

Keep the same kind of plan (saving towards dated payments) with your own figures and dates. Start the page without the example:

```
uv run python -m harness ui
```

Say what you want help with, answer the questions (or click **Propose the plan now**), correct any step, then click **Accept plan** and **Build the calculations**. A build takes one to four minutes. Then ask, as in principles 3 and 4.

Your work lives in `my/`: your plan in `my/brief/`, your tested calculations in `my/modules/`, the database and working files in `my/var/` (never committed). Nothing we ship overwrites it. To start again, delete `my/var/harness.db*` and `my/var/grounding_state.json`.

- Never type account numbers or passwords into the chat.
- Your plan must be a money question that arithmetic on amounts and dates can answer.
- Check each worked example with a calculator before you rely on it.

## 9. If something goes wrong

- **`check` fails with Claude Code.** Run `claude auth status`, and `claude update`. If `ANTHROPIC_API_KEY` is set by mistake, unset it.
- **The interview is slow.** Click **Propose the plan now** after the first question.
- **A branch proposes nothing.** Say it plainly again (`Change the guest count to 150.`). The side assistant may ask a question first.
- **Your call shows no buttons.** Move on, and play it as a replay (below).
- **The reviewer raised nothing.** Ask a question (principle 4, action 1) for a second pass.
- **Wikipedia cannot be reached.** Start with `HARNESS_RESEARCHER=reference` to look terms up only in `reference/terms.json`. The reviewer's challenges then carry no source.
- **A figure differs from this page.** Date-dependent figures and model wording vary; read them off the screen.

**Play a moment instead.** A replay plays a scripted person against the real model in a scratch copy (`my/var/replay/`), and prints a line per expectation. Each takes from 30 seconds to two minutes. The model varies, so run a failure twice before believing it.

```
uv run python -m harness replay wedding build_monthly_surplus    # principle 2: the rebuild
uv run python -m harness replay wedding cover_each_payment       # principle 3: the 150 to 200 guest question
uv run python -m harness replay wedding branch_that_joins        # principle 4: 120 guests, then 150
uv run python -m harness replay wedding decide_what_to_update    # principle 4: your call
uv run python -m harness replay wedding review_the_plan          # principle 5: use and dismiss
```

`examples/README.md` lists every scenario. Add `--keep` to keep the scratch copy.

## 10. Go further

- [`workshop/BUILD_YOUR_OWN.md`](workshop/BUILD_YOUR_OWN.md): build a similar harness from scratch, one principle at a time.
- [`SPEC.md`](SPEC.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md): the contract, and how the harness is built and configured.
- [`examples/README.md`](examples/README.md): the wedding example and its scenarios.
- [`workshop/slides/deck.html`](workshop/slides/deck.html): the slides; open the file in a browser.
- [`AGENTS.md`](AGENTS.md): notes for working on the harness itself.
