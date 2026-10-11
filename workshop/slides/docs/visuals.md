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
| ink | both | CVD 19.7 and normal vision 26.4 pass; lightness band fails (bright hues on near-black) |
| paper | light | chroma fails for ochre (0.094) and CVD fails between clay and moss (ΔE 3.2), which sit next to each other in this order |
| paper | dark | lightness, chroma, CVD (3.3) and normal vision (14.2) fail |

Charts in the kit use one or two series and a highlight, which are series 1
and 2 (principles 1 and 4). That pair passes in every theme and mode (CVD
ΔE ≥ 19). Values are always labelled or tabled, so identity never rests on
colour alone. A theme can fix its own order: for paper, setting
`--viz-series-1..5` to principles 3, 1, 5, 2, 4 passes CVD (ΔE 12.6) in both
modes. That override is not applied: the example themes are left as they were
reviewed, to show the kit working with no theme edits.

### Candidate looks (October 2026)

Each look sets its own series order (`--viz-series-*` in its theme file).
Validator results, adjacent pairs, against each palette's ground:

| Look | Primary | Alternate |
| --- | --- | --- |
| dusk | CVD 11.4, normal 24.4 pass; lightness band fails (luminous fills on dark slate) | same fills: same result |
| mist | all checks pass (CVD 12.0) | CVD 8.1, normal 15.7 pass; lightness band fails (tints) |
| chalkboard | CVD 11.3, normal 17.8 pass; lightness band fails (chalk pastels) | all checks pass (CVD 17.0) |
| ledger | all checks pass (CVD 11.9) | CVD 11.1, normal 16.7 pass; lightness band fails (tints) |
| receipt | all checks pass (CVD 9.7): its series are the pen inks, not the pale highlighters | CVD 8.5, normal 16.8 pass; lightness and chroma fail (highlighters on dark) |

The first two series pass in every look and palette (CVD ΔE ≥ 21). The
lightness-band failures come from the brief itself: luminous or pastel fills
that carry dark text.

## Not tested

- Firefox and Safari: only Chromium was run (Playwright's build).
- Google Fonts: the sandbox cannot reach them, so screenshots used local
  woff2 copies of the same families (IBM Plex, Caveat, Space Grotesk,
  Fraunces) injected as data URIs; the hosted page loads them from Google.
- Projectors: sizes were judged on 1920×1080 screenshots (chart labels are 30 px
  and up on the stage).
