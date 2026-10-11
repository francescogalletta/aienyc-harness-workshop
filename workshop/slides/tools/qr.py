"""Writes the QR code for the setup slide into src/assets/qr.json.

    python tools/qr.py [URL]      (default: the url of the setup slide)

Needs the third-party `segno` package (pip install segno); the build does not.
The path draws each run of dark modules as one rectangle; the setup layout wraps
it in an SVG whose colours come from the --qr-ink / --qr-ground tokens.
"""
import json
import sys
import tomllib
from pathlib import Path

import segno

SRC = Path(__file__).resolve().parent.parent / "src"


def setup_url() -> str:
    for f in sorted((SRC / "slides").glob("*.toml")):
        for s in tomllib.loads(f.read_text(encoding="utf-8")).get("slide", []):
            if s.get("layout") == "setup":
                return s["url"]
    raise SystemExit("no setup slide found; pass the URL")


url = sys.argv[1] if len(sys.argv) > 1 else setup_url()
q = segno.make(url, error="m", micro=False)
m = q.matrix
n = len(m)
d = []
for y, row in enumerate(m):
    x = 0
    while x < n:
        if row[x]:
            s = x
            while x < n and row[x]:
                x += 1
            d.append(f"M{s} {y}h{x - s}v1h-{x - s}z")
        else:
            x += 1
out = SRC / "assets" / "qr.json"
out.write_text(json.dumps({"url": url, "size": n, "path": "".join(d)}, indent=2) + "\n", encoding="utf-8")
print(f"wrote {out}: version {q.version}, {n}x{n} modules")
