# Financial Advisor Harness UI: design decisions

The product decisions behind the page. The design system is in `design/system/`, the page source in `design/page/`. Where the code and this file differ, this file wins (`AGENTS.md`).

## Principles for the UI

- Simple and high signal first. Few manual confirmation steps.
- Not fitted to the workshop: design for the product, not the demo.
- Keep things top-level; do not design for edge cases. The system has an agent in the loop and some ambiguity is expected.
- The chat is the channel, not the core experience. It stays reachable everywhere as one panel.
- One main surface throughout: a flow diagram of the analysis, which gains information at each step.
- Nothing blocks unless the call is the person's. Anything unconfirmed runs and is visibly marked.
- One signal for "needs you": a single highlight on the step concerned, in principle 4's attention fill.
- Colour is the principle: an element takes the colour of the principle (the harness layer) that produced it, so the page reads as the five principles of the workshop. Colour is never the only signal; every mark, shape and word stays.

## Look

- Product name: Financial Advisor Harness.
- Palette: Blueprint for the neutrals. Ground `#eef2f7`, surface `#ffffff`, ink `#0f2440`, muted `#4f6078`, line `#bccadb`. The only other colours are the five principles, the slide deck's colours (below); "needs you" is principle 4's attention fill and the tested tick is principle 2's ink. Nothing is coloured for decoration.
- Typeface: IBM Plex Sans.
- Inputs are their own small boxes, sitting just above the step that uses them, kept quiet so they do not compete with the steps.

## Colour is the principle

Each of the five principles of the workshop has one colour, the deck's (`workshop/slides/src/principles.json`), carried by the design system as `principle-N` (a fill, tint or stroke) and `principle-N-ink` (small text, marks, thin strokes; 4.5:1 or more on surface and ground in both themes). An element takes the colour of the layer that produces it, with one exception: provenance (where a thing came from) is always principle 3, whichever layer recorded it, because it is what lets a number be followed back. The colour follows one rule: a container takes a faint tint and a 3px edge in the fill; a mark, tag or section heading takes the ink; an outline takes the ink; a principle's primary button takes the fill. Body text stays ink. A step carries several principles at once, so each part of it is coloured, not the box.

| Principle | Layer | On the page |
| --- | --- | --- |
| 1 Shared Domain: Agree the plan before any number. | 1 the plan | The goal (edge), each step's outline and name, the input pills, open questions (●), "Whole plan" and its section, "Accept plan", the "Plan accepted" and plan-revised nodes, the folded interview |
| 2 Consistency: Numbers come only from tested code. | 2 build | The build button and its working line, a step's build line ("✓ 4 examples · 5/5", "Building", "Stale · rebuild", "Not built") and tick, the plan check mark, the pop-up's Build part (examples, tests, code) |
| 3 Evidence: Every number can be followed back. | 3 answers | Origin marks (❝ ↗ ✎) and their labels, the person's quoted words, looked-up sources and their links (on steps, inputs, the goal, the Whole plan, and in chat messages), the pop-up's "Where this came from" part, a step's result ("→ 43,000", underlined in the fill), underlined figures in the chat, result and "Rests on" value chips, the pop-up's run and receipt, the pulse along the lines, a withheld reply |
| 4 Accountability: Ask only where a person must decide. | 4 needs you | The "needs you" fill and line, `◌` marks and the notice with Confirm and Change it, "your call" steps, their decision cards and records, "not in the plan", "Decided", branches and their marks, proposals with Yes and Keep and what they would touch, "re-ran" tags and their nodes, "New branch" |
| 5 Verification: A reviewer challenges the plan. | 5 review | The Review button and its count, "Reviewing", ▲ counts and "used" tags, the Review view's lines and list, reviewer branches with Use this and Dismiss, the pop-up's Reviewer part, the "used" node |

Neutral: the chat bubbles and plain answers, the message box, the step a message is about, the lines between steps, the trunk, refs, selection (an ink outline).

A legend sits at the foot of the plan: the five principles, each a swatch, its number and name, with its statement as a tooltip and read to screen readers. An entry is quiet until something of its principle is on the page, so an empty page shows five quiet entries and they switch on as the plan (with its origins, which are Evidence), the build, answers, marks and challenges arrive (a short pulse the first time, none under reduced motion). Hovering or focusing an entry spotlights its principle: its elements stay, everything else fades. A click keeps the spotlight; a second click or Escape lets go. On a narrow screen the legend sits at the end of the plan, above the chat.

## The screen

Two parts that never change: the plan as a diagram, and the chat, drawn as a decision graph (a trunk of decisions, branches, chips; ARCHITECTURE.md section 12). Clicking a step attaches it to the next chat message. Each step can open a pop-up with its detail.

## 1. Grounding

- The brief is shown as a flow diagram: the steps, what each needs, what comes out. The goal sits above it.
- Each step shows its kind (calculation, a figure from the person, the person's call) and a mark for an open question.
- Origin is shown on every item, readable without hovering: a mark and a short label in the diagram (the glyph alone only where a step's marks would not fit), a mark on each input pill that has room, the full quote or source in the pop-up and the Whole plan; coloured as Evidence. It is the person's quote, a looked-up source, or proposed by the assistant.
- Particulars and open questions attach to the step they concern. Whole-plan context (assumptions, scope, what counts as done) has its own section, off screen by default.
- Correcting: click a step and say what is wrong; it goes to the chat with that step attached. No direct editing.
- The diagram first appears when the brief is proposed and redraws on each correction.
- A brief with open questions can be accepted.

## 2. Build

- One action starts the build; it runs through every calculation step without stopping.
- Per step, one indicator: number of golden examples, number of tests, how many pass. The same indicator shows a module that has gone stale.
- Examples, tests and code are hidden, opened on demand in the step's pop-up.
- Examples are checked by a second independent model pass, not by the person as a requirement. Each example carries its origin: "checked by a second pass" or "confirmed by you". Known trade-off: a mistake both passes make gets through.
- The plan check appears only when the detailed plan departs from the brief, as a mark on the step.
- When code and an example disagree, the step shows "not built"; the person resolves it through the chat on that step.

## 3. Asking questions and evidence

- An answer is one run through the diagram. Steps used for the last answer show what went in and what came out.
- Every number in a chat answer leads to the step that produced it. A number no step produced is never shown.
- Everything that says where a thing came from (origin marks, the person's quoted words, sources) is Evidence, and is on the page from the first plan, before any question is asked.
- No scenario comparison. A step keeps its last few runs, one click away in its pop-up.

## 4. When the harness needs the person

- Assumptions: run and mark. The result carries a mark ("rests on things you haven't confirmed"); one click confirms or corrects.
- Calls that are the person's stay real stops. They belong to the "your call" steps; the question arrives in the chat with options as buttons, or the person answers in their own words. The record lives in that step's pop-up; there is no separate decisions list.
- A calculation missing from the plan is built automatically; the person is told, and it appears as a new step marked "not in the plan".
- Side questions are branches in the decision graph beside the plan (ARCHITECTURE.md section 12): each forks from the trunk and folds open to its conversation. They work everywhere (plan, build, questions). A branch may propose a change, and nothing changes until the person says yes, which joins the branch to the trunk and runs the steps it reaches again. The side assistant itself never applies anything. A branch that proposes nothing stays dead and dimmed.

## 5. Review

- A reviewer looks at how the problem is being thought about (assumptions, inputs, methods, the shape of the plan) and pushes back where something looks weak. It may research on the web and ask the person a clarifying question.
- It runs automatically in the background after the plan is accepted and when new assumptions appear.
- A challenge attaches to a step. Steps show a count; a "Review" view of the same diagram shows one line per challenged step.
- Each challenge is a branch in the decision graph, like a side question, opened by the reviewer.
- Each challenge has two actions, "use this" and "dismiss", plus replying in its thread. It never blocks.
- A challenge based on outside information carries a source the harness actually fetched. Only the general question goes to the web, never the person's figures.
- Each pass is capped to a few challenges, ranked by how much they would change the result.
- A challenge may propose building or replacing a step.
- Not included: loading the person's account files, a "from your files" origin, and highlighting everything downstream of a challenge.
