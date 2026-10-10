# Financial Advisor Harness

The interface of an agent harness for personal finance. One screen: the plan as a diagram of steps, and a chat beside it. The diagram is the product; the chat is how the person and the agent change it.

This system holds the tokens, the component styles and a small script for motion. It has no framework and no dependencies, so it drops into a single self-contained HTML page.

## Files in this folder

| File | What it is |
| --- | --- |
| `README.md` | This page: principles, colour, type, shape, voice |
| `tokens.json` | The source of every token, with a usage note on each |
| `tokens.css` | The tokens compiled to CSS custom properties, light and dark |
| `bundle.css` | Styles for every component |
| `bundle.js` | `window.FAH`: helpers for state and motion |
| `index.d.ts` | The helpers' signatures, as documentation |
| `components.md` | Markup and rules for each component, and a full demo |
| `motion.md` | Timings, the moments that move, and the rules |

The same system is published as the design system artifact "Financial Advisor Harness", where each component has a live preview. The agreed product behaviour is in `claude/ui-design-decisions.md`.

## How to use it

1. Load `tokens.css` (generated from `tokens.json`), then `bundle.css`, then `bundle.js`.
2. Wrap the screen in one element with class `fah`. It sets the font, text colour and tabular figures.
3. Write components as plain HTML with `fah-` classes. Each component's page shows the markup.
4. Call `window.FAH` when state changes. The helpers only add and remove classes; they never fetch, store or build layout.

For a page that must work with no network, copy the three files inline and drop the web font link. The font stack falls back to Segoe UI and the system sans.

Set `data-theme="dark"` on the root element for the dark theme. Light is the default.

Positioning steps and drawing the lines between them is the page's job. The system styles a step and a line; it does not lay out a graph.

## Principles

- **The diagram carries the state.** A step shows its name and at most one more line. If nothing happened to a step, it says nothing.
- **One attention colour.** `needs-you` fills the step that is waiting on the person. It is never used for selection, hover, emphasis or decoration.
- **Selection is an outline.** A selected step gets a 3px ink outline drawn inside its box, so nothing moves.
- **Nothing blocks unless the call is the person's.** Anything unconfirmed runs and carries a mark.
- **Every figure leads somewhere.** A number in the chat is underlined and selects the step that produced it.
- **Quiet by default.** Pills, origin marks and threads are small and low contrast until they are used.

## Colour

Twelve colours in two themes. Each has one job; the token notes say which text goes on which ground.

| Token | Job |
| --- | --- |
| `ground`, `surface` | The page, and everything that sits on it |
| `ink`, `ink-2`, `muted` | Text, from primary to quiet. `ink` also draws step outlines and fills primary buttons |
| `line`, `flow` | Hairlines, and the arrows between steps |
| `needs-you` | The step waiting on the person. Nothing else |
| `tested` | The tick on a step whose tests pass |
| `thread`, `bubble` | Side and reviewer threads; the person's own messages |
| `on-ink` | Text on an ink fill |

Do not add a red. A failed build is a step that needs the person, so it uses `needs-you`.

## Type

IBM Plex Sans in two weights, 400 and 600. Seven styles, from the 22px goal down to the 11px pill. Figures are tabular everywhere, so amounts line up and do not jitter when they change.

Write step names as a number and a short noun phrase: "5 Fund balance". Write a step's second line as a fact, not a sentence: "4 examples · 6/6", "→ 43,000", "Needs you · not built".

## Shape

- A calculation step is a rectangle with a 6px corner.
- A figure from the person is the same box with a 36px corner, so it reads as a pill.
- A call that is the person's has a dashed outline.
- An input is a small pill sitting just above the step that uses it.

The three kinds differ in shape, not colour, so they hold up in greyscale and for colour-blind readers.

## Marks

Text marks, not an icon set: `●` an open question, `↗` looked up, `✎` proposed by the assistant, `▲` challenged by the reviewer, `◌` rests on something unconfirmed, `→` a result. The tick is the only drawn mark; `FAH.tick()` builds it.

## Motion

See the Motion section. In short: things respond in 120ms, enter in 200ms, and the two signature moments (a tick drawing, a pulse travelling along an arrow) take 500ms. Nothing loops except the working line. All of it switches off under reduced motion.

## Voice

Plain and short. Name things the way the person would: "the plan", "a step", "needs you", "on the side". Buttons say what happens: "Accept plan", "Use this", "Dismiss". The interface never apologises and never explains itself in the diagram.
