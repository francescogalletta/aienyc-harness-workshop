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

# Slides whose every intermediate step is shot in the regression set.
STEPPED = [2, 3, 4, 7, 9, 12, 13, 15, 18, 22, 24, 28, 32]
# Final states shot in dark: (slide, how). "media" emulates prefers-color-scheme,
# "attr" sets data-theme="dark" (the D key), so both dark blocks are exercised.
DARK = [(2, "media"), (3, "media"), (7, "attr"), (13, "media"), (19, "media"), (20, "media"),
        (24, "media"), (28, "attr"), (32, "media"), (35, "media"), (53, "media"), (55, "media")]
# Representative slides for looking at a theme.
REVIEW = [1, 3, 7, 18, 19, 20, 28, 32, 35, 33, 34, 53, 55]

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
        steps = page.evaluate(STEPS_JS)
        wanted = [int(x) for x in a.slides.split(",")] if a.slides else None
        count = 0
        if a.set == "all":
            for n in (wanted or range(1, len(steps) + 1)):
                open_at(page, url, n)
                forward(page, steps[n - 1])
                page.screenshot(path=str(outdir / f"{n:02d}.png")); count += 1
            if a.dark:
                dark = new_page(b, scheme="dark")
                for n in (wanted or range(1, len(steps) + 1)):
                    open_at(dark, url, n)
                    forward(dark, steps[n - 1])
                    dark.screenshot(path=str(outdir / f"dark-{n:02d}.png")); count += 1
        elif a.set == "review":
            for n in (wanted or REVIEW):
                open_at(page, url, n)
                forward(page, steps[n - 1])
                page.screenshot(path=str(outdir / f"{n:02d}.png")); count += 1
            dark = new_page(b, scheme="dark")
            for n in (wanted or REVIEW)[:6]:
                open_at(dark, url, n)
                forward(dark, steps[n - 1])
                dark.screenshot(path=str(outdir / f"dark-{n:02d}.png")); count += 1
        else:
            for n in (wanted or range(1, len(steps) + 1)):
                total = steps[n - 1]
                keep = set(range(total + 1)) if n in STEPPED else {0, total}
                open_at(page, url, n)
                for k in range(total + 1):
                    if k:
                        forward(page, 1)
                    if k in keep:
                        page.screenshot(path=str(outdir / f"{n:02d}-s{k}.png")); count += 1
            if not wanted:
                dark = new_page(b, scheme="dark")
                for n, how in DARK:
                    pg = dark if how == "media" else page
                    open_at(pg, url, n)
                    if how == "attr":
                        pg.evaluate("document.documentElement.setAttribute('data-theme','dark')")
                    forward(pg, steps[n - 1])
                    pg.screenshot(path=str(outdir / f"dark-{n:02d}.png")); count += 1
                    if how == "attr":
                        pg.evaluate("document.documentElement.removeAttribute('data-theme')")
        errs = page.errors
        b.close()
    print(f"{count} shots in {outdir}; slides={len(steps)} steps={steps}")
    if errs:
        print("console:", *errs, sep="\n  ")


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
        for i, total in enumerate(steps):
            for k in range(total + 1):
                h = page.evaluate("location.hash")
                if h != f"#{i + 1}":
                    problems.append(f"slide {i + 1} step {k}: hash {h}")
                for issue in page.evaluate(BOUNDS_JS):
                    problems.append(f"slide {i + 1} step {k}: {issue}")
                if not (i == n_slides - 1 and k == total):
                    page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")  # past the end: must stay put
        end = page.evaluate("[location.hash, document.querySelectorAll('.slide.active').length]")
        if end != [f"#{n_slides}", 1]:
            problems.append(f"past the end: {end}")
        for _ in range(sum(steps) + n_slides + 2):
            page.keyboard.press("ArrowLeft")
            for issue in page.evaluate(BOUNDS_JS):
                problems.append(f"going back, {page.evaluate('location.hash')}: {issue}")
        back = page.evaluate("[location.hash, document.querySelector('.slide.active').id, document.querySelectorAll('.slide.active .shown, .slide.active .gone, .slide.active .filled, .slide.active .struck').length]")
        if back[0] != "#1" or back[2] != 0:
            problems.append(f"back to start: {back}")
        open_at(page, url, 18)
        if page.evaluate("document.querySelector('.slide.active').id") != page.evaluate("document.querySelectorAll('#stage > .slide')[17].id"):
            problems.append("loading #18 did not open slide 18")
        page.keyboard.press("d")
        if page.evaluate("document.documentElement.getAttribute('data-theme')") != "dark":
            problems.append("D did not switch to dark")
        problems += page.errors
        if a.csp:
            problems += [f"CSP: {v}" for v in page.evaluate("window.__csp || []")]
        mobile = new_page(b, width=400, height=800, device_scale_factor=2, has_touch=True)
        for n in range(1, n_slides + 1):
            open_at(mobile, url, n)
            forward(mobile, steps[n - 1])
            sw, cw = mobile.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            if sw > cw:
                problems.append(f"400px viewport, slide {n}: horizontal scroll {sw}>{cw}")
        problems += mobile.errors
        b.close()
    print(f"checked {n_slides} slides, {sum(steps)} steps")
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
    s.add_argument("--dark", action="store_true", help="with --set all: dark shots too")
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
