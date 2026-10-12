# Workshop slides

`deck.html` is the deck for the session: one self-contained page you open in a
browser. It is built from the sources in `src/` by `build.py` (Python 3.11+,
standard library only, no network). The harness never uses this folder.
Keys: arrows, Space or a click step; `F` fullscreen; `D` the other palette;
`T` / `Shift+T` the next or previous look (in a `--looks` page); `#12` opens slide 12.

## Build

Run from the repository root:

```
python workshop/slides/build.py                    # deck.html (default theme) + dist/deck.fragment.html
python workshop/slides/build.py --theme catppuccin # one theme into dist/
python workshop/slides/build.py --all              # every theme into dist/
python workshop/slides/build.py --gallery --all    # the review deck, dist/gallery.<theme>.html
python workshop/slides/build.py --looks nord,catppuccin,blueprint [--gallery]  # one page with a look switcher
python workshop/slides/build.py --check            # validate everything; exits 1 on problems
```

`deck.html` is the only built file committed; `dist/` is ignored. Same sources
give byte-identical output. Each build also writes a `.fragment.html` for the
hosting page. `--check` says when `deck.html` is out of date: run `build.py` and
`--check` before committing. The gallery shows colour roles, type scale,
layouts, components and visuals on sample data.

## Where things are

```
build.py, deck.html      the build and checks; the built deck (committed)
src/deck.toml            title, default theme, palette, section order
src/principles.json      the five principles
src/slides/*.toml        the words: one file per section, slides in order
src/layouts/             layouts.toml (the vocabulary) + one template per layout
src/themes/*.css         one file per look: nord, catppuccin, blueprint
src/styles/              tokens.css (defaults), base, components, viz, looks
src/js/                  deck.js (steps), viz.js (visuals kit), confetti.js, looks.js
src/assets/, src/vendor/ qr.json, sample-draw.svg; Rough.js (optional) with its LICENSE
src/gallery/             the gallery's sections, gallery.css, gallery.js
tools/, tests/           qr.py, shoot.py (optional), fonts.json; pytest
```

## Edit a slide

Find the words with a search in `src/slides/`, change them, build. A slide is a
`[[slide]]` with an `id`, a `name`, a `layout` and that layout's fields. A
statement slide is a list of blocks, top to bottom:

```toml
[[slide]]
id = "s-example"
name = "Example"
layout = "statement"
blocks = [
  { display = "A line shown at once." },
  { sub = "A second one, at the first click.", step = 1 },
]
footnote = { text = "* A footnote, at the second click.", step = 2 }
```

- `step = n` shows a thing at click n (`out`, `mute`, `strike`, `fill` likewise).
- In text: `==trust==` is the trust accent; `[words]{aside step=3}` a handwritten
  aside at click 3; `[words]{strike=2}` strikes them at click 2.
- Every layout, block role and inline role is listed, with its fields, in
  `src/layouts/layouts.toml` (spacing between blocks is automatic, `gap = "l"`
  overrides it). `raw` takes bespoke HTML when nothing fits.
- Slides are numbered by position: move one by moving its `[[slide]]`.
  `group = "…"` at the top of a section file sets its section label.
- The QR code, `src/assets/qr.json`, is written by `tools/qr.py` (needs `segno`).

**The five principles** are one line each in `src/principles.json`: name, emoji,
colour token, statement and "builds on" line. The structure slides, the
framework stack, the rail and the dividers all follow it.

## Change the look

Everything visual is a token. `src/styles/tokens.css` holds the defaults (type
scale, spacing, radii, strokes, motion, component sizes); a theme file sets the
palette, fonts and colour roles and may override any other token. Components
never contain colours, font names, sizes, radii or paddings (`--check` enforces
it). To change the look, edit one theme file in `src/themes/`, rebuild, and
look at the gallery. One knob for all type: `--type-scale`.

Three themes ship, each with a primary and an alternate palette:

- `nord` (default): Polar Night (dark), then Snow Storm (light).
- `catppuccin`: Macchiato (dark), then Latte (light).
- `blueprint`: navy ink on pale blue-grey (light), then night, a deep navy with a faint grid (dark).

`palette` in `src/deck.toml` chooses what people see: `"primary"` (default, for
everyone), `"alternate"`, or `"system"` (the one matching the viewer's light or
dark setting). `D` toggles in every mode. The deck uses its own
`data-palette="alternate"` attribute, so a host page's `data-theme` never flips it.

## Palettes

Each palette lives in one file, `src/themes/<name>.css`. The **primary** is on
`:root`: raw palette values first, then the colour roles that point at them. The
**alternate** is under `:root[data-palette="alternate"]`: only the roles that
differ. Each block ends with its `color-scheme: light | dark`. Write each palette
once; the build adds what the `palette` setting needs. Do not write `data-theme`
or `prefers-color-scheme` in a theme (`--check` refuses it).

| Role token | Means |
| --- | --- |
| `--slide-bg`, `--surface` | slide ground; boxes and panels, one step off it |
| `--text`, `--text-quiet`, `--text-muted` | main, secondary and tertiary text |
| `--outline` | box outlines |
| `--hairline`, `--line`, `--connector` | pill and rail strokes, dividers; arrows |
| `--accent-trust` | the trust accent (`==words==`) |
| `--attention` | the big ask (`--ask-fill`, `--ask-text`) and the chart highlight |
| `--principle-1..5` | the fill of each principle |
| `--on-principle`, `--on-principle-N` | text on a principle fill; `--principle-N-ink` is the hue as text or a line on the ground |
| `--qr-ink`, `--qr-ground` | the QR code |
| `--viz-primary`, `-highlight`, `-up`, `-down`, `-total` | chart roles, each with an `-ink` form for hand-drawn charts |
| `--viz-series-1..5`, `--viz-grid`, `--viz-axis`, `--viz-muted` | multi-series order (kept apart for colour-blind viewers); chart rules and labels |

`--check` enforces in both palettes of every theme: `--text` on the ground 7:1;
quiet and muted text, trust accent, text on `--surface`, pill and ask text 4.5:1;
each `--on-principle-N` on its fill 4:1; each ink on the ground 3:1; the QR 7:1;
and a `color-scheme` on every block.

**Credits.** Nord: `nord` 0.2.1 (Arctic Ice Studio), licence Apache-2.0 AND
CC-BY-SA-4.0 as the package declares. Catppuccin: `@catppuccin/palette` 1.8.0,
MIT, (c) 2021 Catppuccin. Blueprint is the workshop's own. A community colour
changes only where a contrast check failed, by the smallest lightness step that
passes; each deviation is listed in the theme's header comment.

## Add a chart, diagram or animation

Charts and diagrams use a small in-house kit (`src/js/viz.js`, `src/styles/viz.css`)
that draws SVG themed by the tokens, so every theme works with no edits and the
steps are the deck's own. Rough.js (`src/vendor/rough/`) is optional: it gives
`style = "rough"` a hand-drawn look and is inlined only into a build whose slides
use it. Mermaid, canvas chart libraries and whole slide frameworks were
considered and rejected: too heavy, a look that fights the tokens, a different build.

A visual is a block, `{ viz = "<type>", label = "…", … }`, in a statement slide's
`blocks` or the `figure` of a `figure` slide. `label` is required (a screen
reader hears it). `step = n` is the click it appears on; `animate = false` keeps
it still. `--check` rejects unknown keys and bad data.

```toml
{ viz = "flow", label = "Ask, plan, check", nodes = ["Ask", { text = "Plan", principle = 1 }, { text = "Check", role = "accent", step = 2 }], travel = 3 }
{ viz = "bars", label = "Balance by date", data = [["Jan 15", 18200], ["Jun 10", 9800]], highlight = "Jun 10", highlight_step = 2, prefix = "$" }
```

Others: `line` (`x`, `series`), `waterfall` (start, changes, end), `timeline` (events with dates), `count`
(a number that counts up), and `draw`: `svg = "sample-draw.svg"` strokes in any SVG
from `src/assets`, one `data-step` group per click, using the `.ln` (line), `.nm`
(label) and `.note` (handwritten) classes so it follows the theme. Any of them
takes `style = "rough"`. A slide may also take `marks = [ { target = ".display .hook",
kind = "circle", step = 2 } ]` (`underline`, `circle`, `bracket`, `box`) on text
written as `[words]{hook}`. The gallery shows every type (`src/gallery/visuals.toml`).

## Add a theme

Copy `src/themes/blueprint.css` to `src/themes/NAME.css` and change the values.
Keep the header comment (`font-link:` is required; `name:` and `short:` label the
looks bar), the primary palette on `:root` and the alternate under
`:root[data-palette="alternate"]`. Then build with `--theme NAME` and run `--check`,
which lists missing tokens and reports contrast. If the theme loads new font
faces, add them to `tools/fonts.json` for screenshots.

## Tests and screenshots

`python -m pytest workshop/slides/tests -q` (from the repo root) needs only
pytest; `tests/test_palette_browser.py` needs Playwright and is skipped without
it. `tools/shoot.py` (optional, Playwright and Chromium) takes screenshots and
steps through every slide checking console errors, the address, elements outside
the 1920×1080 stage and phone-width scrolling:

```
python workshop/slides/tools/shoot.py shots workshop/slides/deck.html OUTDIR --set review
python workshop/slides/tools/shoot.py check workshop/slides/deck.html --csp   # under the host's CSP
```

Where Google Fonts cannot be reached, pass `--font-dir` (or set `DECK_FONT_DIR`)
to a folder of the woff2 files listed in `tools/fonts.json`. Also: `frames` (one
slide at chosen steps) and `compare BEFORE AFTER` (diff two folders of shots).

**Not tested:** Firefox and Safari (only Chromium was run), projectors (sizes
were judged on 1920×1080 screenshots), the hosted Google Fonts (screenshots use
local copies).
