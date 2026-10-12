"""B2: the real page is served with the token and loads nothing from outside; the sample plan state
documents have the shape ARCHITECTURE.md section 3 states; the state and the actions round trip
through the real server."""
import json
import re
from pathlib import Path

import pytest

from harness.ui.server import PAGE, TOKEN_PLACEHOLDER
from layer0_helpers import SETTLE
from state_shape import problems
from test_server import serve        # noqa: F401  (the fixture)

STATES = Path(__file__).parent / "states"
SAMPLES = sorted(STATES.glob("*.json"))
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def test_the_real_page_is_served_with_the_token_in_place(serve):                # noqa: F811
    request = serve(page_path=PAGE)
    response, text = request("GET", "/", token=False)
    assert response.status == 200 and response.getheader("Content-Type").startswith("text/html")
    assert request.server.token in text and TOKEN_PLACEHOLDER not in text
    assert "<title>" in text and "page is not built yet" not in text           # not the placeholder


def test_the_page_loads_nothing_from_outside():
    page = PAGE.read_text(encoding="utf-8")
    assert [url for url in re.findall(r"https?://[^\s\"'<>)]+", page) if url != SVG_NAMESPACE] == []
    assert re.findall(r"<(?:script|img|iframe|link|source|video|audio|embed|object)\b[^>]*\b(?:src|href|data)\s*=",
                      page, re.IGNORECASE) == []
    assert not re.search(r"@import|url\(\s*[\"']?(?!data:|#)|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts",
                         page)
    assert TOKEN_PLACEHOLDER in page and page.count(TOKEN_PLACEHOLDER) == 1
    assert re.findall(r"fetch\(([^,)]*)", page) == ["path"]                       # every request goes through api()
    assert set(re.findall(r"['\"](/[a-z/]*api/[a-z]+)['\"]", page)) == {"/api/state", "/api/act"}


def test_there_are_six_sample_states_and_the_decision_graph_stories():
    stories = [path.stem for path in SAMPLES if path.stem.startswith("dg_story_")]       # B3's mock, the two stories of 12.10
    assert [path.stem for path in SAMPLES if path.stem not in stories] == [
        "answer_with_mark", "built_one_not_built", "call_waiting", "decision_graph", "plan_proposed", "review_challenges"]
    assert {"dg_story_proposal", "dg_story_joined", "dg_story_dead"} <= set(stories)


@pytest.mark.parametrize("path", SAMPLES, ids=lambda path: path.stem)
def test_each_sample_state_has_the_documented_shape(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    assert problems(state) == []


def test_the_validator_notices_a_wrong_document():
    state = json.loads((STATES / "review_challenges.json").read_text(encoding="utf-8"))
    state["threads"][0]["after"] = "m999"
    state["chat"][-1]["figures"] = [{"start": 0, "end": 3, "text": "zzz", "step": None, "run": None, "input": None}]
    found = problems(state)
    assert any("not in the chat" in line for line in found)
    assert any("offsets" in line for line in found)
    state["activity"] = [{"lane": "side", "what": "side", "step": None, "text": "x", "since": "t"}]
    assert any("activity[0]: missing thread" in line for line in problems(state))


def test_the_state_and_an_action_round_trip_through_the_real_server(serve):     # noqa: F811
    request = serve(page_path=PAGE)
    before = json.loads(request("GET", "/api/state")[1])
    assert problems(before) == [] and before["chat"] == []
    response, text = request("POST", "/api/act", {"action": "say", "text": "hello there"})
    assert response.status == 200 and json.loads(text)["ok"] is True
    request.session.settle(SETTLE)
    after = json.loads(request("GET", "/api/state")[1])
    assert after["version"] > before["version"] and problems(after) == []
    assert [(m["who"], m["text"]) for m in after["chat"]][0] == ("you", "hello there")


# --- Colour is the principle (design/ui-design-decisions.md): the tokens, the legend, the built page ---

DESIGN = Path(__file__).resolve().parents[2] / "design"
PRINCIPLES = [("Shared Domain", "Agree the plan before any number."),
              ("Consistency", "Numbers come only from tested code."),
              ("Evidence", "Every number can be followed back."),
              ("Accountability", "Ask only where a person must decide."),
              ("Verification", "A reviewer challenges the plan.")]


def _theme_blocks(css: str) -> dict:
    light = re.search(r':root, \[data-theme="light"\] \{(.*?)\n\}', css, re.S).group(1)
    dark = re.search(r'\[data-theme="dark"\] \{(.*?)\n\}', css, re.S).group(1)
    return {theme: dict(re.findall(r"--([\w-]+):\s*([^;]+);", block)) for theme, block in (("light", light), ("dark", dark))}


def _contrast(a: str, b: str) -> float:
    def lum(hex_colour):
        channels = [int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    high, low = sorted([lum(a), lum(b)], reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_the_built_page_is_its_sources():
    src = (DESIGN / "page" / "page_src.html").read_text(encoding="utf-8")
    for marker, path in [("/*@@TOKENS@@*/", DESIGN / "system" / "tokens.css"), ("/*@@BUNDLE_CSS@@*/", DESIGN / "system" / "bundle.css"),
                         ("/*@@BUNDLE_JS@@*/", DESIGN / "system" / "bundle.js"), ("/*@@APP_JS@@*/", DESIGN / "page" / "app.js")]:
        src = src.replace(marker, path.read_text(encoding="utf-8").rstrip("\n"))
    assert PAGE.read_text(encoding="utf-8") == src, "run python design/page/build_page.py"


def test_tokens_css_says_what_tokens_json_says_in_both_themes():
    tokens = json.loads((DESIGN / "system" / "tokens.json").read_text(encoding="utf-8"))
    css = _theme_blocks((DESIGN / "system" / "tokens.css").read_text(encoding="utf-8"))
    for token in tokens["color"]["tokens"]:
        for theme in ("light", "dark"):
            assert css[theme].get(token["name"]) == token["value"][theme], (token["name"], theme)


def test_every_principle_has_a_fill_and_an_ink_that_reads_in_both_themes():
    css = _theme_blocks((DESIGN / "system" / "tokens.css").read_text(encoding="utf-8"))
    for theme, colours in css.items():
        for n in range(1, 6):
            assert re.fullmatch(r"#[0-9a-f]{6}", colours[f"principle-{n}"])
            for ground in ("surface", "ground"):
                assert _contrast(colours[f"principle-{n}-ink"], colours[ground]) >= 4.5, (n, theme, ground)
            on = colours["on-principle-3" if n == 3 else "on-principle"]
            assert _contrast(on, colours[f"principle-{n}"]) >= 4.5, (n, theme, "text on the fill")


def test_the_legend_names_the_five_principles_and_each_one_colours_something():
    page = PAGE.read_text(encoding="utf-8")
    legend = re.search(r'<nav class="fa-legend".*?</nav>', page, re.S).group(0)
    keys = re.findall(r'<button class="fa-key" type="button" data-p="(\d)" aria-pressed="false" title="([^"]+)">', legend)
    assert [n for n, _ in keys] == ["1", "2", "3", "4", "5"]
    for (n, title), (name, statement) in zip(keys, PRINCIPLES):
        assert title == f"{name}: {statement}"
        assert f"<span>{name}</span>" in legend and f": {statement}</span>" in legend        # read out, not only a tooltip
        assert f'[data-p="{n}"] {{ --p: var(--principle-{n}); --p-ink: var(--principle-{n}-ink);' in page
