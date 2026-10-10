# Motion

Motion here does one job: it shows that something changed, and where. It is never decoration, and nothing moves while the person is reading.

## Timing

| Token | Value | Used for |
| --- | --- | --- |
| `dur-fast` | 120ms | Hover, press, selection |
| `dur-base` | 200ms | A message, pop-up or thread entering; a fill changing |
| `dur-slow` | 360ms | A step's new line arriving |
| `dur-draw` | 500ms | The tick drawing; one pulse along an arrow |
| `ease-out` | `cubic-bezier(0.2, 0, 0, 1)` | Everything that enters or responds |
| `ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | The pulse along an arrow |

## The moments

| Moment | What moves | How to trigger |
| --- | --- | --- |
| A step is tested | Its line rises 4px and fades in; the tick draws itself | `FAH.setLine(step, '4 examples · 6/6', 'tested')` |
| A result comes out | The result line rises in | `FAH.setLine(step, '→ 43,000', 'result')` |
| An answer runs | One ink pulse travels along each arrow, in the order the value flows | `FAH.flow([line1, line2])` |
| A step needs you | The fill fades to the attention colour and one ring expands and fades | `FAH.needsYou(step)` |
| A step is selected | The outline thickens inside the box, with no reflow | `FAH.select(step)` |
| A number is traced | The number takes a tint; its step is selected and scrolled into view | `FAH.trace(num, step)` |
| A step was not used | Its outline and text ease to the faded colours | `FAH.fade(step)` |
| A message arrives | It rises 4px and fades in | automatic on `.fah-msg` |
| A thread opens | The marker turns a quarter; the body rises in | automatic on `details.fah-thread` |
| A pop-up opens | It scales from 97% at its top-left corner | automatic on `.fah-pop` |
| The agent is working | A short line with a sliding segment. The only loop | `.fah-working` |
| Hover and press | A step lifts 1px with the pop shadow; a press settles to 99% | automatic |

## Rules

- **One thing at a time.** When several steps change, stagger them in plan order, about 150ms apart. Do not animate the whole diagram at once.
- **The pulse follows the data.** Run `FAH.flow` first and set each step's result as its pulse lands, so the eye is led from input to answer.
- **The ring plays once.** The attention colour stays; the ring does not repeat. A looping pulse would nag.
- **Nothing moves the layout.** Outlines are drawn inside the box and lines enter by opacity and a 4px rise, so text never reflows.
- **Reduced motion.** Under `prefers-reduced-motion: reduce` every animation and transition is cut to nothing. State still changes; it just does not travel.
