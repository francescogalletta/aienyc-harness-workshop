# Financial Advisor Harness UI: design decisions

The product decisions behind the page. The design system is in `design/system/`, the page source in `design/page/`. Where the code and this file differ, this file wins (`AGENTS.md`).

## Principles for the UI

- Simple and high signal first. Few manual confirmation steps.
- Not fitted to the workshop: design for the product, not the demo.
- Keep things top-level; do not design for edge cases. The system has an agent in the loop and some ambiguity is expected.
- The chat is the channel, not the core experience. It stays reachable everywhere as one panel.
- One main surface throughout: a flow diagram of the analysis, which gains information at each step.
- Nothing blocks unless the call is the person's. Anything unconfirmed runs and is visibly marked.
- One signal for "needs you": a single highlight on the step concerned.

## Look

- Product name: Financial Advisor Harness.
- Palette: Blueprint. Ground `#eef2f7`, surface `#ffffff`, ink `#0f2440`, muted `#4f6078`, line `#bccadb`, needs you `#ffd9b0`, tested `#0b6b6a`, side and reviewer threads `#dde6f2`. One attention colour, one "tested" colour, nothing coloured for decoration.
- Typeface: IBM Plex Sans.
- Inputs are their own small boxes, sitting just above the step that uses them, kept quiet so they do not compete with the steps.

## The screen

Two parts that never change: the plan as a diagram, and the chat, drawn as a decision graph (a trunk of decisions, branches, chips; ARCHITECTURE.md section 12). Clicking a step attaches it to the next chat message. Each step can open a pop-up with its detail.

## 1. Grounding

- The brief is shown as a flow diagram: the steps, what each needs, what comes out. The goal sits above it.
- Each step shows its kind (calculation, a figure from the person, the person's call) and a mark for an open question.
- Origin is a quiet annotation on every item, traceable to source: the person's quote, a looked-up source, or proposed by the assistant.
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
- No scenario comparison. A step keeps its last few runs, one click away in its pop-up.

## 4. When the harness needs the person

- Assumptions: run and mark. The result carries a mark ("rests on things you haven't confirmed"); one click confirms or corrects.
- Calls that are the person's stay real stops. They belong to the "your call" steps; the question arrives in the chat with options as buttons, or the person answers in their own words. The record lives in that step's pop-up; there is no separate decisions list.
- A calculation missing from the plan is built automatically; the person is told, and it appears as a new step marked "not in the plan".
- Side questions are a collapsible tinted thread inside the chat. They work everywhere (plan, build, questions). A side thread is a branch (ARCHITECTURE.md section 12) and no longer only talks: it may propose a change, and nothing changes until the person says yes, which joins the branch to the trunk and runs the steps it reaches again. The side assistant itself never applies anything. A branch that proposes nothing stays dead and dimmed.

## 5. Review

- A reviewer looks at how the problem is being thought about (assumptions, inputs, methods, the shape of the plan) and pushes back where something looks weak. It may research on the web and ask the person a clarifying question.
- It runs automatically in the background after the plan is accepted and when new assumptions appear.
- A challenge attaches to a step. Steps show a count; a "Review" view of the same diagram shows one line per challenged step.
- Each challenge is a thread in the chat, the same tinted thread as a side question, started by the reviewer.
- Each challenge has two actions, "use this" and "dismiss", plus replying in its thread. It never blocks.
- A challenge based on outside information carries a source the harness actually fetched. Only the general question goes to the web, never the person's figures.
- Each pass is capped to a few challenges, ranked by how much they would change the result.
- A challenge may propose building or replacing a step.
- Not included: loading the person's account files, a "from your files" origin, and highlighting everything downstream of a challenge.
