"""The palette in a real browser: with palette = "primary" the deck shows its theme's primary
palette whatever the OS or a hosting page's data-theme says, and D shows the alternate.

Needs Playwright and Chromium (like tools/shoot.py); skipped where they are not installed.
"""
import sys
from pathlib import Path

import pytest

SLIDES = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SLIDES))
sys.path.insert(0, str(SLIDES / "tools"))
sync_api = pytest.importorskip("playwright.sync_api")
import build  # noqa: E402
import shoot  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as pw:
        try:
            b = shoot.launch(pw)
        except Exception as e:  # no Chromium
            pytest.skip(f"no browser: {e}")
        yield b
        b.close()


@pytest.mark.parametrize("theme", ["nord", "blueprint"])
def test_primary_palette_ignores_os_and_host_and_d_toggles(browser, theme, tmp_path):
    deck = build.Deck()
    assert deck.meta.get("palette", "primary") == "primary"
    page = tmp_path / "deck.html"
    page.write_text(build.build(deck, theme, True), encoding="utf-8")
    url = shoot.test_page(page, tmp_path, None).as_uri()
    assert shoot.palette_problems(browser, url) == []


def test_looks_page_uses_the_same_mechanism(browser, tmp_path):
    deck = build.Deck()
    page = tmp_path / "looks.html"
    page.write_text(build.build(deck, "nord", True, ["nord", "catppuccin"]), encoding="utf-8")
    url = shoot.test_page(page, tmp_path, None).as_uri()
    pg = shoot.new_page(browser, scheme="dark")
    pg.goto(url + "#1")
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    shown = "getComputedStyle(document.documentElement).getPropertyValue('--palette-shown').trim()"
    assert pg.evaluate(shown) == "primary"
    pg.click('.looks-bar [data-mode-btn]')
    assert pg.evaluate(shown) == "alternate" and pg.inner_text('.looks-bar [data-mode-btn]') == "Alternate"
    pg.click('.looks-bar [data-look-btn="catppuccin"]')
    assert pg.evaluate(shown) == "alternate"  # the palette choice carries across looks
    pg.keyboard.press("d")
    assert pg.evaluate(shown) == "primary"
    pg.context.close()


def test_system_palette_follows_the_viewer_and_a_host_attribute(browser, tmp_path):
    deck = build.Deck()
    deck.meta["palette"] = "system"   # nord: primary is dark, alternate light
    page = tmp_path / "system.html"
    page.write_text(build.build(deck, "nord", True), encoding="utf-8")
    url = shoot.test_page(page, tmp_path, None).as_uri()
    shown = "getComputedStyle(document.documentElement).getPropertyValue('--palette-shown').trim()"
    for scheme, host, want in (("dark", None, "primary"), ("light", None, "alternate"),
                               ("light", "dark", "primary"), ("dark", "light", "alternate")):
        pg = shoot.new_page(browser, scheme=scheme)
        pg.goto(url + "#1")
        if host:
            pg.evaluate(f"document.documentElement.setAttribute('data-theme', '{host}')")
        assert pg.evaluate(shown) == want, (scheme, host)
        pg.keyboard.press("d")
        assert pg.evaluate(shown) == ("alternate" if want == "primary" else "primary")
        pg.context.close()
