"""Draws the hand-drawn sketch for the "How we got here" slide into src/assets/sketch.svg.

Standard library only. Seeded, so the same code always draws the same picture:
    python tools/sketch.py
Stroke widths, colours and label fonts come from the theme (.sketch rules in
src/styles/components.css); this file only decides geometry, words and clicks.
data-step="n" shows a group at click n; data-step-mute="n" greys a label.
"""
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "assets" / "sketch.svg"
R = random.Random(11)
def j(a=3): return R.uniform(-a, a)
def f(v): return f"{v:.1f}"

def box(x, y, w, h, r=20):
    p = lambda a, b: f"{f(a)} {f(b)}"
    d = f"M{p(x+r+j(), y+j(2))}"
    d += f" Q{p(x+w*0.5+j(25), y+j(6))} {p(x+w-r+j(), y+j(2))}"
    d += f" Q{p(x+w+j(2), y+j(2))} {p(x+w+j(2), y+r+j())}"
    d += f" Q{p(x+w+j(6), y+h*0.5+j(8))} {p(x+w+j(2), y+h-r+j())}"
    d += f" Q{p(x+w+j(2), y+h+j(2))} {p(x+w-r+j(), y+h+j(2))}"
    d += f" Q{p(x+w*0.5+j(25), y+h+j(6))} {p(x+r+j(), y+h+j(2))}"
    d += f" Q{p(x+j(2), y+h+j(2))} {p(x+j(2), y+h-r+j())}"
    d += f" Q{p(x+j(6), y+h*0.5+j(8))} {p(x+j(2), y+r+j())}"
    d += f" Q{p(x+j(2), y+j(2))} {p(x+r+j(), y+R.uniform(2,5))}"
    d += f" L{p(x+r+R.uniform(18,30), y+R.uniform(3,7))}"   # overshoot past the start
    return d

def head(tip, frm, size=26, spread=27):
    dx, dy = frm[0]-tip[0], frm[1]-tip[1]; L = math.hypot(dx, dy); dx, dy = dx/L, dy/L
    pts = []
    for s, k in ((1, 1.0), (-1, 0.85)):
        a = math.radians(spread*s + j(3))
        vx, vy = dx*math.cos(a)-dy*math.sin(a), dx*math.sin(a)+dy*math.cos(a)
        pts.append((tip[0]+vx*size*k, tip[1]+vy*size*k))
    return f"M{f(pts[0][0])} {f(pts[0][1])} L{f(tip[0])} {f(tip[1])} L{f(pts[1][0])} {f(pts[1][1])}"

def arrow(segs, cls="ln"):
    """segs: start point then list of (c1, c2, end) cubic segments."""
    s0 = segs[0]; d = f"M{f(s0[0])} {f(s0[1])}"
    for c1, c2, e in segs[1:]:
        d += f" C{f(c1[0])} {f(c1[1])} {f(c2[0])} {f(c2[1])} {f(e[0])} {f(e[1])}"
    c2, e = segs[-1][1], segs[-1][2]
    return f'<path class="{cls}" d="{d}"/><path class="ln" d="{head(e, c2)}"/>'

def scribble_ellipse(cx, cy, rx, ry, turns=1.85, start=200):
    pts = []
    n = int(28*turns)
    for i in range(n+1):
        t = math.radians(start + 360*turns*i/n)
        k = 1 + 0.035*math.sin(3.1*t) + (0.06 if i > n/2 else 0) + j(0.012)
        pts.append((cx + rx*k*math.cos(t), cy + ry*k*math.sin(t)))
    d = f"M{f(pts[0][0])} {f(pts[0][1])}"
    for a, b in zip(pts[1:-1], pts[2:]):
        m = ((a[0]+b[0])/2, (a[1]+b[1])/2)
        d += f" Q{f(a[0])} {f(a[1])} {f(m[0])} {f(m[1])}"
    return d

def node(name, x, y, w, h, rot, mute=None):
    cx, cy = x+w/2, y+h/2
    m = f' data-step-mute="{mute}"' if mute else ''
    return (f'<g transform="rotate({rot} {f(cx)} {f(cy)})"><path class="ln" d="{box(x, y, w, h)}"/>'
            f'<text class="nm" x="{f(cx)}" y="{f(cy+2)}" text-anchor="middle" dominant-baseline="central"{m}>{name}</text></g>')

def note(text, x, y, rot, big=False):
    c = "note big" if big else "note"
    return f'<text class="{c}" x="{x}" y="{y}" transform="rotate({rot} {x} {y})">{text}</text>'

def wob(pts, cls="ln"):
    d = f"M{f(pts[0][0]+j(1))} {f(pts[0][1]+j(1))}"
    for a, b in zip(pts[1::2], pts[2::2]):
        d += f" Q{f(a[0]+j(2))} {f(a[1]+j(2))} {f(b[0]+j(1))} {f(b[1]+j(1))}"
    return f'<path class="{cls}" d="{d}"/>'

# ---- geometry (viewBox 0 0 1640 760) ----
A = dict(x=10,  y=300, w=380, h=122, rot=-2)
B = dict(x=560, y=40,  w=450, h=112, rot=2.5)
C = dict(x=632, y=432, w=300, h=126, rot=-1.5)
D = dict(x=1112,y=548, w=322, h=112, rot=3)
E = dict(x=1372,y=268, w=222, h=118, rot=-3)

parts = []
parts.append('<g>' + node("The principles", **A) + note("too abstract", 44, 500, -4)
             + wob([(40, 520), (150, 528), (268, 514)], "ln tick") + '</g>')
# step 1: A -> B, curving up
parts.append('<g data-step="1">' + arrow([(338, 288), ((372, 190), (440, 106), (544, 100))])
             + node("A harness builder", mute=2, **B) + '</g>')
# step 2: cross out B, note
parts.append('<g data-step="2">'
             + wob([(578, 150), (790, 112), (1000, 52)]) + wob([(586, 52), (800, 96), (994, 158)])
             + wob([(612, 160), (720, 120), (930, 40)])
             + note("too meta", 878, 226, 4) + wob([(874, 248), (940, 258), (1032, 256)], "ln tick") + '</g>')
# step 3: A -> C, a detour that dips and comes back up
parts.append('<g data-step="3">' + arrow([(400, 392), ((474, 418), (452, 586), (536, 592)), ((590, 596), (606, 548), (624, 512))])
             + node("An example", **C) + '</g>')
# step 4: C -> D
parts.append('<g data-step="4">' + arrow([(940, 528), ((990, 566), (1030, 610), (1100, 606))])
             + node("Scaffolding", **D) + note("just for today", 1144, 728, -3)
             + wob([(1142, 744), (1200, 734), (1236, 752)], "ln tick") + '</g>')
# step 5: D -> E, going up
parts.append('<g data-step="5">' + arrow([(1362, 542), ((1382, 476), (1416, 430), (1452, 392))])
             + node("A UI", mute=6, **E) + '</g>')
# step 6: cross out E, note
parts.append('<g data-step="6">'
             + wob([(1388, 388), (1490, 336), (1598, 272)]) + wob([(1384, 278), (1488, 322), (1594, 390)])
             + note("looked like a product", 1176, 238, -4) + '</g>')
# step 7: dashed loop back to C, circle C, "here we are"
loop = [(1360, 340), ((1306, 350), (1262, 364), (1242, 394)), ((1224, 422), (1244, 454), (1274, 444)),
        ((1306, 432), (1290, 384), (1232, 384)), ((1150, 382), (1060, 396), (1006, 426))]
parts.append('<g data-step="7">' + arrow(loop, "ln dash")
             + f'<path class="ln" d="{scribble_ellipse(782, 494, 232, 112)}"/>'
             + note("here we are", 590, 694, -3, big=True)
             + wob([(586, 716), (730, 728), (884, 708)]) + '</g>')

svg = ('<svg class="sketch gap-s" viewBox="0 0 1640 760" role="img" aria-label="How we got here">\n    '
       + '\n    '.join(parts) + '\n  </svg>')
OUT.write_text(svg + "\n", encoding="utf-8")
print(f"wrote {OUT} ({len(svg)} chars)")
