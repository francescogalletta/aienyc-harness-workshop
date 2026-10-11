"""Screenshots and a scripted check of a built deck. Optional: needs Playwright + Chromium.

Not needed to build the deck. Used to compare a build against a baseline and to
look at themes.

    python tools/shoot.py shots  DECK.html OUTDIR [--set regress|review] [--slides 1,7,20]
    python tools/shoot.py check  DECK.html [--csp]
    python tools/shoot.py shots  GALLERY.html OUTDIR --set all [--dark]
    python tools/shoot.py frames DECK.html OUTDIR --at 20:1,24:2 [--delays 150,450,900]
    python tools/shoot.py compare BEFORE_DIR AFTER_DIR [--threshold 0.05]

Fonts: Google Fonts may be unreachable (sandboxes, trains). Pass --font-dir (or set
DECK_FONT_DIR) to a folder holding the woff2 files listed in tools/fonts.json; they
are injected with @font-face into a test copy of the page, and requests to Google
Fonts are blocked so every run renders the same.

Shots are taken with reduced motion emulated, so the confetti never fires and the
handwritten-aside pop shows its end state: the images are deterministic.
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Representative slides for looking at a theme (by id, so they survive reordering).
REVIEW = ["s-title", "s-francesco", "s-monzo", "s-trust", "s-evolution", "s-stakes", "s-gap", "s-deal",
          "s-not-new", "s-framework", "s-ask", "s-hands", "s-tracks", "s-setup", "s-repo", "s-map", "s-check",
          "s-p1", "s-p2-examples", "s-p3-receipts", "s-p4-ambiguity", "s-p5-thin", "s-takeaways", "s-questions"]
IDS_JS = "Array.from(document.querySelectorAll('#stage > .slide')).map(s => s.id)"
ALT_JS = "document.documentElement.setAttribute('data-palette', 'alternate')"

STEPS_JS = """() => Array.from(document.querySelectorAll('#stage > .slide')).map(s => {
  let m = 0;
  ['data-step','data-step-out','data-step-fill','data-step-strike','data-step-mute'].forEach(a =>
    s.querySelectorAll('[' + a + ']').forEach(e => { m = Math.max(m, +e.getAttribute(a) || 0); }));
  const r = s.querySelector('.emoji-reel'); if (r) m = Math.max(m, r.children.length + 1);
  return m; })"""

BOUNDS_JS = """() => {
  const s = document.querySelector('.slide.active'), st = document.getElementById('stage').getBoundingClientRect();
  const k = st.width / 1920, out = [];
  const name = e => e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().replace(/\\s+/g, '.') : '');
  const els = [s, ...s.querySelectorAll('*'), ...document.querySelectorAll('.rail, .rail *')];
  els.forEach(e => {
    const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility !== 'visible') return;
    const r = e.getBoundingClientRect(); if (!r.width && !r.height) return;
    const x0 = (r.left - st.left) / k, y0 = (r.top - st.top) / k, x1 = (r.right - st.left) / k, y1 = (r.bottom - st.top) / k;
    if (x0 < -1 || y0 < -1 || x1 > 1921 || y1 > 1081) out.push('OUT ' + name(e) + ' ' + [x0, y0, x1, y1].map(Math.round).join(','));
    if (e.matches('.step,.pill,.chip,.bar,.doubt,.cell,.rail-cell,.panel')) {
      const range = document.createRange(); range.selectNodeContents(e); const t = range.getBoundingClientRect();
      if (t.width && (t.right > r.right + 1 || t.left < r.left - 1 || t.bottom > r.bottom + 2 || t.top < r.top - 2)) out.push('TEXT-OVER ' + name(e) + ' "' + e.textContent.trim().slice(0, 30) + '"');
    }
  });
  return out; }"""


# The hosting page's policy, near enough: inline scripts only, no eval, no network for data or workers.
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com data:; img-src data:; connect-src 'none'; worker-src 'none'; base-uri 'none'")
CSP_LISTEN = ("window.__csp = []; document.addEventListener('securitypolicyviolation', function (e) {"
              " window.__csp.push(e.violatedDirective + ' <- ' + (e.blockedURI || e.sample || '')); });")


def font_css(font_dir: str | None) -> str:
    if not font_dir:
        return ""
    manifest = json.loads((HERE / "fonts.json").read_text())
    rules = []
    for family, weights in manifest.items():
        if family.startswith("_"):
            continue
        for weight, rel in weights.items():
            path = Path(font_dir) / rel
            if path.exists():
                data = base64.b64encode(path.read_bytes()).decode()
                rules.append(f'@font-face{{font-family:"{family}";font-weight:{weight};src:url(data:font/woff2;base64,{data}) format("woff2")}}')
            else:
                print(f"note: missing local font {path}", file=sys.stderr)
    return "<style>\n" + "\n".join(rules) + "\n</style>"


def test_page(deck: Path, outdir: Path, font_dir: str | None, csp: bool = False) -> Path:
    """Write a copy of the deck with local fonts injected (and the host CSP). Works for standalone and fragment builds."""
    html = deck.read_text(encoding="utf-8")
    fonts = font_css(font_dir)
    if csp:
        fonts = f'<meta http-equiv="Content-Security-Policy" content="{CSP}"><script>{CSP_LISTEN}</script>' + fonts
    if re.search(r"<head[^>]*>", html):
        html = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + fonts, html, count=1)
    else:  # fragment: wrap it the way the hosting page does
        html = ('<!doctype html><html><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                + fonts + "</head><body>" + html + "</body></html>")
    outdir.mkdir(parents=True, exist_ok=True)
    p = (outdir / "_test.html").resolve()
    p.write_text(html, encoding="utf-8")
    return p


def launch(pw):
    exe = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    kw = {"executable_path": exe[-1]} if exe else {}
    return pw.chromium.launch(**kw)


def new_page(browser, width=1920, height=1080, scheme="light", motion="reduce", **kw):
    ctx = browser.new_context(viewport={"width": width, "height": height}, reduced_motion=motion,
                              color_scheme=scheme, **kw)
    ctx.route(re.compile(r"https://fonts\.(googleapis|gstatic)\.com/.*"), lambda r: r.abort())
    page = ctx.new_page()
    page.errors = []
    def on_console(m):
        if m.type in ("error", "warning") and "fonts.g" not in (m.location or {}).get("url", ""):
            page.errors.append(f"console.{m.type}: {m.text}")
    page.on("console", on_console)
    page.on("pageerror", lambda e: page.errors.append(f"pageerror: {e}"))
    page.on("requestfailed", lambda r: None if "fonts.g" in r.url else page.errors.append(f"request failed: {r.url[:90]}"))
    return page


def open_at(page, url: str, n: int):
    page.goto(f"{url}#{n}")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(60)


def forward(page, k: int):
    for _ in range(k):
        page.keyboard.press("ArrowRight")
    if k:
        page.wait_for_timeout(40)


def cmd_shots(a):
    from playwright.sync_api import sync_playwright
    outdir = Path(a.outdir).resolve()
    url = test_page(Path(a.deck), outdir, a.font_dir, a.csp).as_uri()
    with sync_playwright() as pw:
        b = launch(pw)
        page = new_page(b)
        page.goto(url)
        page.evaluate("document.fonts.ready")
        if a.look:
            page.evaluate(f"document.documentElement.setAttribute('data-look', '{a.look}')")
        if a.alt:
            page.evaluate(ALT_JS)
        page.wait_for_timeout(100)
        steps = page.evaluate(STEPS_JS)
        ids = page.evaluate(IDS_JS)
        wanted = [int(x) for x in a.slides.split(",")] if a.slides else None
        count = 0
        if a.set == "all":   # every slide at its final step
            for n in (wanted or range(1, len(steps) + 1)):
                open_at(page, url, n)
                forward(page, steps[n - 1])
                page.screenshot(path=str(outdir / f"{a.prefix}{n:02d}.png")); count += 1
        elif a.set == "review":   # the representative slides, final step
            for n in (wanted or [ids.index(i) + 1 for i in REVIEW if i in ids]):
                open_at(page, url, n)
                forward(page, steps[n - 1])
                page.screenshot(path=str(outdir / f"{a.prefix}{n:02d}-{ids[n - 1]}.png")); count += 1
        else:   # regression: every step of every slide
            for n in (wanted or range(1, len(steps) + 1)):
                open_at(page, url, n)
                for k in range(steps[n - 1] + 1):
                    if k:
                        forward(page, 1)
                    page.screenshot(path=str(outdir / f"{a.prefix}{n:02d}-s{k}.png")); count += 1
        if a.dark and not a.alt:   # the alternate palette too (the D key), final steps
            for n in (wanted or ([ids.index(i) + 1 for i in REVIEW if i in ids] if a.set != "all" else range(1, len(steps) + 1))):
                open_at(page, url, n)
                page.evaluate(ALT_JS)
                forward(page, steps[n - 1])
                page.screenshot(path=str(outdir / f"alt-{n:02d}.png")); count += 1
                page.evaluate("document.documentElement.removeAttribute('data-palette')")
        errs = page.errors
        b.close()
    print(f"{count} shots in {outdir}; slides={len(steps)} steps={steps}")
    if errs:
        print("console:", *errs, sep="\n  ")


PALETTE_JS = "[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.documentElement).getPropertyValue('--palette-shown').trim()]"


def palette_problems(browser, url: str) -> list[str]:
    """With palette = "primary" (the default), the deck shows its primary palette whatever the OS
    or a hosting page's data-theme says; D shows the alternate and D again comes back."""
    problems, seen = [], {}
    for scheme in ("light", "dark"):
        pg = new_page(browser, scheme=scheme)
        pg.goto(url + "#1"); pg.evaluate("document.fonts.ready")
        seen[f"OS {scheme}"] = pg.evaluate(PALETTE_JS)
        for host in ("dark", "light"):
            pg.evaluate(f"document.documentElement.setAttribute('data-theme', '{host}')")
            seen[f"OS {scheme}, host data-theme={host}"] = pg.evaluate(PALETTE_JS)
        pg.evaluate("document.documentElement.removeAttribute('data-theme')")
        if scheme == "dark":
            pg.keyboard.press("d")
            after_d = pg.evaluate(PALETTE_JS)
            pg.keyboard.press("d")
            back = pg.evaluate(PALETTE_JS)
        pg.context.close()
    first = seen["OS light"]
    for k, v in seen.items():
        if v != first:
            problems.append(f"palette: {k} shows {v}, not {first}")
    if first[1] != "primary":
        problems.append(f"palette: opens on {first[1]!r}, not the primary palette")
    if after_d[1] != "alternate" or after_d[0] == first[0]:
        problems.append(f"palette: D did not show the alternate ({after_d})")
    if back != first:
        problems.append(f"palette: D twice did not come back to the primary ({back})")
    return problems


def cmd_check(a):
    """Step through everything and back; report console errors, hash, bounds, mobile scroll."""
    from playwright.sync_api import sync_playwright
    outdir = Path(a.outdir or (HERE.parent / "dist" / "check")).resolve()
    url = test_page(Path(a.deck), outdir, a.font_dir, a.csp).as_uri()
    problems = []
    with sync_playwright() as pw:
        b = launch(pw)
        page = new_page(b)
        page.goto(url)
        page.evaluate("document.fonts.ready")
        steps = page.evaluate(STEPS_JS)
        n_slides = len(steps)
        looks = page.evaluate("Array.from(document.querySelectorAll('.looks-bar [data-look-btn]')).map(function (b) { return b.getAttribute('data-look-btn'); })")
        if looks and page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--palette-shown').trim()") != "primary":
            problems.append("looks build did not open on the primary palette")
        walks = [(look, pal) for look in looks for pal in ("primary", "alternate")] if looks else [(None, None)]
        for look, pal in walks:
            tag = f"[{look} {pal}] " if look else ""
            if pal == "alternate":  # same look, other palette, through the real key
                page.keyboard.press("d")
                if page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--palette-shown').trim()") != "alternate":
                    problems.append(f"{tag}D did not switch to the alternate palette")
            if look and pal == "primary":
                # switching keeps slide and step, and the button does not move the deck
                open_at(page, url, 28)
                forward(page, 3)
                before = page.evaluate("[location.hash, document.querySelectorAll('.slide.active .shown, .slide.active .filled').length]")
                page.click(f'.looks-bar [data-look-btn="{look}"]')
                page.keyboard.press(" ")  # a focused button must not take Space as "next" (it was blurred anyway)
                page.keyboard.press("ArrowLeft")
                after = page.evaluate("[location.hash, document.querySelectorAll('.slide.active .shown, .slide.active .filled').length, document.documentElement.getAttribute('data-look')]")
                if after[0] != before[0] or after[2] != look:
                    problems.append(f"{tag}switching look moved the deck or failed: {before} -> {after}")
                page.keyboard.press("Home")
            for i, total in enumerate(steps):
                for k in range(total + 1):
                    h = page.evaluate("location.hash")
                    if h != f"#{i + 1}":
                        problems.append(f"{tag}slide {i + 1} step {k}: hash {h}")
                    for issue in page.evaluate(BOUNDS_JS):
                        problems.append(f"{tag}slide {i + 1} step {k}: {issue}")
                    if not (i == n_slides - 1 and k == total):
                        page.keyboard.press("ArrowRight")
            page.keyboard.press("ArrowRight")  # past the end: must stay put
            end = page.evaluate("[location.hash, document.querySelectorAll('.slide.active').length]")
            if end != [f"#{n_slides}", 1]:
                problems.append(f"{tag}past the end: {end}")
            for _ in range(sum(steps) + n_slides + 2):
                page.keyboard.press("ArrowLeft")
                for issue in page.evaluate(BOUNDS_JS):
                    problems.append(f"{tag}going back, {page.evaluate('location.hash')}: {issue}")
            back = page.evaluate("[location.hash, document.querySelector('.slide.active').id, document.querySelectorAll('.slide.active .shown, .slide.active .gone, .slide.active .filled, .slide.active .struck').length]")
            if back[0] != "#1" or back[2] != 0:
                problems.append(f"{tag}back to start: {back}")
            if pal == "alternate":
                page.keyboard.press("d")
                if page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--palette-shown').trim()") != "primary":
                    problems.append(f"{tag}D did not switch back to the primary palette")
        if looks:
            page.keyboard.press("t")
            if page.evaluate("document.documentElement.getAttribute('data-look')") != looks[0]:
                problems.append("T did not cycle back to the first look")
            page.keyboard.press("Shift+T")
            if page.evaluate("document.documentElement.getAttribute('data-look')") != looks[-1]:
                problems.append("Shift+T did not go back a look")
        open_at(page, url, 18)
        if page.evaluate("document.querySelector('.slide.active').id") != page.evaluate("document.querySelectorAll('#stage > .slide')[17].id"):
            problems.append("loading #18 did not open slide 18")
        page.keyboard.press("d")
        if page.evaluate("document.documentElement.getAttribute('data-palette')") != "alternate":
            problems.append("D did not switch to the alternate palette")
        problems += page.errors
        if a.csp:
            problems += [f"CSP: {v}" for v in page.evaluate("window.__csp || []")]
        if not looks:
            problems += palette_problems(b, url)
        mobile = new_page(b, width=400, height=800, device_scale_factor=2, has_touch=True)
        for n in range(1, n_slides + 1):
            open_at(mobile, url, n)
            forward(mobile, steps[n - 1])
            sw, cw = mobile.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            if sw > cw:
                problems.append(f"400px viewport, slide {n}: horizontal scroll {sw}>{cw}")
        problems += mobile.errors
        b.close()
    print(f"checked {n_slides} slides, {sum(steps)} steps" + (f", in {len(looks)} looks x 2 palettes" if looks else ""))
    for p in problems:
        print("PROBLEM", p)
    print("ok" if not problems else f"{len(problems)} problems")
    sys.exit(1 if problems else 0)


def cmd_frames(a):
    """Mid-animation frames: open slide n at step k-1, click once, shoot at each delay (motion allowed)."""
    from playwright.sync_api import sync_playwright
    outdir = Path(a.outdir).resolve()
    url = test_page(Path(a.deck), outdir, a.font_dir).as_uri()
    with sync_playwright() as pw:
        b = launch(pw)
        page = new_page(b, motion="no-preference")
        for item in a.at.split(","):
            n, k = (int(x) for x in item.split(":"))
            open_at(page, url, n)
            for _ in range(k - 1):
                page.keyboard.press("ArrowRight")
            page.wait_for_timeout(400)
            page.keyboard.press("ArrowRight")
            t = 0
            for d in [int(x) for x in a.delays.split(",")]:
                page.wait_for_timeout(d - t); t = d
                # freeze CSS transitions and Web Animations while the (slow) screenshot is taken
                page.evaluate("document.getAnimations().forEach(function (x) { x.pause(); })")
                page.screenshot(path=str(outdir / f"{n:02d}-s{k}-{d}ms.png"))
                page.evaluate("document.getAnimations().forEach(function (x) { x.play(); })")
        print("frames:", page.errors or "no console errors")
        b.close()


def cmd_compare(a):
    """ImageMagick compare -metric AE -fuzz 2% on every shot present in both folders."""
    before, after = Path(a.before), Path(a.after)
    names = sorted(p.name for p in before.glob("*.png"))
    worse, missing = [], []
    for name in names:
        other = after / name
        if not other.exists():
            missing.append(name); continue
        r = subprocess.run(["compare", "-metric", "AE", "-fuzz", "2%", str(before / name), str(other), "null:"],
                           capture_output=True, text=True)
        px = float((r.stderr.strip().split() or ["0"])[0] or 0)
        pct = px / (1920 * 1080) * 100
        if pct > a.threshold:
            worse.append((name, int(px), pct))
            if a.diffs:
                Path(a.diffs).mkdir(parents=True, exist_ok=True)
                subprocess.run(["compare", "-fuzz", "2%", str(before / name), str(other), str(Path(a.diffs) / name)],
                               capture_output=True)
        elif px and a.verbose:
            print(f"  {name}: {int(px)} px ({pct:.4f}%)")
    extra = sorted(set(p.name for p in after.glob("*.png")) - set(names))
    print(f"compared {len(names) - len(missing)} shots; over {a.threshold}%: {len(worse)}; missing: {len(missing)}; extra: {len(extra)}")
    for name, px, pct in worse:
        print(f"  DIFF {name}: {px} px ({pct:.3f}%)")
    for name in missing:
        print(f"  MISSING {name}")
    sys.exit(1 if worse or missing else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shots"); s.add_argument("deck"); s.add_argument("outdir")
    s.add_argument("--set", choices=["regress", "review", "all"], default="regress"); s.add_argument("--slides")
    s.add_argument("--dark", action="store_true", help="the alternate palette too (alt-NN.png)")
    s.add_argument("--look", help="in a looks build: switch to this look first")
    s.add_argument("--alt", action="store_true", help="switch to the alternate palette (data-palette=alternate) first")
    s.add_argument("--prefix", default="", help="prefix for file names")
    c = sub.add_parser("check"); c.add_argument("deck"); c.add_argument("--outdir")
    f = sub.add_parser("frames"); f.add_argument("deck"); f.add_argument("outdir")
    f.add_argument("--at", required=True, help="slide:step pairs, e.g. 20:1,24:2")
    f.add_argument("--delays", default="150,450,900", help="ms after the click")
    for p in (s, c, f):
        p.add_argument("--font-dir", default=os.environ.get("DECK_FONT_DIR"))
    for p in (s, c):
        p.add_argument("--csp", action="store_true", help="add the hosting page's Content-Security-Policy")
    m = sub.add_parser("compare"); m.add_argument("before"); m.add_argument("after")
    m.add_argument("--threshold", type=float, default=0.05); m.add_argument("--diffs"); m.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    {"shots": cmd_shots, "check": cmd_check, "compare": cmd_compare, "frames": cmd_frames}[a.cmd](a)


if __name__ == "__main__":
    main()
