"""Tests for the slide build: the template engine, inline markup, themes, and the deck.

    python -m pytest workshop/slides/tests -q
"""
import re
import shutil
import sys
from pathlib import Path

import pytest

SLIDES = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SLIDES))
import build  # noqa: E402
from build import BuildError, Markup, Template, TemplateError  # noqa: E402


def render(src, **ctx):
    return Template(src).render(ctx, {"up": str.upper, "raw": Markup})


# ---------- template engine ----------
def test_variables_are_escaped_and_markup_is_not():
    assert render("<b>{{ x }}</b>", x="a<b>&\"") == "<b>a&lt;b&gt;&amp;&quot;</b>"
    assert render("{{ x }}", x=Markup("<i>ok</i>")) == "<i>ok</i>"
    assert render("{{ x|raw }}", x="<i>ok</i>") == "<i>ok</i>"


def test_dotted_lookup_filters_and_numbers():
    assert render("{{ a.b.0|up }} {{ n }}", a={"b": ["x"]}, n=3) == "X 3"


def test_if_elif_else_not():
    t = "{% if a %}A{% elif not b %}notB{% else %}E{% endif %}"
    assert render(t, a=1, b=0) == "A"
    assert render(t, a=0, b=0) == "notB"
    assert render(t, a=0, b=1) == "E"
    assert render("{% if missing %}x{% endif %}") == ""


def test_for_loop_variables_and_nesting():
    t = "{% for r in rows %}{{ loop.index }}{% if loop.first %}^{% endif %}{% for c in r %}{{ c }}{% endfor %}{% if not loop.last %},{% endif %}{% endfor %}"
    assert render(t, rows=[["a", "b"], ["c"]]) == "1^ab,2c"


def test_tag_only_lines_disappear_but_include_keeps_indent(tmp_path):
    (tmp_path / "part.html").write_text("<i>{{ v }}</i>\n")
    (tmp_path / "main.html").write_text("<ul>\n{% for v in vs %}\n  {% include \"part.html\" %}\n{% endfor %}\n</ul>\n")
    out = build.Loader(tmp_path).get("main.html").render({"vs": [1, 2]})
    assert out == "<ul>\n  <i>1</i>\n\n  <i>2</i>\n\n</ul>\n"


def test_comments_are_dropped():
    assert render("a\n{# a note\n   over lines #}\nb") == "a\nb"


@pytest.mark.parametrize("src", ["{{ nope }}", "{% for x in nope %}{% endfor %}", "{{ a|nofilter }}"])
def test_undefined_and_unknown_are_errors(src):
    with pytest.raises(TemplateError):
        render(src, a=1)


@pytest.mark.parametrize("src", ["{% if a %}", "{% endif %}", "{% for x %}{% endfor %}", "{% bogus %}", "{{ 1+1 }}"])
def test_malformed_templates_are_errors(src):
    with pytest.raises(TemplateError):
        Template(src)


# ---------- inline markup and step attributes ----------
ROLES = {"accent": "trust", "aside": "hand-aside", "who": "ask-who"}


def test_inline_accent_and_spans():
    assert build.inline("Earn the ==trust==.", ROLES) == 'Earn the <span class="trust">trust</span>.'
    assert build.inline("x [(unpaid)]{aside step=1}", ROLES) == 'x <span class="hand-aside" data-step="1">(unpaid)</span>'
    assert build.inline("[a]{aside who step=2}", ROLES) == '<span class="hand-aside ask-who" data-step="2">a</span>'
    assert build.inline("[Financial Analyst]{strike=2}", ROLES) == '<span data-step-strike="2">Financial Analyst</span>'
    assert build.inline("a < b & c", ROLES) == "a &lt; b &amp; c"


def test_inline_rejects_unknown_roles_and_keys():
    with pytest.raises(BuildError):
        build.inline("[x]{shout}", ROLES)
    with pytest.raises(BuildError):
        build.inline("[x]{color=red}", ROLES)


def test_reveal_order_and_validation():
    assert build.reveal({"mute": 2, "step": 1}) == ' data-step="1" data-step-mute="2"'
    assert build.reveal({}) == ""
    with pytest.raises(BuildError):
        build.reveal({"step": "soon"})


def test_sequences_for_swap_and_tally():
    assert build.SlideRenderer.sequence(3) == [{"step": None, "out": 1}, {"step": 1, "out": 2}, {"step": 2, "out": None}]
    assert build.SlideRenderer.sequence(2, 1, "mute") == [{"step": 1, "mute": 2}, {"step": 2, "mute": None}]


# ---------- themes ----------
def test_theme_dark_block_is_written_once_and_emitted_twice():
    css = build.Theme(SLIDES / "src" / "themes" / "blueprint.css").css()
    assert css.count("--slide-bg: var(--navy-950);") == 2
    assert '@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {' in css
    assert css.count("color-scheme: dark;") == 2 and "color-scheme: light;" in css


def test_literal_checker_finds_literals():
    bad = ".a { color: #fff; font-size: 12px; font-family: Arial; border-radius: 4px; padding: 3px var(--x); }"
    kinds = " ".join(build.literal_problems("x.css", bad))
    for kind in ("literal colour", "literal font size", "literal font family", "literal radius", "literal length"):
        assert kind in kinds
    assert build.literal_problems("x.css", ".a { margin: calc(var(--x) * -1) 0; font-size: var(--y); }") == []


# ---------- the deck ----------
@pytest.fixture(scope="module")
def deck():
    return build.Deck()


def test_build_is_deterministic(deck):
    assert build.build(deck, "blueprint", True) == build.build(build.Deck(), "blueprint", True)


def test_fragment_and_standalone_shapes(deck):
    frag = build.build(deck, "blueprint", False)
    stand = build.build(deck, "blueprint", True)
    assert frag.startswith("<title>")
    for tag in ("<!doctype", "<html", "<head", "<body"):
        assert tag not in frag.lower()
    assert frag.count("<style>") == frag.count("<script>") == 1
    assert stand.startswith("<!doctype html>") and "[hidden] { display: none !important; }" in stand
    assert frag.split("\n")[1].startswith("<link rel=\"stylesheet\"")


def test_committed_deck_html_is_current(deck):
    assert (SLIDES / "deck.html").read_text(encoding="utf-8") == build.build(deck, deck.meta["theme"], True), \
        "deck.html is stale: run python workshop/slides/build.py"


def test_slides_numbered_and_unique(deck):
    html = build.SlideRenderer(deck).render_all()
    assert html.count("<section ") == 52
    assert "<!-- 05 · Trust -->" in html
    ids = [s for s in html.split('id="')[1:]]
    assert len({i.split('"')[0] for i in ids}) == len(ids)


def test_check_passes(deck, capsys):
    assert build.check(deck) == 0


def test_every_theme_builds(deck):
    for name in deck.themes:
        assert "<section" in build.build(deck, name, False)


def copy_src(tmp_path):
    src = tmp_path / "src"
    shutil.copytree(SLIDES / "src", src)
    return src


def test_principle_is_a_one_line_edit(tmp_path):
    src = copy_src(tmp_path)
    p = src / "principles.json"
    p.write_text(p.read_text(encoding="utf-8").replace('"Evidence", "emoji": "🧾"', '"Provenance", "emoji": "🪪"'), encoding="utf-8")
    html = build.build(build.Deck(src), "blueprint", False)
    assert "Evidence" not in html and "🧾" not in html
    assert html.count("Provenance") == 11 and html.count("🪪") == 4  # flow, stack, stack again, divider (+ its comment), 6 section labels


def test_check_catches_broken_sources(tmp_path, capsys):
    src = copy_src(tmp_path)
    comp = src / "styles" / "components.css"
    comp.write_text(comp.read_text(encoding="utf-8") + "\n.x { color: #123456; padding: var(--nope); }\n", encoding="utf-8")
    (src / "themes" / "ink.css").write_text((src / "themes" / "ink.css").read_text(encoding="utf-8").replace("--principle-5: var(--lilac);", ""), encoding="utf-8")
    sec = src / "slides" / "wrap.toml"
    sec.write_text(sec.read_text(encoding="utf-8").replace('id = "s-better"', 'id = "s-questions"'), encoding="utf-8")
    assert build.check(build.Deck(src)) == 1
    out = capsys.readouterr().out
    for needle in ("literal colour", "--nope is used but never defined", "ink.css: missing --principle-5", "duplicate slide id 's-questions'"):
        assert needle in out


def test_unknown_layout_field_is_reported(tmp_path):
    src = copy_src(tmp_path)
    sec = src / "slides" / "opening.toml"
    sec.write_text(sec.read_text(encoding="utf-8").replace('kicker = "Stop', 'kikcer = "x"\nkicker = "Stop', 1), encoding="utf-8")
    with pytest.raises(BuildError, match="kikcer"):
        build.SlideRenderer(build.Deck(src)).render_all()


def test_raw_layout_escape_hatch(tmp_path):
    src = copy_src(tmp_path)
    (src / "slides" / "wrap.toml").open("a", encoding="utf-8").write('\n[[slide]]\nid = "s-raw"\nname = "Raw"\nlayout = "raw"\nhtml = "<p class=\\"sub\\">hi</p>"\n')
    html = build.SlideRenderer(build.Deck(src)).render_all()
    assert '<!-- 53 · Raw -->\n<section class="slide" id="s-raw" data-principle="wrap">\n  <p class="section-label">Wrap</p>\n<p class="sub">hi</p>\n</section>' in html


# ---------- section label and slide number ----------
def sections_html(deck):
    return build.SlideRenderer(deck).render_all()


def test_section_label_from_group_and_principle_default(deck):
    html = sections_html(deck)
    assert html.count('class="section-label"') == 51  # every slide but the title
    assert '<p class="section-label">Intro</p>' in html and "<p class=\"section-label\">Today's demo</p>" in html
    # principle sections have no `group`: "{n} · {name}" from principles.json
    s = next(x for x in deck.slides if x.get("principle") == 3)
    assert s["group"] == "3 · Evidence"
    assert '<p class="section-label">3 · Evidence</p>' in html


def test_group_in_the_section_file_overrides_the_default(tmp_path):
    src = copy_src(tmp_path)
    sec = src / "slides" / "principle-3.toml"
    sec.write_text(sec.read_text(encoding="utf-8").replace("principle = 3\n", 'principle = 3\ngroup = "Receipts"\n'), encoding="utf-8")
    assert '<p class="section-label">Receipts</p>' in sections_html(build.Deck(src))


def test_chrome_false_hides_label_and_number(deck, tmp_path):
    html = sections_html(deck)
    title = html.split("</section>")[0]
    assert 'data-chrome="off"' in title and "section-label" not in title
    assert html.count('data-chrome="off"') == 1
    src = copy_src(tmp_path)
    sec = src / "slides" / "demo.toml"
    sec.write_text(sec.read_text(encoding="utf-8").replace('id = "s-bait"', 'id = "s-bait"\nchrome = false'), encoding="utf-8")
    d2 = build.Deck(src)
    bait = next(x for x in d2.slides if x["id"] == "s-bait")
    out = build.SlideRenderer(d2).render_slide(1, bait)
    assert 'data-chrome="off"' in out and "section-label" not in out


def test_unknown_top_level_keys_are_still_rejected(tmp_path):
    src = copy_src(tmp_path)
    sec = src / "slides" / "demo.toml"
    sec.write_text(sec.read_text(encoding="utf-8").replace('group = ', 'grup = "x"\ngroup = ', 1), encoding="utf-8")
    with pytest.raises(BuildError, match="unknown top-level keys"):
        build.Deck(src)


def test_slide_number_comes_from_the_script_not_the_sources(deck):
    html = build.SlideRenderer(deck).render_all()
    assert 'id="counter"' not in html
    js = (SLIDES / "src" / "js" / "deck.js").read_text(encoding="utf-8")
    assert "counter.textContent = String(idx + 1)" in js


# ---------- visuals kit ----------
BARS = {"viz": "bars", "label": "Fund balance", "step": 1, "data": [["Jan", 10], ["Feb", 20]], "prefix": "$"}


def test_viz_block_renders_a_figure_with_spec_and_hidden_table(deck):
    html = build.viz_markup(BARS, deck, " gap-m")
    assert html.startswith('<figure class="viz viz-bars gap-m" data-viz="bars" data-spec="{&quot;label&quot;:&quot;Fund balance&quot;')
    assert '<table class="viz-sr"><caption>Fund balance</caption>' in html and "<td>$20</td>" in html
    assert "data-lib" not in html
    assert 'data-lib="rough"' in build.viz_markup({**BARS, "style": "rough"}, deck)


def test_count_is_the_number_itself_with_its_step(deck):
    html = build.viz_markup({"viz": "count", "label": "Left", "to": 11400, "prefix": "$", "step": 3}, deck)
    assert html == '<p class="viz viz-count" data-viz="count" data-spec="{&quot;label&quot;:&quot;Left&quot;,&quot;to&quot;:11400,&quot;prefix&quot;:&quot;$&quot;,&quot;step&quot;:3}" data-step="3" title="Left">$11,400</p>'


@pytest.mark.parametrize("block, needle", [
    ({"viz": "pie", "label": "x"}, "unknown viz type 'pie'"),
    ({"viz": "bars", "data": [["a", 1]]}, "needs 'label'"),
    ({**BARS, "highlight": "Mar"}, "not one of the labels"),
    ({**BARS, "highlight": "Jan", "highlight_step": 0}, "highlight_step must be"),
    ({**BARS, "step": 3, "highlight": "Jan", "highlight_step": 2}, "comes before the block's step"),
    ({**BARS, "data": [["a", "lots"]]}, "pairs"),
    ({**BARS, "colour": "red"}, "has no keys ['colour']"),
    ({"viz": "line", "label": "x", "x": ["a", "b"], "series": [{"name": "s", "values": [1]}]}, "one number per x label"),
    ({"viz": "timeline", "label": "x", "events": [{"date": "2026-05-01", "text": "b"}, {"date": "2026-01-01", "text": "a"}]}, "date order"),
    ({"viz": "flow", "label": "x", "nodes": ["a", {"text": "b", "principle": 9}]}, "principle 9"),
    ({"viz": "flow", "label": "x", "nodes": ["a", {"text": "b", "step": 3}], "travel": 2}, "travel comes before"),
    ({"viz": "echarts", "label": "x", "option": "{not json"}, "not valid JSON"),
])
def test_viz_validation(deck, block, needle):
    with pytest.raises(BuildError, match=re.escape(needle)):
        build.viz_markup(block, deck)


def test_marks_and_choreo_overlays(deck):
    out = build.overlays({"marks": [{"target": ".sub", "kind": "circle", "step": 2, "style": "rough"}],
                          "choreo": [{"step": 1, "targets": ".pill", "to": {"opacity": 1}}]}, deck)
    assert '<svg class="viz-marks" data-viz="mark" data-lib="rough"' in out
    assert '<i class="viz-choreo" data-viz="choreo" data-lib="anime"' in out and 'data-step="1" hidden></i>' in out
    with pytest.raises(BuildError, match="kind is circle"):
        build.overlays({"marks": [{"target": ".x", "kind": "zigzag"}]}, deck)
    with pytest.raises(BuildError, match="needs 'step'"):
        build.overlays({"choreo": [{"targets": ".x"}]}, deck)


def test_kit_and_libraries_only_when_used(deck, tmp_path):
    plain = build.build(deck, "blueprint", False)
    assert "var viz = (function" not in plain and "--viz-series-1" not in plain and "vendor:" not in plain
    src = copy_src(tmp_path)
    sec = src / "slides" / "wrap.toml"
    sec.write_text(sec.read_text(encoding="utf-8") + '\n[[slide]]\nid = "s-chart"\nname = "Chart"\nlayout = "statement"\n'
                   'blocks = [ { viz = "bars", style = "rough", label = "A chart", data = [["a", 1], ["b", 2]] } ]\n', encoding="utf-8")
    html = build.build(build.Deck(src), "blueprint", False)
    assert "var viz = (function" in html and "--viz-series-1" in html and ".viz-svg" in html
    assert "vendor: roughjs 4.6.6" in html and "anime" not in html.lower().split("<script>")[1][:200]
    assert "echarts" not in html.split("<script>")[1].split("(function () {")[0]
    assert html.count("<script>") == 1 and html.count("<style>") == 1
    assert html.index("var rough=") < html.index("(function () {")  # vendor code sits before the deck's own script


def test_figure_layout_takes_a_viz(tmp_path):
    src = copy_src(tmp_path)
    sec = src / "slides" / "about-us.toml"
    sec.open("a", encoding="utf-8").write('\n[[slide]]\nid = "s-path"\nlayout = "figure"\nlabel = "HOW"\nfigure = { viz = "draw", svg = "sketch.svg", label = "The path" }\n')
    deck = build.Deck(src)
    html = build.SlideRenderer(deck).render_slide(5, deck.slides[-1] if False else next(x for x in deck.slides if x["id"] == "s-path"))
    assert '<figure class="viz viz-draw" data-viz="draw"' in html and '<svg class="sketch gap-s"' in html


def test_hand_written_figure_in_raw_is_checked(tmp_path, capsys):
    src = copy_src(tmp_path)
    (src / "slides" / "wrap.toml").open("a", encoding="utf-8").write(
        '\n[[slide]]\nid = "s-raw-viz"\nname = "Raw viz"\nlayout = "raw"\nhtml = \'<figure class="viz" data-viz="sparkle"></figure>\'\n')
    assert build.check(build.Deck(src)) == 1
    assert "unknown viz type 'sparkle'" in capsys.readouterr().out


def test_gallery_builds_with_every_library_and_the_theme_name():
    g = build.Deck(gallery=True)
    for theme in g.themes:
        frag = build.build(g, theme, False)
        assert frag.startswith(f"<title>Design system gallery · {theme}</title>")
        assert frag.count("<script>") == frag.count("<style>") == 1 and "<!doctype" not in frag.lower()
        assert f"Theme: <span class=\"trust\">{theme}</span>" in frag
        for lib in ("roughjs 4.6.6", "animejs 4.5.0", "echarts 6.1.0"):
            assert f"vendor: {lib}" in frag
        for kind in build.VIZ_TYPES:
            assert f'data-viz="{kind}"' in frag, kind
        assert 'data-viz="mark"' in frag and 'data-viz="choreo"' in frag


def test_viz_tokens_are_stripped_but_kept_in_tokens_css(deck):
    assert build.VIZ_TOKENS_MARK in (SLIDES / "src" / "styles" / "tokens.css").read_text(encoding="utf-8")
    assert build.VIZ_TOKENS_MARK not in build.tokens_css(deck, False)
    assert "--viz-bar-radius" in build.tokens_css(deck, True)
