# Components

Every component is plain HTML with `fah-` classes from `bundle.css`. State changes go through `window.FAH` in `bundle.js`. Wrap the screen in one element with class `fah`.

---

## Principle colour

Colour says which of the five principles (one per harness layer) produced an element. Put `data-p="1"` … `data-p="5"` on the element; for it and everything it holds, `bundle.css` sets

| Property | Is | Used for |
| --- | --- | --- |
| `--p` | `principle-N` | A primary button's fill, a container's 3px edge, a figure's underline, a mark on the trunk |
| `--p-ink` | `principle-N-ink` | Marks, tags, section headings, a step's line, outlines |
| `--p-tint` | `principle-tint` of `--p` in surface | A container's ground: notice, decision, branch; hover |
| `--p-line` | `--p-ink` half into surface | A quiet outline: pills, value chips, a reply box |
| `--p-on`, `--p-hover` | `on-principle(-3)`, the fill lightened (3: darkened) | Text on the fill; the fill under the pointer |

Components read these with their neutral colour as the fallback, so without `data-p` nothing changes, and a button or chip inside a coloured container takes the container's principle. One rule everywhere: a container takes the tint and an edge, a mark or label the ink, an outline the ink, a primary button the fill; body text stays ink. A step is several principles at once: the step (outline, name) is 1, or 4 for a call that is the person's; its line carries its own `data-p`; each mark under it its own. Colour never replaces a shape, a glyph or a word.

---

## Step

One node of the plan: a name and at most one more line. A step is a `<button>`, because clicking it selects it and attaches it to the next chat message.

```html
<button class="fah-step">
  <span class="fah-step__name">5 Fund balance</span>
  <span class="fah-step__line">4 examples · 6/6</span>
</button>
```

### Kind (shape)

| Class | Kind |
| --- | --- |
| none | A calculation |
| `fah-step--from-you` | A figure from the person |
| `fah-step--your-call` | A call that is the person's |

### State

| Class | Meaning |
| --- | --- |
| `fah-step--selected` | The step the person clicked, or the one a traced number came from. One at a time: use `FAH.select(step)` |
| `fah-step--needs-you` | Waiting on the person. Fills with the attention colour and rings once: `FAH.needsYou(step)` |
| `fah-step--faded` | Not part of the last answer: `FAH.fade(step)` |

### The second line

| Class | Use |
| --- | --- |
| `fah-step__line` | A quiet fact: an origin mark, a test count, a challenge. With `data-p` it is in that principle's ink |
| `fah-step__line--result` | What came out of the step, starting with `→`. With `data-p` (3) underlined in the fill, like a figure in the chat |
| `fah-step__line--strong` | "Needs you", with the reason |

Set it with `FAH.setLine(step, text, kind)` so the arrival plays. Kind `'tested'` adds the tick. Pass empty text to remove the line.

A step with nothing to report shows only its name. Do not write "nothing to flag" or "not used".

The page provides the position, and the name. Keep the second line under about 22 characters so it stays on one line at the 184px width.

---

## Pill

An input the plan needs from the person, shown as a small pill just above the step that uses it. Pills are deliberately quiet: the steps are the diagram, the pills annotate them.

```html
<div class="fah-pills">
  <span class="fah-pill">guest count</span>
  <span class="fah-pill">cost per guest</span>
</div>
```

Add `fah-pill--used` when the input took part in the last answer; its text darkens to ink and its outline to the principle's ink (ink without one). On the page the row carries `data-p="1"`: an input is part of the plan.

Rules:

- Names only. The value that went in belongs in the step's pop-up, not on the pill.
- Place the row 4px above its step, left edges aligned. No connecting line.
- A step that is itself a figure from the person (`fah-step--from-you`) has no pill.
- If a step needs more than three inputs, show the first two and "+2".

---

## Flow

A line or arrow between two steps. It is a small SVG the page positions; when an answer runs, one ink pulse travels along it to show where the value went.

```html
<svg class="fah-flow" width="55" height="8" viewBox="0 0 55 8">
  <path d="M0 4H51" pathLength="100"/>
  <path class="fah-flow__head" d="M51 1l4 3-4 3z"/>
  <path class="fah-flow__pulse" d="M0 4H51" pathLength="100"/>
</svg>
```

- The first path is the line. Stop it 4px short of the tip so the head covers the end.
- `fah-flow__head` is the arrowhead. Leave it out for a plain joining line.
- `fah-flow__pulse` repeats the line's path. It is invisible until the pulse plays.
- `pathLength="100"` on the line and the pulse is required: it lets one animation fit any length.

For a vertical line swap the axes: `width="8" height="47"`, `d="M4 0V43"`, head `d="M1 43l3 4 3-4z"`.

Play it with `FAH.flow([line1, line2])`, passing the lines in the order the value travels. It returns a promise, so set each step's result as its pulse lands.

A bent connection is two or three straight segments, each its own SVG, with the head on the last. Keep lines horizontal or vertical and never run one across a step.

---

## Message

The chat: what the person and the assistant say to each other. The assistant's text has no frame; the person's sits in a bubble on the right.

```html
<div class="fah-chat">
  <p class="fah-msg">This is the plan as I understand it.</p>
  <p class="fah-msg fah-msg--you">
    <span class="fah-chip">2 Three payments</span>
    The first payment is a fixed 6k.
  </p>
</div>
```

### Parts

| Class | Use |
| --- | --- |
| `fah-chat` | The column. It sets the 14px gap between messages |
| `fah-msg` | The assistant's message. Rises in when added |
| `fah-msg--you` | The person's message |
| `fah-chip` | The step a message is about. Inside a person's message it sits on its own line above the text |
| `fah-num` | A figure a step produced. Underlined and clickable; add `is-traced` to the one that is selected, or call `FAH.trace(num, step)` |
| `fah-working` | A short sliding line while the assistant is working. Give it `role="status"` and an `aria-label` |

Every number the assistant shows must be a `fah-num` that leads to a step. A number with no step behind it is not shown at all.

There is no "Chat" heading and no avatar. Insert message text as text, never as HTML.

---

## Thread

A conversation set apart from the main chat: a side question the person asked, or a challenge the reviewer raised. Both use the same tinted, collapsible block. It is a native `<details>`, so it opens with the keyboard and needs no script.

```html
<details class="fah-thread" open>
  <summary>Reviewer <span class="fah-thread__meta">· 5 Fund balance</span></summary>
  <div class="fah-thread__body">
    <p>The contribution arrives after the second payment is due.
       <span class="fah-thread__source">❝ 2 quotes</span></p>
    <p><b>Proposed:</b> count it toward the third payment only.</p>
    <div class="fah-row">
      <button class="fah-btn fah-btn--primary">Use this</button>
      <button class="fah-btn">Dismiss</button>
    </div>
  </div>
</details>
```

Rules:

- The summary names who started it ("Side question" or "Reviewer") and what it is about, in under 45 characters so it stays on one line.
- Keep one thread open at a time. Give the threads in a chat the same `name` attribute and the browser closes the others.
- A reviewer thread ends with what it proposes and two buttons, "Use this" and "Dismiss". It never blocks anything.
- A challenge built on outside information shows its source in `fah-thread__source`, as a link the harness actually fetched.
- On the page a thread is now drawn as a **Branch** (below), which can join the trunk with the person's yes. `fah-thread` stays for anything that is not part of the decision history.

---

## Decision

The one real stop: a call only the person can make. It arrives in the chat with the step it belongs to, the question, and two to four options as buttons.

```html
<div class="fah-decision">
  <div><span class="fah-chip">7 Review and decide</span></div>
  <p class="fah-decision__q">Which guest count should the plan be built on?</p>
  <button class="fah-btn fah-btn--block">150 guests</button>
  <button class="fah-btn fah-btn--block fah-btn--primary">200 guests · suggested</button>
  <p class="fah-decision__why">Suggested because a shortfall would show up earlier.</p>
</div>
```

Rules:

- Two to four options, each in plain words. If the assistant suggests one, it is the primary button and says "suggested"; give the reason in one sentence in `fah-decision__why`.
- With no suggestion, every option is an outlined button.
- The person can always answer in their own words in the message box instead. Set its placeholder to "…or answer in your own words" while a decision is open.
- While it is open, the step it belongs to carries `fah-step--needs-you`.
- Every figure in the question or the options must come from a step, the same as in a message.
- Once answered, the block is replaced by the person's message. The record of what they decided lives in the step's pop-up.

---

## Notice

A note under an answer saying it rests on something the person has not confirmed. The calculation already ran; the notice lets them confirm or change the assumption in one click.

```html
<div class="fah-notice">
  <div>◌ This rests on one thing you haven't confirmed: the guest count stays at 150.</div>
  <div class="fah-row">
    <button class="fah-btn fah-btn--primary">Confirm</button>
    <button class="fah-btn">Change it</button>
  </div>
</div>
```

Rules:

- The dashed outline marks it as provisional. It is not a warning and never uses the attention colour; on the page it is principle 4 (`data-p="4"`): a dashed ink outline on the faint tint.
- State each assumption as one plain sentence. With more than one, list them and keep a single pair of buttons.
- The step whose result depends on it shows a small `◌` after its result, with no words.
- "Confirm" removes the notice and the mark. "Change it" puts the step in the message box so the person can say what is different.

---

## Composer

The message box at the bottom of the chat. It carries two extra things: the step the message is about, and a toggle for starting a new branch.

```html
<div class="fah-composer">
  <span class="fah-chip">2 Three payments ✕</span>
  <input type="text" placeholder="Say what should change…" aria-label="Message about step 2">
  <button class="fah-side" type="button" aria-pressed="false">New branch</button>
</div>
```

### Behaviour

- Clicking a step in the diagram puts its chip in the box. The message then goes to the assistant with that step attached. The `✕` removes it.
- "New branch" is a toggle. Call `FAH.sideToggle(button)` on click: it flips `aria-pressed` and tints the box, so it is obvious the next message starts a branch (on the attached step, else on the whole plan) rather than going to the main chat.
- Enter sends. There is no send button.

### Placeholder

Change it to say what the box will do right now: "Ask, or click a step…" by default, "Say what should change…" with a step attached, "Start a branch…" or "Start a branch about this…" with "New branch" pressed, "…or answer in your own words" while a decision is open.

Give the input a stable `id` and an `aria-label`; the placeholder is not a label.

---

## Button

Buttons, the Review toggle and text links. All are 44px tall or more, and the label says exactly what happens.

```html
<button class="fah-btn fah-btn--primary">Accept plan</button>
<button class="fah-btn">Dismiss</button>
<button class="fah-btn" aria-pressed="false">Review · 3</button>
<button class="fah-link">Whole plan</button>
```

| Class | Use |
| --- | --- |
| `fah-btn fah-btn--primary` | The main action in a group. At most one per group |
| `fah-btn` | Any other action |
| `fah-btn` with `aria-pressed` | A toggle. Pressed, it fills with ink. Used for Review, with the count of open challenges after a middle dot |
| `fah-btn--block` | Full width and left aligned, for the options in a decision |
| `fah-link` | A quiet text link, for "Whole plan", "Code", "Run tests now" |
| `fah-row` | A wrapping row with an 8px gap for buttons that belong together |

Rules:

- The Review toggle sits in one fixed place, top right of the diagram, on every screen after the plan is accepted. Leave the count off when there are no challenges.
- "Accept plan" lives in the chat, under the message that proposes the plan, not in the header.
- No icon-only buttons, with one exception: the Hover menu, whose buttons carry an `aria-label` and show their name in words under the pointer or focus. No destructive style: nothing here deletes anything.

---

## Popover

A step's detail, opened on demand next to the step: its worked examples and who checked each, its tests, and links to the code. Everything the diagram keeps off the step lives here.

```html
<div class="fah-pop" role="dialog" aria-label="5 Fund balance">
  <div class="fah-pop__head"><span>5 Fund balance</span>
    <button class="fah-link" aria-label="Close">✕</button></div>
  <div class="fah-pop__row"><span>Example 1</span><span>checked by a second pass</span></div>
  <div class="fah-pop__row fah-pop__row--you"><span>Example 3</span><span>confirmed by you</span></div>
  <div class="fah-pop__foot"><span>6 tests, all passing</span>
    <button class="fah-link">Code</button>
    <button class="fah-link">Run tests now</button></div>
</div>
```

| Class | Use |
| --- | --- |
| `fah-pop__head` | The step's name and the close button |
| `fah-pop__row` | A label on the left, its status on the right in muted text |
| `fah-pop__row--you` | A row the person confirmed themselves; its status is ink and semibold |
| `fah-pop__foot` | The test summary and text links |

What goes in it, by kind of step: a calculation shows its examples and tests; after an answer, what went in and what came out; a call that is the person's shows what they decided, in their words.

The page positions it: 8px below the step, left edges aligned, flipping above when there is no room. Toggle it with the `hidden` attribute; the entrance plays each time it is shown. Set `aria-expanded` on the step, close on Escape and on a click outside, and return focus to the step.

One pop-up open at a time, and it never covers the step it belongs to.

---

## Decision graph

The panel beside the plan is the decision history: a vertical spine (the trunk) of confirmed decisions, with branches forking sideways that fold open to their conversation. Everything below uses `dg-` classes from the same `bundle.css` and the same tokens; colour is the principle (`data-p`): a trunk node and its mark take the principle of what was decided, a branch takes 4 (5 when the reviewer opened it), a join request 4. Two rules change: a branch (a side thread) **can** change the plan, once the person says yes; and the Hover menu is the one place with icon buttons.

### Contributor mark

Who said or decided something. The shape says who, the fill says where it stands. Build it with `FAH.mark(who, state, size)`; the graph draws the same path with `FAH.shape(who, x, y, r)`.

| Shape | Who |
| --- | --- |
| circle | You |
| diamond | The assistant |
| square | The harness |
| triangle | The reviewer |

| Class on the path | Meaning |
| --- | --- |
| `dg-shape` | Filled with ink, or with `--p` under `data-p`: a decision on the trunk |
| `dg-shape--open` | Hollow: said on a branch |
| `dg-shape--dead` | Hollow and muted: on a dead branch |
| `dg-shape--needs` | The attention fill: a proposal waits for the person's yes (not while a call waits) |

The SVG carries the name in `aria-label`. Never tell contributors apart by colour.

### History (the graph)

```html
<div class="dg-graph">
  <svg class="dg-svg" aria-hidden="true"><!-- trunk, forks, joins, marks: drawn from measured positions --></svg>
  <div class="dg-row dg-row--trunk"><div class="dg-row__l"><!-- dg-node --></div><div class="dg-row__s"></div><div class="dg-row__r"></div></div>
  <div class="dg-row dg-row--branch"><div class="dg-row__l"></div><div class="dg-row__s"></div><div class="dg-row__r"><!-- dg-branch --></div></div>
  <div class="dg-row dg-row--now"><div class="dg-row__l"><span class="dg-now">Now</span></div>…</div>
</div>
```

- Decisions sit on the left of the spine, right aligned; branches on the right. Under 440px add `dg-graph--narrow`: the spine moves to a 30px column on the left and everything stacks beside it.
- Lines (`dg-l--trunk` ink 2.5px, `dg-l--branch` flow 1.75px, `dg-l--dead` dotted, `dg-l--cap` the bar that ends a dead branch, `dg-l--sel` the ring round a selected node) are drawn after layout and again on resize and on every branch `toggle`. A fork leaves the trunk 18px above the branch's title; a join arrives 8px above its node. The SVG has no meaning of its own: every line has a text equivalent in the cards.
- A joined branch sits just above the node it joined as; other branches sit after the node they left from.

### Trunk node

One confirmed decision: who (the mark on the spine, and a hidden "You, decided:"), what (one short line), and refs to what it touched.

```html
<div class="dg-node" data-node="n3">
  <button class="dg-node__title"><span class="dg-sr">You, decided: </span>Guest count: 120 → 150</button>
  <p class="dg-node__meta"><span>Changed</span><button class="dg-ref dg-ref--input">Guest count</button><span>re-ran</span><button class="dg-ref">1</button><button class="dg-ref">2</button></p>
  <div class="dg-node__results"><!-- result chips the join produced --></div>
</div>
```

The title is a button: it selects the node (a ring on the spine) and marks what it changed in the plan in place of the latest node. Escape clears it. `is-new` plays the arrival (see Motion).

### Ref

A step or input named in a node, branch or proposal, in the plan's shape language at 20px: `dg-ref` a calculation's number, `dg-ref--you` round, `dg-ref--call` dashed, `dg-ref--input` a pill with the input's name. Clicking selects that step, or that input's pills (`dg-pill--sel`), and scrolls it into view. The hit area grows 8px above and below.

### Branch

A conversation about one thing in the plan, a native `<details>`. It ends one of two ways: it joins, or it dies.

| Class | Looks | State word |
| --- | --- | --- |
| `dg-branch--open` | its principle's tint and edge (`thread` without one), open | "open", "answering", "challenge", "question"; "needs you" (semibold, `dg-branch--needs`) with a pending proposal |
| `dg-branch--joined` | tinted, folded | "joined" |
| `dg-branch--dead` | no tint, 1px `line` outline, muted | "no change", "dismissed" |

Parts: `dg-branch__on` ("From [chip]" or "On [ref]"), `dg-say` (one line: a 10px hollow mark, then the words; `dg-say--you` in ink), `dg-branch__end` ("Joined when you said yes.", "You kept 120. Nothing in the plan changed."), `dg-reply` (the branch's own reply box), `dg-branch__acts` ("Close branch"). Fold a branch when it joins or dies; a dead branch never disappears. The opening line is not repeated when the title already says it.

### Join request

The harness's proposal at the end of an open branch: the change as a question, what it changes (old struck, new in semibold), what re-runs and what lies further on, then Yes and No.

```html
<div class="dg-propose" role="group" aria-label="Proposed change">
  <p class="dg-propose__q"><svg class="dg-who">…needs…</svg>Change guest count to 150?</p>
  <p class="dg-propose__row"><button class="dg-ref dg-ref--input">Guest count</button><s>120</s>→<b>150</b></p>
  <p class="dg-propose__row"><span class="dg-propose__k">Re-runs</span><button class="dg-ref">1</button><button class="dg-ref">2</button></p>
  <p class="dg-propose__row"><span class="dg-propose__k">Further on</span>…</p>
  <div class="fah-row"><button class="fah-btn fah-btn--primary">Yes, change it</button><button class="fah-btn">Keep 120</button></div>
</div>
```

While it is pending the plan shows its impact: `dg-touch` (dashed, outside the box) on the inputs and steps that re-run, `dg-touch--far` (dotted) on the steps further on, `dg-needs` (the attention fill) on the input, unless a call is waiting, which stays the one "needs you".

### Chip

A value in place of a sentence. Kinds are told apart by shape and a glyph, never by colour alone; the colour is the principle (results and values 3, assumptions 4, a decision its node's).

| Class | Kind | Shape |
| --- | --- | --- |
| `dg-chip--given` | A value that went in ("Guest count **120**") | Round, 1px outline |
| `dg-chip--assumed` | An assumption (`◌`, `✓` once confirmed, wraps) | Dashed `flow` outline |
| `dg-chip--result` | What a step produced ("Total cost → **43,000**") | 4px corners, 1.5px ink |
| `dg-chip--decision` | A decision (the decider's mark, then the node's text) | 4px corners, 2px ink |
| `dg-chip--stale` | No longer current after a join: struck and muted | |
| `is-traced` | Its place is selected in the plan | its principle's tint |

```html
<span class="dg-chip dg-chip--given">
  <button class="dg-chip__btn" aria-label="Guest count 120, a value that went in. Show in the plan">
    <span class="dg-chip__k">Guest count</span><span class="dg-chip__v">120</span></button>
  <span class="dg-menu" role="group" aria-label="Actions for Guest count 120">…</span>
</span>
```

Clicking selects its place: the input when there is one, else the step, opening its pop-up on the run. Of a replaced run, results go stale, and of the values only the one the join changed.

### Answer

A short lead (the message's own text, figures underlined) and the chips as facts: `dg-answer`, then `dl.dg-facts` with one row per result (labelled with the step), then "Rests on" (values) and "Assumes" (assumptions). An open Notice takes the assumption chips into itself, above Confirm and Change it.

### Hover menu

Three icon buttons on a chip or an underlined figure (`dg-fig`): **See in graph** (eye), **Challenge or correct** (correction mark), **Talk about it** (thread). The last two only when layer 4 is on. It opens on hover and on keyboard focus, names the button under the pointer or focus in `dg-menu__label`, and closes on Escape with focus back on the chip. It flips below (`dg-below`) within 72px of the top of its scroll area and aligns right (`dg-end`) near the right edge. Buttons are 32px, 44px under `pointer: coarse`.

"Challenge or correct" opens a new branch on the chip's subject with its box focused ("Say what should change…"); "Talk about it" opens the branch already about it, else a new one ("Start a branch about this…"). A branch is stored only with its first message.

### In the plan

| Class | On | Meaning |
| --- | --- | --- |
| `dg-touch` | step, pill | A pending proposal (or a running join) changes it: dashed `principle-4-ink` |
| `dg-touch--far` | step | Further on: touched, not re-run |
| `dg-needs` | pill | The input a pending proposal is about |
| `dg-pill--sel` | pill | A selected input: 2.5px ink inside |
| `dg-pill--changed` | pill | Changed by the latest node; shows its value (`dg-pill__v`) |
| `dg-tag` / `dg-tag__new` | under a step | The latest node's mark and word ("re-ran", "changed", "rebuilt"), or a working line and "running again" |

---

## Screen

A small plan with a chat beside it, used to show how the pieces move together. It is a demonstration, not a component to copy whole.

The three buttons play the three sequences the real screen runs:

- **Build**: each step's tested line arrives in plan order, and its tick draws.
- **Answer**: the inputs darken, a pulse travels along the arrow, each result lands as the pulse reaches its step, and the answer arrives in the chat. Clicking a number selects the step it came from.
- **Needs you**: the pulse reaches the last step, which fills with the attention colour and rings once.

The page provides the positions. Steps and lines are placed with `position: absolute` inside one relatively positioned box; the system does not lay out the graph.

Order of calls for an answer: `FAH.setLine(first, result, 'result')`, then `await FAH.flow([line])`, then `FAH.setLine(next, result, 'result')`, and so on along the path. Fade the steps that were not used with `FAH.fade(step)`.

### Full demo source

```html
<!-- @dsCard group="Composition" height=380 width=960 subtitle="The motion, played on a small plan" -->
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>body{margin:0;background:var(--ground)}</style>
<div class="fah" style="padding:24px;display:flex;flex-direction:column;gap:20px">
  <div class="fah-row">
    <button class="fah-btn fah-btn--primary" id="play-build">Play: build</button>
    <button class="fah-btn" id="play-answer">Play: answer</button>
    <button class="fah-btn" id="play-call">Play: needs you</button>
    <button class="fah-link" id="reset" style="margin-left:8px">Reset</button>
  </div>
  <div style="display:flex;gap:32px;align-items:flex-start">
    <div id="stage" style="position:relative;flex:none;width:664px;height:150px">
      <div class="fah-pills" style="position:absolute;left:0;top:0"><span class="fah-pill" data-pill>guest count</span><span class="fah-pill" data-pill>cost per guest</span></div>
      <div class="fah-pills" style="position:absolute;left:240px;top:0"><span class="fah-pill" data-pill>payment schedule</span></div>
      <svg class="fah-flow" id="a1" width="55" height="8" viewBox="0 0 55 8" style="position:absolute;left:184px;top:60px"><path d="M0 4H51" pathLength="100"/><path class="fah-flow__head" d="M51 1l4 3-4 3z"/><path class="fah-flow__pulse" d="M0 4H51" pathLength="100"/></svg>
      <svg class="fah-flow" id="a2" width="55" height="8" viewBox="0 0 55 8" style="position:absolute;left:424px;top:60px"><path d="M0 4H51" pathLength="100"/><path class="fah-flow__head" d="M51 1l4 3-4 3z"/><path class="fah-flow__pulse" d="M0 4H51" pathLength="100"/></svg>
      <button class="fah-step" id="s1" style="position:absolute;left:0;top:28px"><span class="fah-step__name">1 Total cost</span></button>
      <button class="fah-step" id="s2" style="position:absolute;left:240px;top:28px"><span class="fah-step__name">2 Three payments</span></button>
      <button class="fah-step fah-step--your-call" id="s7" style="position:absolute;left:480px;top:28px"><span class="fah-step__name">7 Review and decide</span></button>
    </div>
    <div class="fah-chat" id="chat" style="flex:1;min-width:200px;min-height:150px"></div>
  </div>
</div>
<script>
(function () {
  var F = window.FAH;
  var s1 = document.getElementById('s1'), s2 = document.getElementById('s2'), s7 = document.getElementById('s7');
  var a1 = document.getElementById('a1'), a2 = document.getElementById('a2');
  var chat = document.getElementById('chat'), stage = document.getElementById('stage');
  var pills = stage.querySelectorAll('[data-pill]');
  var run = 0;

  function say(text, you) {
    var p = document.createElement('p');
    p.className = 'fah-msg' + (you ? ' fah-msg--you' : '');
    p.textContent = text;
    chat.appendChild(p);
    return p;
  }
  function num(text, step) {
    var n = document.createElement('span');
    n.className = 'fah-num'; n.tabIndex = 0; n.textContent = text;
    n.addEventListener('click', function () { F.trace(n, step, document); });
    return n;
  }
  function reset() {
    run++;
    [s1, s2, s7].forEach(function (s) { F.setLine(s, ''); F.needsYou(s, false); F.fade(s, false); s.classList.remove('is-arriving'); });
    F.select(null, document);
    pills.forEach(function (p) { p.classList.remove('fah-pill--used'); });
    chat.textContent = '';
    return run;
  }
  async function build() {
    var me = reset();
    say('Building the calculations…');
    await F.wait(300); if (me !== run) return;
    F.setLine(s1, '4 examples · 4/4', 'tested');
    await F.wait(350); if (me !== run) return;
    F.setLine(s2, '3 examples · 5/5', 'tested');
    await F.wait(350); if (me !== run) return;
    say('Two calculations are built and tested.');
  }
  async function answer() {
    var me = reset();
    say('What is the second payment with 150 guests at 230 each?', true);
    await F.wait(350); if (me !== run) return;
    pills.forEach(function (p) { p.classList.add('fah-pill--used'); });
    F.fade(s7);
    F.setLine(s1, '→ 43,000', 'result');
    await F.flow([a1]); if (me !== run) return;
    F.setLine(s2, '→ 6,000 + 2×18,500', 'result');
    await F.wait(300); if (me !== run) return;
    var p = say('With a total of ');
    p.appendChild(num('43,000', s1));
    p.appendChild(document.createTextNode(', the second payment is '));
    p.appendChild(num('18,500', s2));
    p.appendChild(document.createTextNode('. Click a number.'));
  }
  async function call() {
    var me = reset();
    await F.flow([a1, a2]); if (me !== run) return;
    F.needsYou(s7);
    F.setLine(s7, 'Needs you', 'strong');
    say('The steps before this one are done. This one is yours.');
  }
  document.getElementById('play-build').addEventListener('click', build);
  document.getElementById('play-answer').addEventListener('click', answer);
  document.getElementById('play-call').addEventListener('click', call);
  document.getElementById('reset').addEventListener('click', reset);
  [s1, s2, s7].forEach(function (s) { s.addEventListener('click', function () { F.select(s, document); }); });
  build();
})();
</script>
```
