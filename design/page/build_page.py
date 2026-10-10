"""Inline the design system (unmodified) and the page script into harness/ui/page.html.

Run from anywhere: python design/page/build_page.py. Edit page_src.html and app.js, never page.html.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DS = REPO / "design" / "system"
OUT = REPO / "harness" / "ui" / "page.html"

src = (HERE / "page_src.html").read_text(encoding="utf-8")
parts = {
    "/*@@TOKENS@@*/": (DS / "tokens.css").read_text(encoding="utf-8"),
    "/*@@BUNDLE_CSS@@*/": (DS / "bundle.css").read_text(encoding="utf-8"),
    "/*@@BUNDLE_JS@@*/": (DS / "bundle.js").read_text(encoding="utf-8"),
    "/*@@APP_JS@@*/": (HERE / "app.js").read_text(encoding="utf-8"),
}
for marker, text in parts.items():
    assert src.count(marker) == 1, marker
    assert "</script" not in text.lower() and "</style" not in text.lower(), marker
    src = src.replace(marker, text.rstrip("\n"))
OUT.write_text(src, encoding="utf-8")
print(OUT, OUT.stat().st_size, "bytes")
