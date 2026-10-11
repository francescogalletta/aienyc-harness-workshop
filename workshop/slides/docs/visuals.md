# Visuals: charts, diagrams and animation

Decision record, October 2026. Status: adopted.

## The question

The deck needed charts (a wedding fund over time, where the money goes),
diagrams (flows, branches) and some motion, without breaking what the deck
already is: one self-contained HTML file on a fixed 1920×1080 stage, styled
only by tokens, built by a standard-library Python script, steps driven by the
deck's own engine, hosted in a page with a strict Content Security Policy.

## What was compared

A research pass built the same slide (a five-step flow with a travelling
marker, a bar chart with a highlighted bar, a count-up) in each candidate, in
three themes, light and dark, under the host's CSP:

- plain SVG + CSS + Web Animations (no library);
- Rough.js (hand-drawn rendering of SVG shapes);
- Mermaid;
- Chart.js (canvas);
- Apache ECharts (SVG renderer);
- Observable Plot and Vega-Lite;
- animation engines: Web Animations, SMIL, GSAP, Motion, anime.js;
- whole frameworks: reveal.js, Slidev, Marp.

## What was chosen

**Default: a small in-house kit**, `src/js/viz.js` + `src/styles/viz.css`.
Slides declare a visual in TOML; the build writes a `<figure data-viz data-spec>`
with a hidden data table; `viz.js` draws inline SVG at load time.

- Colours are CSS classes reading `--viz-*` tokens, which map onto the theme's
  roles in one block at the end of `styles/tokens.css`. Light, dark and theme
  switches repaint with no JavaScript, and all three themes work with no edits.
- Steps are the deck's own: drawn parts carry `data-step`, so the deck counts
  and shows them. Motion is CSS keyed on `.shown`; Web Animations only for the
  travelling marker, rAF only for the count-up. `.instant` (arriving at a slide),
  `animate = false` and `prefers-reduced-motion` show end states at once.
- Nothing is added to a build that does not use it: today's `deck.html` is
  byte-identical with the kit in the repository.

**On the shelf**, vendored under `src/vendor/` with licences, inlined only
into a build whose slides ask for them:

- **Rough.js 4.6.6** (MIT) for `style = "rough"`, the look of the hand-drawn
  sketch. It needs concrete colours, so rough figures redraw on a theme change.
- **anime.js 4.5.0** (MIT) for `choreo`: multi-element sequences on one click,
  undone when stepping back.
- **Apache ECharts 6.1.0, `common` build, SVG renderer** (Apache-2.0) for charts
  the kit does not draw. The full build contains `new Function`, which the host
  CSP forbids; `common` does not. The adapter injects token-driven defaults
  (fonts, text, axis and grid colours, series palette, no animation under
  reduced motion) and re-applies them when the theme changes.

## Why not the others

- **Mermaid**: 1.57 MB gzipped, its own look that fights the tokens, and layout
  it decides for you. Rejected for weight and look.
- **Canvas chart libraries** (Chart.js and similar): pixels, so no `var()`
  colours, no crisp scaling with the stage, no hidden-table accessibility for free.
- **Plot / Vega-Lite**: good grammars, heavy for what the deck draws, and
  Vega-Lite needs an interpreter to run under the CSP.
- **GSAP / Motion**: capable, but CSS + Web Animations cover the deck's needs;
  anime.js is kept for the rare multi-element sequence.
- **WASM tools** (Graphviz builds and similar): blocked or awkward under the CSP.
- **Switching framework** (reveal.js, Slidev, Marp): each replaces the step
  engine but not the figure work, and fights the fixed stage, the tokens, the
  single file and the Python-only build.

Findings the kit respects:

- No engine can tween `var()` colours, so a colour change is a CSS crossfade of
  a second shape (the highlighted bar).
- A `data-step` above the slide would be hidden by the deck's own rule, so step
  attributes live only inside slides.
- CSS features without Firefox/Safari support are avoided where a plain
  alternative exists: no `round()`/`mod()` counters (the count-up is JS), SVG `rx`
  is set as an attribute, the marker moves with transform keyframes rather than
  `offset-path`.

## Weights (measured on what is vendored, gzip -9)

| Piece | Raw | Gzipped |
| --- | --- | --- |
| Kit: `viz.js` + `viz.css` + the `--viz-*` tokens | 42.8 KB | 12.8 KB |
| Rough.js 4.6.6 `bundled/rough.js` | 27.1 KB | 8.7 KB |
| anime.js 4.5.0 `anime.umd.min.js` | 115.3 KB | 39.6 KB |
| ECharts 6.1.0 `echarts.common.min.js` | 697.7 KB | 234.2 KB |

| Build | Raw | Gzipped |
| --- | --- | --- |
| `deck.html` (no visuals) | 79.9 KB | 20.5 KB |
| Gallery, kit only | 147.2 KB | 37.0 KB |
| Gallery, kit + Rough.js | 174.4 KB | 45.7 KB |
| Gallery, kit + anime.js | 262.5 KB | 76.6 KB |
| Gallery, kit + ECharts | 845.0 KB | 271.2 KB |
| Gallery, everything | 987.7 KB | 319.0 KB |

The research estimate for the kit was about 5 KB gzipped; the hardened kit is
12.8 KB, unminified and commented, with eight types plus marks and choreography.

## Chart palette

The principle hues double as the series palette, reordered so that neighbours
stay apart for colour-blind readers: series 1 to 5 are principles 1, 4, 2, 5, 3.
In the deck's own order, principles 1 and 2 (blue and violet) are nearly the
same colour under deuteranopia (ΔE 1.0 in blueprint). Results from the dataviz
validator (`validate_palette.js`, adjacent pairs, against each mode's background):

| Theme | Mode | Result |
| --- | --- | --- |
| blueprint | light | all checks pass (worst CVD ΔE 11.2) |
| blueprint | dark | CVD 11.7 and normal vision 23.7 pass; lightness band fails (the dark-mode pastels are L 0.76–0.81, chosen to carry dark text) |

Charts in the kit use one or two series and a highlight. A single-series chart
draws in `--viz-primary` (principle 1's ink unless a look says otherwise), the
highlight in `--viz-highlight` (the look's attention colour, or its ink in
swiss), so the highlight never doubles as a series colour. Values are always
labelled or tabled, so identity never rests on colour alone.

### Candidate looks (October 2026)

Each look sets its own series order (`--viz-series-*` in its theme file),
chosen for colour-blind separation of neighbours. Validator results, adjacent
pairs, against each palette's ground (series listed in order):

| Look | Palette | Series (principles) | Result |
| --- | --- | --- | --- |
| blueprint-night | primary | 1, 4, 2, 5, 3 | CVD 11.7, normal 23.7, contrast pass; lightness band fails (pastels that carry navy text) |
| blueprint-night | alternate | 1, 4, 2, 5, 3 | all checks pass (CVD 11.2) |
| catppuccin | Macchiato | 1, 5, 2, 4, 3 | CVD 12.6 passes; normal vision 13.0, lightness and chroma fail (Catppuccin's pastels are close in lightness by design) |
| catppuccin | Latte | 1, 5, 2, 4, 3 | CVD 19.9, normal 20.5 pass; contrast warns for pink and peach on base (their inks are used for text) |
| nord | Polar Night | 1, 4, 2, 5, 3 | CVD 8.9, normal 15.5 pass; lightness and chroma fail (Nord's aurora is deliberately muted) |
| nord | Snow Storm | 1, 4, 2, 5, 3 | same fills: CVD 8.9, normal 15.5 pass; contrast warns (inks are used for lines and text) |
| swiss | primary | 4, 2, 5, 1, 3 | all checks pass (CVD 21.1) |
| swiss | graphite | 4, 2, 5, 1, 3 | CVD 14.0, normal 20.4 pass; lightness band fails (L 0.76 fields that carry ink text) |
| prospectus | primary | 4, 2, 5, 1, 3 | CVD 9.1, normal 15.1 pass; lightness and chroma fail (muted deep fields) |
| prospectus | ink-dark | 4, 2, 5, 1, 3 | CVD 10.4 passes; normal 12.2, lightness and chroma fail (soft tints) |

The first two series pass CVD in every look and palette (ΔE ≥ 17). The
lightness and chroma failures come from the palettes themselves: the community
palettes are used as published, and the brief asked for muted fields in
prospectus and pastel fields with dark text in the dark looks.

### Palette sources and deviations

The community palettes are taken from their npm packages; a value changes only
where a contrast check failed, and then by the smallest OKLCH lightness step
that passes. Every deviation is also listed in the theme's header comment.

- **catppuccin**: `@catppuccin/palette` 1.8.0, MIT licence, (c) 2021
  Catppuccin. Macchiato is used unchanged. Latte: subtext0 #6c6f85 → #696c82
  (muted text 4.5:1), teal #179299 → #007a81 (trust 4.5:1); text-strength inks
  pink #ea76cb → #d361b6, peach #fe640b → #f25800, green #40a02b → #3e9e29 and
  yellow #df8e1d → #c87800 (chart highlight), each for 3:1 on base. Text on
  Latte's blue and mauve fields is Latte base; on the others, Macchiato crust.
- **nord**: `nord` 0.2.1 (Arctic Ice Studio), licence Apache-2.0 AND
  CC-BY-SA-4.0 as the package declares. Polar Night: nord3 lifted to #687388
  for outlines, dashes and connectors and to #909cb2 for muted text (4.5:1;
  Nord has no mid grey); nord11 #bf616a → #d6767e and nord12 #d08770 → #d38972
  as fills (nord0 text at 4:1 and 4.5:1). Snow Storm: nord7 → #497474 as trust
  (4.5:1); inks nord15 → #a47e9d, nord13 → #a48547, nord14 → #779161,
  nord12 → #be7660 (3:1 on nord6). The QR tile is nord4, not nord6, on the dark
  ground.
- **blueprint-night**: the workshop's own blueprint palette on a navy ground;
  the ask is apricot-200 one step down (#f0c396) so it does not glare.
- **swiss** and **prospectus**: palettes made for this deck (OKLCH section
  families for swiss; named deep fields for prospectus), with dimmer ask fills
  on their dark alternates (#e8c000, #dcc48a).


## Not tested

- Firefox and Safari: only Chromium was run (Playwright's build).
- Google Fonts: the sandbox cannot reach them, so screenshots used local
  woff2 copies of the same families (IBM Plex, Caveat, Figtree, JetBrains Mono,
  Schibsted Grotesk, Instrument Serif and Instrument Sans, from their npm
  packages) injected as data URIs; the hosted page loads them from Google.
- Projectors: sizes were judged on 1920×1080 screenshots (chart labels are 30 px
  and up on the stage).
