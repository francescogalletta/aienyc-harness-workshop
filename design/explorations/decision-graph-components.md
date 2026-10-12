# Decision graph components

New components for the decision graph. They extend the design system in `design/system/` and are written the same way: plain HTML with `dg-` classes, built from the existing tokens, with no new colours. The working source is `decision-graph.html` in this folder: every class below is defined once in its second `<style>` block ("Decision graph components") and used by all three variants. To adopt them, move that block into `bundle.css` and the builders into the page.

They rely on the system's Step, Pill, Flow, Thread, Button and Composer, which keep their rules. Two of those rules change:

- **"A side thread never changes anything" is reversed.** A side thread is now a branch, and a branch can join the trunk once the person says yes.
- **"No icon-only buttons" gets one exception:** the hover menu. Each icon button has an `aria-label`, and the menu shows the name of the button under the pointer or focus in words.

---

## Contributor mark

Who said or decided something. The shape says who; the fill says where it stands. It holds up in greyscale and for colour-blind readers, like the step kinds.

| Shape | Who | Why this shape |
| --- | --- | --- |
| circle | You | Round, like a figure from you (`fah-step--from-you`) |
| diamond | The assistant | New; the assistant had only the `✎` mark |
| square | The harness | Square corners, like a calculation step |
| triangle | The reviewer | The reviewer's existing `▲` mark |

| Class on the shape | Meaning |
| --- | --- |
| `dg-shape` | Filled with ink: a decision on the trunk |
| `dg-shape--open` | Hollow: said on a branch, not decided |
| `dg-shape--dead` | Hollow and muted: on a dead branch |
| `dg-shape--needs` | Attention fill: the harness is waiting for your yes. The only use of `needs-you` in the history |

```html
<svg class="dg-who" viewBox="0 0 12 12" width="12" height="12" role="img" aria-label="The harness">
  <path class="dg-shape dg-shape--needs" d="M2 2h8v8h-8z"/>
</svg>
```

Rules:

- Draw the shapes from one function so a mark in text and a node in the graph are the same path at different sizes: 10px in a branch line, 12px in text, 12 to 14px on the trunk.
- The mark always has a text equivalent: `aria-label` on the SVG, or a visually hidden "You, decided:" before the words.
- Never tell contributors apart by colour.

---

## Trunk node

One confirmed decision that changed the plan. The trunk shows nothing else: no questions, no answers, no talk.

```html
<div class="dg-node" data-node="t2">
  <p class="dg-node__title" tabindex="-1">
    <span class="dg-sr">You, decided: </span>Second payment is 40% of what remains</p>
  <p class="dg-node__meta">
    <span>Changed</span>
    <button class="dg-ref dg-ref--input" aria-label="payment schedule: show in the plan">payment schedule</button>
    <button class="dg-ref" aria-label="Step 2, Three payments: show in the plan">2</button>
    <button class="dg-ref" aria-label="Step 5, Fund balance: show in the plan">5</button>
  </p>
</div>
```

| Part | Use |
| --- | --- |
| `dg-node__title` | The decision as a short fact, under 45 characters. Focusable (`tabindex="-1"`) so focus can move to a new node after a join |
| `dg-node__meta` | One verb and what changed, as refs: "Changed [payment schedule] [2] [5]", "By itself, changed [3]", "On a challenge, changed [5]" |
| `dg-node__results` | Optional. The new values the change produced, as result chips |
| `is-new` | The node that just joined. It rises in after the join line has drawn |

Rules:

- The graph draws the node's mark on the trunk line; the card has no mark of its own.
- Every trunk node changed something in the plan, except the first, "Plan accepted", which starts the trunk.
- Write who in the shape, and how in the meta. "Joined by itself" is said only for the harness.

---

## Ref

A step or input named inside a node, a branch or a proposal. It takes the plan's shape language at 20px: a numbered square for a calculation, round for a figure from you, dashed for your call, a pill with its name for an input. Clicking it selects that step or input in the plan.

```html
<button class="dg-ref" title="5 Fund balance" aria-label="Step 5, Fund balance: show in the plan">5</button>
<button class="dg-ref dg-ref--input" aria-label="guest count: show in the plan">guest count</button>
```

| Class | Kind |
| --- | --- |
| `dg-ref` | A calculation step: its number |
| `dg-ref--you` | A figure from you |
| `dg-ref--call` | A call that is yours |
| `dg-ref--input` | An input: its name |

Its hit area is grown by 8px above and below with `::after`, so it is easy to tap even though it draws at 20px.

---

## Branch

A conversation about one thing in the plan. It leaves the trunk at a point and ends in one of two ways: it joins, or it dies. It is the system's Thread with an end state, a native `<details>`.

```html
<details class="dg-branch dg-branch--open" data-branch="b4" open>
  <summary>
    <span class="dg-branch__title"><span class="dg-sr">You opened: </span>No fewer than 150 guests</span>
    <span class="dg-branch__state">needs you</span>
  </summary>
  <div class="dg-branch__body">
    <p class="dg-branch__on">From <!-- the chip it came from, or a ref --></p>
    <p class="dg-say dg-say--you"><svg class="dg-who">…</svg><span class="dg-sr">You: </span><span>We will have no fewer than 150 guests.</span></p>
    <div class="dg-propose">…</div>
  </div>
</details>
```

| State class | Looks | Summary says |
| --- | --- | --- |
| `dg-branch--open` | Tinted (`thread`), open by default | "needs you", in semibold, when it carries a proposal |
| `dg-branch--joined` | Tinted, folded | "joined" |
| `dg-branch--dead` | No tint, a 1px `line` outline, muted text | "no change" |

| Part | Use |
| --- | --- |
| `dg-branch__title` | What the branch is about, in the words that opened it. Under 45 characters |
| `dg-branch__on` | "On [ref]" or "From [chip]": the thing in the plan it is about |
| `dg-say` | One line said on the branch: a 10px hollow mark, then the words. `dg-say--you` sets your words in ink, everyone else's in `ink-2` |
| `dg-branch__end` | One line at the end: "Joined when you said yes.", "Joined by itself: tests are the harness's own.", "Nothing in the plan changed." |

Rules:

- A branch is about exactly one thing: an input, a value, a step or an assumption. Its first body line names it.
- It can be opened by anyone: you (a question, a correction), the assistant (an assumption it made), the reviewer (a challenge) or the harness (a failed test).
- A dead branch stays in the history, dimmed. It never joins and never disappears.
- Fold joined and dead branches by default; keep the open one open. One open branch at a time is enough for the first version.
- Insert every line as text, never as HTML.

---

## Join request

How a branch asks to join: the harness has found where the change lands and proposes it, and you say yes or no. It sits at the end of an open branch. It is the system's Decision, compacted.

```html
<div class="dg-propose" role="group" aria-label="Proposed change">
  <p class="dg-propose__q"><svg class="dg-who">…needs…</svg>Make the low case 150 guests?</p>
  <p class="dg-propose__row"><button class="dg-ref dg-ref--input">guest count</button><s>120</s>→<b>150</b></p>
  <p class="dg-propose__row"><span class="dg-propose__k">Re-runs</span>
    <button class="dg-ref">1</button><button class="dg-ref">2</button><button class="dg-ref">5</button></p>
  <div class="fah-row">
    <button class="fah-btn fah-btn--primary">Yes, change it</button>
    <button class="fah-btn">Keep 120</button>
  </div>
</div>
```

Rules:

- The question is one line in plain words, phrased as the change: "Make the low case 150 guests?"
- Row one is what changes: the input or value, the old value struck, the new one in semibold.
- Row two lists what re-runs, worked out from the plan graph's edges, never by the model.
- Two buttons. Yes says what happens ("Yes, change it"); No says what stays ("Keep 120").
- While it is open, the branch's node carries `dg-shape--needs`, the input concerned carries `dg-needs`, and everything it touches carries `dg-touch` in the plan.
- On yes: the branch becomes joined, a trunk node is added with `is-new`, the join line draws, and the plan re-runs in plan order (see Join, below). On no: the branch becomes dead.
- Anything that changes your figures or the plan's shape needs this yes. What the harness does to itself (a rebuild after a failed test) joins without it, and its trunk node says "By itself".

---

## Join

Not a block of its own: the moment a branch becomes a trunk node, shown in three places at once.

1. **In the history**, the branch line curves back into the trunk and ends at the new trunk node. Draw the curve with `pathLength="100"` and the class `is-drawing` so it draws in 500ms; the new node's shape gets `is-new` and pops in after it.
2. **In the plan**, the change travels in plan order, with the system's own calls: the input takes `fah-pill--used`, then `FAH.setLine(step1, '→ 43,000–54,500', 'result')`, `await FAH.flow([e12])`, `FAH.setLine(step2, …)`, `await FAH.flow([e25])`, `FAH.setLine(step5, …)`. Each step that re-ran gets a `dg-tag__new` "re-ran" tag under it, which rises in 150ms after the previous one.
3. **In the answer** that rested on the old value, the chips that changed take `dg-chip--stale`: struck through and muted. The history keeps what was said and shows it is no longer current.

Move focus to the new node's title, so a keyboard user lands on what changed.

---

## Graph lines

The history's lines are one SVG laid over the column (`dg-svg`, `aria-hidden="true"`), drawn from measured positions after layout and redrawn on resize and on every `toggle` of a branch. Every line has a text equivalent in the cards, so the SVG carries no meaning on its own.

| Class | Line |
| --- | --- |
| `dg-l dg-l--trunk` | The trunk: ink, 2.5px |
| `dg-l dg-l--branch` | A branch and its join: `flow`, 1.75px |
| `dg-l dg-l--dead` | A dead branch: `flow`, dotted, 80% opacity |
| `dg-l dg-l--cap` | The short bar that ends a dead branch |
| `dg-l dg-l--link` | C only: a dashed line from an open branch to what it touches |
| `dg-l dg-l--made` | C only: an ink line from a trunk node to what it changed |
| `dg-l dg-l--sel` | C only: the ring around the selected node (selection is an outline) |

Geometry used in the mockups: in a column, the trunk at x=14 and branches at x=38; a fork leaves the trunk 18px above the branch's first line and arrives 5px above its node; a join leaves the branch's last line and arrives 8px above the trunk node. Keep curves inside the gap between rows.

---

## Chip

A value in an answer, in place of a sentence. Three kinds, told apart by shape and a glyph, never by colour. Clicking a chip selects its place in the plan, as figures do today.

```html
<span class="dg-chip dg-chip--assumed" data-chip="g120">
  <button class="dg-chip__btn" aria-label="120 guests, assumed by the assistant. Show in the plan">
    <span class="dg-chip__g" aria-hidden="true">◌</span><span class="dg-chip__v">120 guests</span>
  </button>
  <span class="dg-menu" role="group" aria-label="Actions for 120 guests">…</span>
</span>
```

| Class | Kind | Shape |
| --- | --- | --- |
| `dg-chip--given` | A value you gave: "200 guests", "230 a guest" | Round, 1px outline, like a figure from you |
| `dg-chip--assumed` | An assumption the assistant made: "◌ 120 guests" | Dashed `flow` outline and the `◌` mark, like the Notice |
| `dg-chip--result` | A result a step produced: "→ 54,500" | 4px corners, 1.5px ink outline and the `→` mark, like a calculation |

| State | Use |
| --- | --- |
| `is-traced` | The chip whose place is selected in the plan. Takes the `thread` tint, like `fah-num.is-traced` |
| `dg-chip--stale` | Its value changed after a join. Struck through and muted |
| `dg-chip--below` | The menu opens below, because there is no room above in the scroll area |

Rules:

- A chip holds one value and at most two words. The label beside it says what it is ("Total cost"), not the chip.
- Every result chip leads to a step, the same rule as `fah-num`. A value no step produced is not shown.
- Lay an answer out as a lead line ("Yes, in both cases.") and a two-column list of label and chips (`dg-answer`, `dg-facts`). "Rests on" lists the given values and assumptions together, so the assumptions sit where they can be challenged.

---

## Hover menu

Three icon buttons on a chip: see it in the graph, challenge or correct it, open a branch about it. It opens on hover and on keyboard focus, and closes on Escape.

```html
<span class="dg-menu" role="group" aria-label="Actions for 54,500">
  <span class="dg-menu__row">
    <button class="dg-menu__btn" aria-label="See in graph: 54,500" title="See in graph"><svg>eye</svg></button>
    <button class="dg-menu__btn" aria-label="Challenge or correct: 54,500" title="Challenge or correct"><svg>correction mark</svg></button>
    <button class="dg-menu__btn" aria-label="Open a branch: 54,500" title="Open a branch"><svg>thread</svg></button>
  </span>
  <span class="dg-menu__label" aria-hidden="true">See in graph</span>
</span>
```

The icons are 16px inline SVGs with a 1.6px `currentColor` stroke, no fill:

| Icon | Paths (viewBox 0 0 16 16) |
| --- | --- |
| Eye: see in graph | `M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8s-2.4 4.5-6.5 4.5S1.5 8 1.5 8z`, circle at 8,8 r2 |
| Correction mark: challenge or correct | `M2 6h12` (the struck value), `M5 13.5l3-4.5 3 4.5` (the insert caret) |
| Thread: open a branch | `M4.5 1.8v12.4`, `M4.5 10.5c0-4 6.5-3 6.5-6.2`, circle at 11,3 r1.4 |

Behaviour:

- It sits 6px above the chip, aligned to its left edge, flipping below when the chip is within 72px of the top of its scroll area. A 10px invisible bridge keeps it open while the pointer crosses the gap, and it hides 120ms after the pointer leaves.
- It shows with `:hover` and `:focus-within`, so Tab from the chip moves into its three buttons. Escape hides it and returns focus to the chip.
- `dg-menu__label` names the button under the pointer or focus, in words.
- **See in graph** selects the step or input (`FAH.select`, or `dg-pill--sel` for an input) and scrolls it into view. Clicking the chip does the same.
- **Challenge or correct** puts the value in the composer and sets the placeholder to "Say what should change…".
- **Open a branch** opens the branch that is already about this value, if there is one, and moves focus to it. Otherwise it puts the value in the composer with "New branch" pressed and the placeholder "Start a branch about this…".
- Buttons are 32px for a mouse and 44px under `pointer: coarse`.

---

## In the plan

Three small additions to the plan diagram, so it shows what a branch would touch and what a join changed.

| Class | On | Meaning |
| --- | --- | --- |
| `dg-touch` | A step or pill | An open branch would change it. A 1.5px dashed `flow` outline drawn 4px outside the box (3px for a pill), so it never competes with the selection inside |
| `dg-needs` | A pill | The input an open join request is about. The `needs-you` fill, as on a step |
| `dg-pill--sel` | A pill | Selected, for an input: a 2.5px ink outline inside, the pill's version of `fah-step--selected` |
| `dg-tag` | Under a step | Quiet facts under a step, right aligned: a contributor mark and a word ("■ rebuilt", "▲ 1"). `dg-tag__new` "re-ran" is in ink and semibold |

---

## Composer

Unchanged except for the toggle: "On the side" becomes **New branch**, with the same `fah-side` toggle. The placeholders become "Ask, or click a step…", "Say what should change…" (a value or step attached), "Start a branch…" and "Start a branch about this…" (New branch pressed).

---

## Motion

| Moment | What moves | Time |
| --- | --- | --- |
| A branch joins | The join line draws itself into the trunk | 500ms, `ease-out` |
| A trunk node is added | Its shape scales in from nothing after the line; its card rises 4px | 200ms after 500ms; 360ms |
| The plan re-runs | The system's pulse and line arrival, input first, then in plan order | 380ms per arrow |
| A "re-ran" tag appears | It rises in, staggered 150ms | 360ms |
| A hover menu opens | It fades in and settles 3px | 120ms |

Everything is cut to nothing under `prefers-reduced-motion: reduce` by the system's existing rule on `.fah *`. State still changes.
