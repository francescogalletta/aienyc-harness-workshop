#!/usr/bin/env python3
"""Build the workshop deck from src/. Standard library only (Python 3.11+), no network.

    python build.py                  deck.html (default theme) + dist/deck.fragment.html
    python build.py --theme nord     dist/deck.nord.html + dist/deck.nord.fragment.html
    python build.py --all            every theme in src/themes/
    python build.py --check          validate the sources; exit 1 on problems
    python build.py --gallery [--theme NAME | --all]   dist/gallery.<theme>.html (+ fragment)
    python build.py --looks a,b,c [--gallery]           dist/deck.looks.html: several looks, one page, a switcher

The standalone form is a whole page. The fragment form is what the hosting page
wraps: <title>, the font <link>, one <style>, the markup, one <script>.
Same input gives byte-identical output.
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import sys
import tomllib
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
DIST = HERE / "dist"

STEP_ATTRS = {"step": "data-step", "out": "data-step-out", "fill": "data-step-fill",
              "strike": "data-step-strike", "mute": "data-step-mute"}
GAPS = ("xs", "s", "m", "l", "xl")
STANDALONE_RESET = "[hidden] { display: none !important; }\nimg { max-width: 100%; }\n"


class BuildError(Exception):
    pass


# ===========================================================================
# Escaping
# ===========================================================================
class Markup(str):
    """A string that is already HTML. The template engine never escapes it again."""
    __slots__ = ()


def escape(value) -> Markup:
    if isinstance(value, Markup):
        return value
    s = str(value)
    return Markup(s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


# ===========================================================================
# A tiny template engine
#   {{ path }}  {{ path|filter|filter }}      values are HTML-escaped unless Markup
#   {% if [not] path %} {% elif [not] path %} {% else %} {% endif %}
#   {% for x in path %} ... {% endfor %}      loop.index, loop.index0, loop.first, loop.last
#   {% include "name.html" %}                 rendered with the current variables
#   {# comment #}
# A line holding only a {% %} tag (other than include) or a comment disappears
# entirely, so templates can be laid out readably. Undefined values are errors,
# except in an if (false) .
# ===========================================================================
class TemplateError(BuildError):
    pass


class Undefined:
    def __init__(self, name: str):
        self.name = name

    def __bool__(self):
        return False


_TAG = re.compile(r"(\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\})", re.S)
_ALONE = re.compile(r"^[ \t]*(\{%(?!\s*include\b)(?:(?!%\}).)*%\}|\{#(?:(?!#\}).)*#\})[ \t]*\r?\n", re.M | re.S)
_PATH = re.compile(r"[A-Za-z_][\w]*(?:\.\w+)*")


class Template:
    def __init__(self, source: str, name: str = "<string>", loader: "Loader | None" = None):
        self.name, self.loader = name, loader
        self.nodes = self._parse(_TAG.split(_ALONE.sub(lambda m: m.group(1), source)))

    # ---- parsing ----
    def _err(self, msg):
        return TemplateError(f"{self.name}: {msg}")

    def _path(self, text):
        text = text.strip()
        if not _PATH.fullmatch(text):
            raise self._err(f"bad expression {text!r}")
        return text

    def _expr(self, text):
        path, *filters = [t.strip() for t in text.split("|")]
        return ("expr", self._path(path), filters)

    def _cond(self, text):
        text = text.strip()
        neg = text.startswith("not ")
        return (neg, self._path(text[4:] if neg else text))

    def _parse(self, tokens):
        root: list = []
        stack: list = [("root", root, None)]  # (kind, body being filled, node)
        for tok in tokens:
            if not tok or tok.startswith("{#"):
                continue
            body = stack[-1][1]
            if tok.startswith("{{"):
                body.append(self._expr(tok[2:-2]))
            elif tok.startswith("{%"):
                kw, _, rest = tok[2:-2].strip().partition(" ")
                rest = rest.strip()
                if kw == "if":
                    node = ["if", [(self._cond(rest), [])], None]
                    body.append(node)
                    stack.append(("if", node[1][0][1], node))
                elif kw in ("elif", "else", "endif"):
                    if stack[-1][0] not in ("if", "else") or (kw != "endif" and stack[-1][0] == "else"):
                        raise self._err(f"unexpected {{% {kw} %}}")
                    node = stack.pop()[2]
                    if kw == "elif":
                        branch = (self._cond(rest), [])
                        node[1].append(branch)
                        stack.append(("if", branch[1], node))
                    elif kw == "else":
                        node[2] = []
                        stack.append(("else", node[2], node))
                elif kw == "for":
                    m = re.fullmatch(r"(\w+)\s+in\s+(.+)", rest)
                    if not m:
                        raise self._err(f"bad for: {rest!r}")
                    node = ["for", m.group(1), self._path(m.group(2)), []]
                    body.append(node)
                    stack.append(("for", node[3], node))
                elif kw == "endfor":
                    if stack[-1][0] != "for":
                        raise self._err("unexpected {% endfor %}")
                    stack.pop()
                elif kw == "include":
                    body.append(["include", rest.strip("\"'")])
                else:
                    raise self._err(f"unknown tag {kw!r}")
            else:
                body.append(tok)
        if len(stack) != 1:
            raise self._err(f"unclosed {{% {stack[-1][0]} %}}")
        return root

    # ---- rendering ----
    def render(self, context: dict, filters: dict | None = None) -> str:
        out: list[str] = []
        self._render(self.nodes, [context], filters or {}, out)
        return "".join(out)

    def _lookup(self, path, scopes):
        head, *rest = path.split(".")
        for scope in reversed(scopes):
            if head in scope:
                val = scope[head]
                break
        else:
            return Undefined(path)
        for part in rest:
            if isinstance(val, dict) and part in val:
                val = val[part]
            elif isinstance(val, (list, tuple)) and part.isdigit() and int(part) < len(val):
                val = val[int(part)]
            else:
                return Undefined(path)
        return val

    def _render(self, nodes, scopes, filters, out):
        for node in nodes:
            if isinstance(node, str):
                out.append(node)
            elif node[0] == "expr":
                _, path, names = node
                val = self._lookup(path, scopes)
                for name in names:
                    if name not in filters:
                        raise self._err(f"unknown filter {name!r}")
                    if isinstance(val, Undefined):
                        break
                    val = filters[name](val)
                if isinstance(val, Undefined):
                    raise self._err(f"{val.name!r} is undefined")
                out.append(escape(val))
            elif node[0] == "if":
                for (neg, path), body in node[1]:
                    if bool(self._lookup(path, scopes)) != neg:
                        self._render(body, scopes, filters, out)
                        break
                else:
                    if node[2] is not None:
                        self._render(node[2], scopes, filters, out)
            elif node[0] == "for":
                _, var, path, body = node
                seq = self._lookup(path, scopes)
                if isinstance(seq, Undefined):
                    raise self._err(f"{seq.name!r} is undefined")
                seq = list(seq)
                for i, item in enumerate(seq):
                    loop = {"index": i + 1, "index0": i, "first": i == 0, "last": i == len(seq) - 1, "length": len(seq)}
                    self._render(body, scopes + [{var: item, "loop": loop}], filters, out)
            elif node[0] == "include":
                if not self.loader:
                    raise self._err("include without a loader")
                self.loader.get(node[1])._render_into(scopes, filters, out)

    def _render_into(self, scopes, filters, out):
        self._render(self.nodes, scopes, filters, out)


class Loader:
    def __init__(self, root: Path):
        self.root, self.cache = root, {}

    def get(self, name: str) -> Template:
        if name not in self.cache:
            path = self.root / name
            if not path.is_file():
                raise TemplateError(f"no template {name} in {self.root}")
            self.cache[name] = Template(path.read_text(encoding="utf-8"), name, self)
        return self.cache[name]


# ===========================================================================
# Inline markup:  ==Trust==   and   [text]{aside step=1}
# ===========================================================================
_SPAN = re.compile(r"\[([^\[\]]+)\]\{([^{}]*)\}")
_ACCENT = re.compile(r"==(.+?)==")


def reveal(item) -> Markup:
    """Build-step attributes from step/out/fill/strike/mute keys."""
    if not isinstance(item, dict):
        return Markup("")
    parts = []
    for key, attr in STEP_ATTRS.items():
        v = item.get(key)
        if v not in (None, False, ""):
            if not str(v).isdigit():
                raise BuildError(f"{key} must be a step number, not {v!r}")
            parts.append(f' {attr}="{v}"')
    return Markup("".join(parts))


def inline(text, roles: dict) -> Markup:
    s = escape(text)

    def span(m):
        classes, attrs = [], {}
        for word in m.group(2).split():
            if "=" in word:
                key, val = word.split("=", 1)
                if key not in STEP_ATTRS:
                    raise BuildError(f"unknown inline key {key!r} in {text!r}")
                attrs[key] = val
            elif word in roles:
                classes.append(roles[word])
            else:
                raise BuildError(f"unknown inline role {word!r} in {text!r} (known: {', '.join(roles)})")
        cls = f' class="{" ".join(classes)}"' if classes else ""
        return f"<span{cls}{reveal(attrs)}>{m.group(1)}</span>"

    s = _SPAN.sub(span, s)
    s = _ACCENT.sub(lambda m: f'<span class="{roles["accent"]}">{m.group(1)}</span>', s)
    return Markup(s)


def indent(text, by: str = "  ") -> Markup:
    return Markup("\n".join(by + line if line.strip() else line for line in str(text).split("\n")))


def fmt_num(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


# ===========================================================================
# Sources
# ===========================================================================
def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise BuildError(f"{path.relative_to(HERE)}: {e}") from None


class Deck:
    """Everything under src/, loaded once. gallery=True reads src/gallery/ instead of deck.toml + slides/."""

    def __init__(self, src: Path = SRC, gallery: bool = False):
        self.src, self.gallery = src, gallery
        self.slides_dir = src / "gallery" if gallery else src / "slides"
        self.meta = read_toml(self.slides_dir / "gallery.toml" if gallery else src / "deck.toml")
        self.vocab = read_toml(src / "layouts" / "layouts.toml")
        self.principles = json.loads((src / "principles.json").read_text(encoding="utf-8"))["principles"]
        for p in self.principles:
            p["ink"] = p.get("color", "") + "-ink"   # the colour as text or a thin stroke
            p["on"] = "--on-" + p.get("color", "").lstrip("-")  # text on the colour
        self.by_n = {p["n"]: p for p in self.principles}
        self.loader = Loader(src / "layouts")
        self.slides = self._load_slides()
        qr = src / "assets" / "qr.json"
        self.qr = json.loads(qr.read_text(encoding="utf-8")) if qr.exists() else None
        if self.qr:
            self.qr["box"] = self.qr["size"] + 8

    @property
    def themes(self) -> list[str]:
        return sorted(p.stem for p in (self.src / "themes").glob("*.css"))

    def _load_slides(self) -> list[dict]:
        slides = []
        rel = self.slides_dir.relative_to(self.src)
        for section in self.meta["sections"]:
            path = self.slides_dir / f"{section}.toml"
            if not path.exists():
                raise BuildError(f"the manifest lists section {section!r} but there is no {rel}/{section}.toml")
            data = read_toml(path)
            extra = set(data) - {"principle", "rail", "group", "slide"}
            if extra:
                raise BuildError(f"{rel}/{section}.toml: unknown top-level keys {sorted(extra)}")
            for i, slide in enumerate(data.get("slide", []), 1):
                slide = dict(slide)
                slide["_where"] = f"{rel}/{section}.toml, slide {i}"
                slide.setdefault("principle", data.get("principle"))
                slide.setdefault("rail", data.get("rail", True))
                group = data.get("group")
                if group is None and isinstance(data.get("principle"), int) and data["principle"] in self.by_n:
                    pr = self.by_n[data["principle"]]
                    group = f"{pr['n']} · {pr['name']}"
                slide.setdefault("group", group)
                slides.append(slide)
        return slides


# ===========================================================================
# Rendering slides
# ===========================================================================
class SlideRenderer:
    def __init__(self, deck: Deck, theme: str = ""):
        self.deck, self.theme = deck, theme
        v = deck.vocab
        self.layouts, self.roles, self.kinds = v["layouts"], v["roles"], v.get("kinds", {})
        self.rhythm, self.inline_roles = v["rhythm"], v["inline"]
        self.line_roles, self.modifiers = v.get("line_roles", {}), v.get("modifiers", {})
        self.h1_used = False

    # ---- filters ----
    def filters(self) -> dict:
        assets = self.deck.src / "assets"

        def asset(name):
            path = assets / name
            if not path.is_file():
                raise BuildError(f"no asset {name} in src/assets")
            return Markup(path.read_text(encoding="utf-8").rstrip("\n"))

        def asset_uri(name):
            path = assets / name
            if not path.is_file():
                raise BuildError(f"no asset {name} in src/assets")
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"

        def bare_url(url):
            return re.sub(r"^\w+://", "", url).rstrip("/")

        def url_lines(url):
            return Markup("/<wbr>".join(escape(part) for part in bare_url(url).split("/")))

        return {
            "text": lambda v: inline(v, self.inline_roles),
            "e": escape,
            "raw": lambda v: Markup(str(v)),
            "reveal": reveal,
            "num": fmt_num,
            "indent": indent,
            "asset": asset,
            "asset_uri": asset_uri,
            "bare_url": bare_url,
            "url_lines": url_lines,
            "blocks": self.render_blocks,
            "viz": lambda spec: viz_markup(spec, self.deck),
        }

    # ---- blocks ----
    def role_of(self, block: dict, roles: dict) -> str:
        for key in block:
            if key in roles:
                return key
        raise BuildError(f"block {block!r} names no role (known: {', '.join(roles)})")

    def render_blocks(self, blocks) -> Markup:
        if not isinstance(blocks, list):
            raise BuildError("blocks must be a list")
        pieces, prev = [], None
        for block in blocks:
            role = self.role_of(block, self.roles)
            gap = block.get("gap")
            if gap is None and prev is not None:
                gap = self.rhythm.get(f"{prev} {role}", self.rhythm["default"])
            pieces.append(self.render_block(block, role, gap))
            prev = role
        return indent("\n".join(pieces))

    def render_block(self, block: dict, role: str, gap: str | None) -> Markup:
        spec = self.roles[role]
        if gap is not None and gap not in GAPS:
            raise BuildError(f"gap {gap!r} is not one of {GAPS}")
        tag = spec.get("tag", "div")
        if tag == "heading":
            tag = "p" if self.h1_used else "h1"
            self.h1_used = True
        gap_cls = f" gap-{gap}" if gap else ""
        classes = [spec["class"]] + [cls for key, cls in self.modifiers.items() if block.get(key)]
        ctx = {"b": block, "role": role, "text": block[role], "tag": tag, "gap_cls": gap_cls,
               "cls": " ".join(classes) + gap_cls, "attrs": reveal(block), "aria": block.get("say") or spec.get("aria")}
        if role == "viz":
            return viz_markup(block, self.deck, gap_cls)
        prep = getattr(self, f"prep_{role}", None)
        if prep:
            ctx.update(prep(block))
        template = self.deck.loader.get(f"blocks/{spec.get('template', 'text')}.html")
        return Markup(template.render(ctx, self.filters()).strip("\n"))

    @staticmethod
    def sequence(n: int, start: int = 0, key2: str = "out") -> list[dict]:
        """Item i shows at step start+i and goes (out) or mutes at the next step; the last one stays."""
        out = []
        for i in range(n):
            d = {"step": start + i if start + i else None, key2: start + i + 1 if i < n - 1 else None}
            out.append(d)
        return out

    def prep_display(self, block):
        items = block.get("cycle")
        if not items:
            return {}
        return {"cycle": [{"text": t, "attrs": reveal(s)} for t, s in zip(items, self.sequence(len(items)))]}

    def prep_lines(self, block):
        lines = []
        for item in block["lines"]:
            r = self.role_of(item, self.line_roles)
            lines.append({"cls": self.line_roles[r], "text": item[r], "attrs": reveal(item)})
        return {"lines": lines}

    def prep_tally(self, block):
        items = block["tally"]
        seq = self.sequence(len(items), block.get("from", 1), "mute")
        return {"items": [{"text": str(t), "attrs": reveal(s)} for t, s in zip(items, seq)]}

    # ---- slides ----
    def resolve(self, slide: dict) -> dict:
        """Validate a slide against its layout and fill in principle-derived defaults."""
        where = slide["_where"]
        name = slide.get("layout")
        if name not in self.layouts:
            raise BuildError(f"{where}: unknown layout {name!r} (known: {', '.join(self.layouts)})")
        layout = self.layouts[name]
        allowed = set(layout.get("fields", [])) | {"id", "name", "layout", "principle", "rail", "group", "chrome", "marks", "_where"}
        unknown = set(slide) - allowed
        if unknown:
            raise BuildError(f"{where}: layout {name!r} has no fields {sorted(unknown)}")
        missing = [f for f in layout.get("required", []) if f not in slide]
        if missing:
            raise BuildError(f"{where}: layout {name!r} needs {missing}")
        s = dict(slide)
        if layout.get("variants"):   # a layout with variants: one template each, a default, unknown values rejected
            s.setdefault("variant", layout["default_variant"])
            if s["variant"] not in layout["variants"]:
                raise BuildError(f"{where}: layout {name!r} has no variant {s['variant']!r} (known: {', '.join(layout['variants'])})")
        pn = s.get("principle")
        if pn is not None and pn != "wrap" and pn not in self.deck.by_n:
            raise BuildError(f"{where}: principle {pn!r} is not in principles.json")
        if layout.get("principle"):
            if pn not in self.deck.by_n:
                raise BuildError(f"{where}: layout {name!r} needs a principle (set principle = n in the section file)")
            p = self.deck.by_n[pn]
            s["p"], s["prev"] = p, self.deck.by_n.get(pn - 1)
            kind = {}
            if "kind" in s:
                if s["kind"] not in self.kinds:
                    raise BuildError(f"{where}: unknown kind {s['kind']!r} (known: {', '.join(self.kinds)})")
                kind = self.kinds[s["kind"]]
            for k, v in kind.items():
                s.setdefault(k, v)
            fmt = {"n": p["n"], "name": p["name"], "kind": s.get("kind", ""), "kind_name": kind.get("kind_name", "")}
            s.setdefault("id", layout["id"].format(**fmt))
            s.setdefault("name", layout["name"].format(**fmt))
        if "id" not in s:
            raise BuildError(f"{where}: needs an id")
        s.setdefault("name", s["id"])
        s.setdefault("from_you", False)
        return s

    def render_slide(self, number: int, slide: dict) -> str:
        if self.deck.gallery:  # in a looks build the name is filled in live by looks.js
            slide = substitute(slide, {"{theme}": "[looks]{lookname}" if self.theme == "looks" else self.theme})
        s = self.resolve(slide)
        layout = self.layouts[s["layout"]]
        ps = self.deck.principles
        ctx = {**s, "principles": ps, "principles_top_down": list(reversed(ps)), "confetti_step": len(ps) + 1,
               "qr": self.deck.qr or Undefined("qr (src/assets/qr.json: run tools/qr.py)")}
        self.h1_used = False
        try:
            template = layout["variants"][s["variant"]] if layout.get("variants") else layout["template"]
            inner = self.deck.loader.get(f"{template}.html").render(ctx, self.filters())
        except BuildError as e:
            raise BuildError(f"{s['_where']} ({s['id']}): {e}") from None
        try:
            inner += overlays(s, self.deck)
        except BuildError as e:
            raise BuildError(f"{s['_where']} ({s['id']}): {e}") from None
        inner = "\n".join(line.rstrip() for line in inner.split("\n") if line.strip())
        chrome = s.get("chrome", True) is not False
        if chrome and s.get("group"):
            inner = f'  <p class="section-label">{escape(s["group"])}</p>\n' + inner
        classes = " ".join(c for c in ["slide", layout.get("class"), s.get("class") if s["layout"] == "raw" else None] if c)
        attrs = f' id="{escape(s["id"])}"'
        if s.get("principle") is not None:
            attrs += f' data-principle="{s["principle"]}"'
        if s.get("rail") is False:
            attrs += ' data-rail="off"'
        if not chrome:
            attrs += ' data-chrome="off"'
        return f"<!-- {number:02d} · {s['name']} -->\n<section class=\"{classes}\"{attrs}>\n{inner}\n</section>"

    def render_all(self) -> str:
        return "\n\n".join(self.render_slide(i, s) for i, s in enumerate(self.deck.slides, 1))

    def render_rail(self) -> str:
        ps = self.deck.principles
        return self.deck.loader.get("parts/rail.html").render({"principles_top_down": list(reversed(ps))}).rstrip("\n")


# ===========================================================================
# Visuals kit: viz blocks and marks (drawn at runtime by src/js/viz.js)
# ===========================================================================
VIZ_COMMON = {"step", "style", "animate"}
VIZ_TYPES = {  # type: (required keys, optional keys)
    "flow": (["label", "nodes"], ["direction", "columns", "links", "travel", "reveal", "numbers", "node_size", "node_width", "node_height", "gap", "width", "height"]),
    "bars": (["label", "data"], ["orient", "highlight", "highlight_step", "values", "axis", "max", "ticks", "prefix", "suffix", "decimals", "width", "height", "label_width"]),
    "waterfall": (["label", "start", "changes"], ["end", "reveal", "max", "ticks", "prefix", "suffix", "decimals", "axis", "width", "height"]),
    "line": (["label", "x", "series"], ["area", "points", "note", "max", "ticks", "prefix", "suffix", "axis", "width", "height"]),
    "timeline": (["label", "events"], ["start", "end", "reveal", "every", "months", "width", "height"]),
    "count": (["label", "to"], ["from", "prefix", "suffix", "decimals", "duration"]),
    "draw": (["label", "svg"], []),
}
MARK_KEYS = ({"target"}, {"kind", "step", "style", "note", "pad"})


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_step(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def is_date(v) -> bool:
    return isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) is not None


def validate_viz(kind: str, spec: dict, deck: "Deck") -> list[str]:
    """Problems with one viz block (empty list when it is fine)."""
    if kind not in VIZ_TYPES:
        return [f"unknown viz type {kind!r} (known: {', '.join(VIZ_TYPES)})"]
    req, opt = VIZ_TYPES[kind]
    p = []
    unknown = set(spec) - set(req) - set(opt) - VIZ_COMMON
    if unknown:
        p.append(f"viz {kind!r} has no keys {sorted(unknown)} (allowed: {', '.join(req + opt + sorted(VIZ_COMMON))})")
    p += [f"viz {kind!r} needs {k!r}" for k in req if k not in spec]
    if "label" in spec and not (isinstance(spec["label"], str) and spec["label"].strip()):
        p.append(f"viz {kind!r}: label must be a sentence saying what it shows (screen readers read it)")
    step = spec.get("step", 0)
    if "step" in spec and not is_step(step):
        p.append(f"viz {kind!r}: step must be a whole number >= 1")
        step = 0
    if spec.get("style", "clean") not in ("clean", "rough"):
        p.append(f"viz {kind!r}: style is 'clean' or 'rough'")
    if "animate" in spec and not isinstance(spec["animate"], bool):
        p.append(f"viz {kind!r}: animate is true or false")
    for k in ("width", "height", "max", "ticks", "node_width", "node_height", "gap", "label_width", "duration"):
        if k in spec and not (is_num(spec[k]) and spec[k] > 0):
            p.append(f"viz {kind!r}: {k} must be a positive number")

    def later(name, v):
        if v is None:
            return
        if not is_step(v):
            p.append(f"viz {kind!r}: {name} must be a whole number >= 1")
        elif step and v < step:
            p.append(f"viz {kind!r}: {name} ({v}) comes before the block's step ({step})")

    def pairs(name, v, min_len=1):
        if not (isinstance(v, list) and len(v) >= min_len and all(isinstance(r, list) and len(r) == 2 and isinstance(r[0], str) and is_num(r[1]) for r in v)):
            p.append(f"viz {kind!r}: {name} must be a list of [\"label\", number] pairs")
            return False
        return True

    if kind == "bars" and "data" in spec and pairs("data", spec["data"]):
        labels = [r[0] for r in spec["data"]]
        if spec.get("orient", "vertical") not in ("vertical", "horizontal"):
            p.append("viz 'bars': orient is 'vertical' or 'horizontal'")
        if "highlight" in spec and spec["highlight"] not in labels:
            p.append(f"viz 'bars': highlight {spec['highlight']!r} is not one of the labels")
        later("highlight_step", spec.get("highlight_step"))
        v = spec.get("values")
        if v is not None and v not in ("all", "none") and not (isinstance(v, list) and all(x in labels for x in v)):
            p.append("viz 'bars': values is 'all', 'none' or a list of labels")
        if "max" in spec and is_num(spec["max"]) and spec["max"] < max(r[1] for r in spec["data"]):
            p.append("viz 'bars': max is smaller than the largest value")
    if kind == "waterfall":
        if "start" in spec and not (isinstance(spec["start"], list) and len(spec["start"]) == 2 and is_num(spec["start"][1])):
            p.append("viz 'waterfall': start must be [\"label\", number]")
        if "changes" in spec:
            pairs("changes", spec["changes"])
        if spec.get("reveal", "all") not in ("all", "each"):
            p.append("viz 'waterfall': reveal is 'all' or 'each'")
    if kind == "line" and "x" in spec and "series" in spec:
        xs, ss = spec["x"], spec["series"]
        if not (isinstance(xs, list) and len(xs) >= 2 and all(isinstance(x, str) for x in xs)):
            p.append("viz 'line': x must be a list of at least two labels")
        elif not (isinstance(ss, list) and 1 <= len(ss) <= 3):
            p.append("viz 'line': series must be a list of 1 to 3 series (more belongs in small multiples)")
        else:
            for i, se in enumerate(ss, 1):
                if not (isinstance(se, dict) and isinstance(se.get("name"), str) and isinstance(se.get("values"), list)
                        and len(se["values"]) == len(xs) and all(is_num(v) for v in se["values"])):
                    p.append(f"viz 'line': series {i} needs a name and one number per x label ({len(xs)})")
                else:
                    later(f"series {i} step", se.get("step"))
            nt = spec.get("note")
            if nt is not None:
                if not (isinstance(nt, dict) and nt.get("at") in xs and isinstance(nt.get("text"), str)):
                    p.append("viz 'line': note needs at (one of the x labels) and text")
                elif not (1 <= nt.get("series", 1) <= len(ss)):
                    p.append("viz 'line': note series is out of range")
                else:
                    later("note step", nt.get("step"))
    if kind == "timeline" and "events" in spec:
        ev = spec["events"]
        if not (isinstance(ev, list) and ev and all(isinstance(e, dict) and is_date(e.get("date")) and isinstance(e.get("text"), str) for e in ev)):
            p.append("viz 'timeline': events must be a list of { date = \"YYYY-MM-DD\", text = \"…\" }")
        else:
            dates = [e["date"] for e in ev]
            if dates != sorted(dates):
                p.append("viz 'timeline': events must be in date order")
            for k in ("start", "end"):
                if k in spec and not is_date(spec[k]):
                    p.append(f"viz 'timeline': {k} must be YYYY-MM-DD")
            if is_date(spec.get("start")) and spec["start"] > dates[0] or is_date(spec.get("end")) and spec["end"] < dates[-1]:
                p.append("viz 'timeline': an event falls outside start..end")
            for e in ev:
                later(f"event {e['text']!r} step", e.get("step"))
        if spec.get("reveal", "all") not in ("all", "each"):
            p.append("viz 'timeline': reveal is 'all' or 'each'")
    if kind == "flow" and "node_size" in spec and spec["node_size"] not in ("xs", "s", "m", "l", "xl", "2xl"):
        p.append("viz 'flow': node_size is a step of the type scale: xs, s, m, l, xl or 2xl")
    if kind == "flow" and "nodes" in spec:
        nodes = spec["nodes"]
        if not (isinstance(nodes, list) and nodes):
            p.append("viz 'flow': nodes must be a non-empty list")
            nodes = []
        steps = []
        for i, n in enumerate(nodes, 1):
            if isinstance(n, str):
                continue
            if not (isinstance(n, dict) and isinstance(n.get("text"), str)):
                p.append(f"viz 'flow': node {i} must be text or {{ text = \"…\" }}")
                continue
            bad = set(n) - {"text", "principle", "role", "step", "at"}
            if bad:
                p.append(f"viz 'flow': node {i} has no keys {sorted(bad)}")
            if "principle" in n and n["principle"] not in deck.by_n:
                p.append(f"viz 'flow': node {i} principle {n['principle']!r} is not in principles.json")
            if n.get("role", "plain") not in ("plain", "muted", "accent"):
                p.append(f"viz 'flow': node {i} role is 'muted' or 'accent'")
            if "at" in n and not (isinstance(n["at"], list) and len(n["at"]) == 2 and all(is_step(v) for v in n["at"])):
                p.append(f"viz 'flow': node {i} at must be [column, row], counted from 1")
            later(f"node {i} step", n.get("step"))
            steps.append(n.get("step") or 0)
        if spec.get("direction", "row") not in ("row", "column", "grid"):
            p.append("viz 'flow': direction is 'row', 'column' or 'grid'")
        for lk in spec.get("links", []):
            if not (isinstance(lk, list) and len(lk) == 2 and all(isinstance(v, int) and 1 <= v <= len(nodes) for v in lk)):
                p.append(f"viz 'flow': link {lk!r} must be [from, to] node numbers (1..{len(nodes)})")
        if "travel" in spec:
            later("travel", spec["travel"])
            if is_step(spec["travel"]) and steps and spec["travel"] < max(steps):
                p.append("viz 'flow': travel comes before the last node appears")
    if kind == "count" and "to" in spec and not is_num(spec["to"]):
        p.append("viz 'count': to must be a number")
    if kind == "draw" and "svg" in spec and not (deck.src / "assets" / str(spec["svg"])).is_file():
        p.append(f"viz 'draw': no asset {spec['svg']!r} in src/assets")
    return p


def check_overlay_items(name: str, items, keys, deck) -> list[str]:
    req, opt = keys
    if not isinstance(items, list):
        return [f"{name} must be a list of tables"]
    p = []
    for i, m in enumerate(items, 1):
        if not isinstance(m, dict):
            p.append(f"{name} {i} must be a table")
            continue
        p += [f"{name} {i} needs {k!r}" for k in sorted(req - set(m))]
        bad = set(m) - req - opt
        if bad:
            p.append(f"{name} {i} has no keys {sorted(bad)}")
        if "step" in m and not is_step(m["step"]):
            p.append(f"{name} {i}: step must be a whole number >= 1")
        if name == "mark" and m.get("kind", "circle") not in ("circle", "underline", "bracket", "box"):
            p.append(f"mark {i}: kind is circle, underline, bracket or box")
    return p


def _json_attr(data) -> Markup:
    return escape(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def _fmt_value(v, spec) -> str:
    d = spec.get("decimals", 0)
    s = f"{abs(v):,.{d}f}"
    return ("−" if v < 0 else "") + spec.get("prefix", "") + s + spec.get("suffix", "")


def viz_table(kind: str, spec: dict) -> str:
    """A visually hidden table with the figure's data, for screen readers and copy-paste."""
    head, rows = [], []
    if kind == "bars":
        head, rows = ["Label", "Value"], [[r[0], _fmt_value(r[1], spec)] for r in spec["data"]]
    elif kind == "waterfall":
        run = spec["start"][1]
        head, rows = ["Item", "Change", "Total"], [[spec["start"][0], "", _fmt_value(run, spec)]]
        for lab, v in spec["changes"]:
            run += v
            rows.append([lab, ("+" if v >= 0 else "") + _fmt_value(v, spec), _fmt_value(run, spec)])
        rows.append([spec.get("end", "End"), "", _fmt_value(run, spec)])
    elif kind == "line":
        head = [""] + [s["name"] for s in spec["series"]]
        rows = [[x] + [_fmt_value(s["values"][i], spec) for s in spec["series"]] for i, x in enumerate(spec["x"])]
    elif kind == "timeline":
        head, rows = ["Date", "Event", "Value"], [[e["date"], e["text"], e.get("value", "")] for e in spec["events"]]
    elif kind == "flow":
        names = [n if isinstance(n, str) else n["text"] for n in spec["nodes"]]
        links = spec.get("links") or [[i, i + 1] for i in range(1, len(names))]
        head, rows = ["From", "To"], [[names[a - 1].replace("\n", " "), names[b - 1].replace("\n", " ")] for a, b in links]
    if not head:
        return f'<figcaption class="viz-sr">{escape(spec["label"])}</figcaption>'
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="viz-sr"><caption>{escape(spec["label"])}</caption><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def viz_markup(block: dict, deck: "Deck", gap_cls: str = "") -> Markup:
    """A viz block as the <figure> viz.js draws into (count: the number itself)."""
    if not isinstance(block, dict) or "viz" not in block:
        raise BuildError("a viz needs viz = \"<type>\"")
    spec = {k: v for k, v in block.items() if k not in ("viz", "gap")}
    kind = block["viz"]
    problems = validate_viz(kind, spec, deck)
    if problems:
        raise BuildError("; ".join(problems))
    lib = ' data-lib="rough"' if spec.get("style") == "rough" else ""
    data = _json_attr(spec)
    if kind == "count":
        step = f' data-step="{spec["step"]}"' if "step" in spec else ""
        return Markup(f'<p class="viz viz-count{gap_cls}" data-viz="count" data-spec="{data}"{step} title="{escape(spec["label"])}">'
                      f'{escape(_fmt_value(spec["to"], spec))}</p>')
    body = viz_table(kind, spec)
    if kind == "draw":
        body += "\n" + indent((deck.src / "assets" / spec["svg"]).read_text(encoding="utf-8").rstrip("\n"))
    return Markup(f'<figure class="viz viz-{kind}{gap_cls}" data-viz="{kind}"{lib} data-spec="{data}">\n  {body}\n</figure>')


def overlays(slide: dict, deck: "Deck") -> str:
    """Slide-level marks (annotations), appended inside the section."""
    out = ""
    if "marks" in slide:
        problems = check_overlay_items("mark", slide["marks"], MARK_KEYS, deck)
        if problems:
            raise BuildError("; ".join(problems))
        lib = ' data-lib="rough"' if any(m.get("style") == "rough" for m in slide["marks"]) else ""
        out += f'\n  <svg class="viz-marks" data-viz="mark"{lib} data-spec="{_json_attr({"marks": slide["marks"]})}" aria-hidden="true"></svg>'
    return out


def substitute(value, mapping: dict):
    """Replace placeholders such as {theme} in every string of a slide (gallery only)."""
    if isinstance(value, str):
        for k, v in mapping.items():
            value = value.replace(k, v)
        return value
    if isinstance(value, list):
        return [substitute(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, mapping) for k, v in value.items()}
    return value


VENDOR = {  # data-lib name: file under src/vendor/
    "rough": "rough/rough.js",
}


def kit_usage(markup: str) -> tuple[bool, list[str]]:
    """Whether rendered slides use the visuals kit, and which shelf libraries (in a fixed order)."""
    libs = set(re.findall(r'data-lib="(\w+)"', markup))
    unknown = libs - set(VENDOR)
    if unknown:
        raise BuildError(f"data-lib names an unknown library {sorted(unknown)} (known: {', '.join(VENDOR)})")
    return ('data-viz="' in markup), [name for name in VENDOR if name in libs]


# ===========================================================================
# Themes and CSS
# ===========================================================================
_ALT = re.compile(r':root\[data-palette="alternate"\]\s*\{(.*?)\}', re.S)
_PRIMARY = re.compile(r":root\s*\{(.*?)\}", re.S)
_FONT_LINK = re.compile(r"font-link:\s*(\S+)")
_SCHEME = re.compile(r"(?<![\w-])color-scheme\s*:\s*(light|dark)\s*;")
PALETTE_MODES = ("primary", "alternate", "system")


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def declarations(block: str) -> dict:
    out = {}
    for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", strip_comments(block)):
        out[m.group(1)] = m.group(2).strip()
    return out


class Theme:
    """A theme file: a primary palette on :root and an alternate on :root[data-palette="alternate"].
    Each block says which kind it is with color-scheme: light or dark."""

    def __init__(self, path: Path):
        self.name, self.path = path.stem, path
        self.text = path.read_text(encoding="utf-8")
        m = _FONT_LINK.search(self.text)
        self.font_link = m.group(1) if m else None
        head = re.search(r"/\*(.*?)\*/", self.text, re.S)
        meta = dict(re.findall(r"^\s*(name|short):\s*(.+?)\s*$", head.group(1) if head else "", re.M))
        self.display = meta.get("name", self.name)       # shown in the looks bar
        self.short = meta.get("short", self.display[:5])  # ... when the bar is narrow
        bare = strip_comments(self.text)
        primary, alt = _PRIMARY.search(bare), _ALT.search(bare)
        self.primary = declarations(primary.group(1)) if primary else {}
        self.alternate = declarations(alt.group(1)) if alt else {}
        sp = _SCHEME.search(primary.group(1)) if primary else None
        sa = _SCHEME.search(alt.group(1)) if alt else None
        self.schemes = (sp.group(1) if sp else None, sa.group(1) if sa else None)

    def css(self, mode: str = "primary") -> str:
        """The theme as the page needs it. mode "primary": everyone sees the primary palette and
        data-palette="alternate" on the root shows the other one (the deck's D key). "alternate": the
        other way round. "system": the palette whose color-scheme matches the viewer's (a host page's
        data-theme wins over the OS), until D sets data-palette. --palette-shown tells the deck's
        script which palette is on screen."""
        if mode not in PALETTE_MODES:
            raise BuildError(f"palette {mode!r}: use one of {', '.join(PALETTE_MODES)}")
        text = self.text
        p = _PRIMARY.search(text)
        if p:
            text = text[:p.end(1)].rstrip() + "\n  --palette-shown: primary;\n" + text[p.end(1):]
        a = _ALT.search(text)
        if not a:
            return text.strip("\n") + "\n"
        body = a.group(1).rstrip("\n ") + "\n  --palette-shown: alternate;"
        if mode == "primary":
            blocks = ':root[data-palette="alternate"] {' + body + "\n}"
        elif mode == "alternate":
            blocks = ':root:not([data-palette="primary"]) {' + body + "\n}"
        else:
            blocks = ':root[data-palette="alternate"] {' + body + "\n}"
            pa, al = self.schemes
            if pa and al and pa != al:
                other = "light" if al == "dark" else "dark"
                blocks += (f'\n@media (prefers-color-scheme: {al}) {{\n  :root:not([data-palette]):not([data-theme="{other}"]) {{'
                           + indent(body, "  ") + "\n  }\n}\n"
                           + f':root[data-theme="{al}"]:not([data-palette]) {{' + body + "\n}")
        text = text[:a.start()] + blocks + text[a.end():]
        return text.strip("\n") + "\n"


VIZ_TOKENS_MARK = "/* ---------- Visuals kit tokens"


def tokens_css(deck: Deck, kit: bool) -> str:
    """tokens.css; its visuals-kit block only when the build uses the kit."""
    text = (deck.src / "styles" / "tokens.css").read_text(encoding="utf-8")
    if not kit and VIZ_TOKENS_MARK in text:
        text = text[:text.index(VIZ_TOKENS_MARK)]
    return text


def scoped_theme_css(theme: Theme, mode: str = "primary") -> str:
    """A theme's CSS with every block scoped to :root[data-look="<name>"], for a looks build."""
    return theme.css(mode).replace(":root", f':root[data-look="{theme.name}"]')


def build_css(deck: Deck, theme: Theme, standalone: bool, kit: bool = False, looks: list[Theme] | None = None) -> str:
    mode = deck.meta.get("palette", "primary")
    styles = deck.src / "styles"
    parts = []
    if standalone:
        parts.append(STANDALONE_RESET)
    parts.append("/* ---------- Tokens: defaults (src/styles/tokens.css) ---------- */\n" + tokens_css(deck, kit))
    if looks:
        for t in looks:
            parts.append(f"/* ---------- Look: {t.name} (src/themes/{t.name}.css), on data-look=\"{t.name}\" ---------- */\n" + scoped_theme_css(t, mode))
    else:
        parts.append(f"/* ---------- Theme: {theme.name} (src/themes/{theme.name}.css) ---------- */\n" + theme.css(mode))
    parts.append("/* ---------- Base (src/styles/base.css) ---------- */\n" + (styles / "base.css").read_text(encoding="utf-8"))
    parts.append("/* ---------- Components (src/styles/components.css) ---------- */\n" + (styles / "components.css").read_text(encoding="utf-8"))
    if kit:
        parts.append("/* ---------- Visuals kit (src/styles/viz.css) ---------- */\n" + (styles / "viz.css").read_text(encoding="utf-8"))
    if deck.gallery:
        parts.append("/* ---------- Gallery (src/gallery/gallery.css) ---------- */\n" + (deck.slides_dir / "gallery.css").read_text(encoding="utf-8"))
    if looks:
        parts.append("/* ---------- Looks switcher (src/styles/looks.css) ---------- */\n" + (styles / "looks.css").read_text(encoding="utf-8"))
    return "\n".join(p.strip("\n") + "\n" for p in parts)


def vendor_js(deck: Deck, name: str) -> str:
    folder = deck.src / "vendor" / name
    note = (folder / "VERSION").read_text(encoding="utf-8").strip() if (folder / "VERSION").exists() else name
    code = (deck.src / "vendor" / VENDOR[name]).read_text(encoding="utf-8")
    code = re.sub(r"//# sourceMappingURL=\S+", "", code).replace("</script", "<\\/script").strip("\n")
    return f"/* ---- vendor: {note} ---- */\n{code}"


def build_js(deck: Deck, kit: bool = False, libs: list[str] = (), looks: bool = False) -> str:
    js = deck.src / "js"
    modules = ([js / "looks.js"] if looks else []) + [js / "confetti.js"] + ([js / "viz.js"] if kit else []) + [js / "deck.js"]
    if deck.gallery:
        modules.append(deck.slides_dir / "gallery.js")
    body = "\n\n".join(m.read_text(encoding="utf-8").strip("\n") for m in modules)
    main = "(function () {\n" + indent(body) + "\n})();"
    return "\n".join([vendor_js(deck, name) for name in libs] + [main])


# ===========================================================================
# Output
# ===========================================================================
def build(deck: Deck, theme_name: str, standalone: bool, looks: list[str] | None = None) -> str:
    """One page. With looks, every listed theme is in it, scoped by data-look, with a switcher."""
    names = list(looks) if looks else [theme_name]
    themes = []
    for name in names:
        if not (deck.src / "themes" / f"{name}.css").is_file():
            raise BuildError(f"no theme {name!r}")
        t = Theme(deck.src / "themes" / f"{name}.css")
        if not t.font_link:
            raise BuildError(f"themes/{name}.css: no 'font-link:' line in its first comment")
        themes.append(t)
    theme = themes[0]
    r = SlideRenderer(deck, "looks" if looks else theme_name)
    slides = r.render_all()
    kit, libs = kit_usage(slides)
    if looks:
        title = deck.meta["title"] + " · looks: " + ", ".join(names)
    else:
        title = deck.meta["title"] + (f" · {theme_name}" if deck.gallery else "")
    font_links = list(dict.fromkeys(t.font_link for t in themes))
    ctx = {"standalone": standalone, "lang": deck.meta.get("lang", "en"), "title": title, "font_links": font_links,
           "css": Markup(build_css(deck, theme, standalone, kit, themes if looks else None).rstrip("\n")),
           "motion": deck.meta.get("motion", "off"), "slides": Markup(slides),
           "looks": [{"id": t.name, "name": t.display, "short": t.short} for t in themes] if looks else [],
           "rail": Markup(r.render_rail()), "js": Markup(build_js(deck, kit, libs, bool(looks)))}
    return deck.loader.get("deck.html").render(ctx)


def looks_outputs(deck: Deck, names: list[str]) -> dict[Path, str]:
    stem = "gallery" if deck.gallery else "deck"
    return {DIST / f"{stem}.looks.html": build(deck, names[0], True, names),
            DIST / f"{stem}.looks.fragment.html": build(deck, names[0], False, names)}


def outputs(deck: Deck, theme: str) -> dict[Path, str]:
    if deck.gallery:
        return {DIST / f"gallery.{theme}.html": build(deck, theme, True),
                DIST / f"gallery.{theme}.fragment.html": build(deck, theme, False)}
    default = theme == deck.meta["theme"]
    stand = HERE / "deck.html" if default else DIST / f"deck.{theme}.html"
    frag = DIST / ("deck.fragment.html" if default else f"deck.{theme}.fragment.html")
    return {stand: build(deck, theme, True), frag: build(deck, theme, False)}


def write(files: dict[Path, str]):
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(HERE)}  ({len(text.encode()):,} bytes)")


# ===========================================================================
# Checks
# ===========================================================================
_COLOR_PROPS = re.compile(r"^(color|background(-color)?|fill|stroke|border(-\w+)*|outline(-color)?|box-shadow|text-decoration(-color)?|caret-color|column-rule)$")
_NAMED = re.compile(r"\b(white|black|red|green|blue|gray|grey|silver|navy|teal|orange|yellow|purple|pink|maroon|olive|lime|aqua|fuchsia)\b")
_PX_PROPS = re.compile(r"^(padding(-\w+)*|margin(-\w+)*|gap|row-gap|column-gap|border(-\w+)*|outline(-\w+)*|stroke-width|text-decoration-thickness|text-underline-offset|outline-offset|letter-spacing)$")


def css_rules(css: str):
    """Yield (selector, property, value) for every declaration, keyframes included."""
    css = strip_comments(css)
    depth, start, sel_stack = 0, 0, []
    for m in re.finditer(r"[{}]", css):
        if m.group() == "{":
            sel_stack.append(css[start:m.start()].strip().split(";")[-1].strip())
            start = m.end()
        else:
            body = css[start:m.start()]
            sel = sel_stack.pop() if sel_stack else ""
            for decl in body.split(";"):
                if ":" in decl and not decl.strip().startswith("@"):
                    prop, val = decl.split(":", 1)
                    prop = prop.strip()
                    if re.fullmatch(r"-?-?[\w-]+", prop):
                        yield sel, prop, val.strip()
            start = m.end()


def literal_problems(name: str, css: str) -> list[str]:
    problems = []
    for sel, prop, val in css_rules(css):
        where = f"{name}: {sel} {{ {prop}: {val} }}"
        if prop.startswith("--"):
            continue
        no_var = re.sub(r"var\([^()]*\)", "", val)
        if re.search(r"#[0-9a-fA-F]{3,8}\b", val) or re.search(r"\b(rgba?|hsla?|oklch|lab|lch)\(", val):
            problems.append(f"literal colour  {where}")
        elif _COLOR_PROPS.match(prop) and _NAMED.search(no_var):
            problems.append(f"named colour  {where}")
        if prop == "font-size" and "var(" not in val and val != "inherit":
            problems.append(f"literal font size  {where}")
        if prop == "font-family" and not val.startswith("var(") and val != "inherit":
            problems.append(f"literal font family  {where}")
        if prop == "font" or (prop == "border-radius" and "var(" not in val and val not in ("0", "inherit")):
            problems.append(f"literal radius/font  {where}")
        if _PX_PROPS.match(prop) and re.search(r"\d(px|rem)\b", no_var):
            problems.append(f"literal length  {where}")
    return problems


def contrast(a: str, b: str) -> float:
    def lum(h):
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        rgb = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def resolve_color(name: str, tokens: dict, seen=()) -> str | None:
    val = tokens.get(name)
    if val is None or name in seen:
        return None
    m = re.fullmatch(r"var\((--[\w-]+)(?:\s*,\s*(.+))?\)", val)
    if m:
        return resolve_color(m.group(1), tokens, seen + (name,)) or (m.group(2) or None)
    return val if re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", val) else None


CONTRAST_PAIRS = [  # (foreground, background, minimum)
    *[(f"--on-principle-{n}", f"--principle-{n}", 4.0) for n in range(1, 6)],
    *[(f"--principle-{n}-ink", "--slide-bg", 3.0) for n in range(1, 6)],
    ("--text", "--slide-bg", 7.0), ("--text-quiet", "--slide-bg", 4.5), ("--text-muted", "--slide-bg", 4.5),
    ("--accent-trust", "--slide-bg", 4.5), ("--text", "--surface", 4.5), ("--pill-text", "--pill-fill", 4.5),
    ("--ask-text", "--ask-fill", 4.5), ("--qr-ink", "--qr-ground", 7.0),
]


def contrast_report(deck: Deck, theme: Theme) -> tuple[list[str], list[str]]:
    defaults = declarations((deck.src / "styles" / "tokens.css").read_text(encoding="utf-8"))
    lines, problems = [], []
    for mode, tokens in (("primary", {**defaults, **theme.primary}), ("alternate", {**defaults, **theme.primary, **theme.alternate})):
        worst = None
        for fg, bg, minimum in CONTRAST_PAIRS:
            if fg not in tokens or bg not in tokens:
                continue
            a, b = resolve_color(fg, tokens), resolve_color(bg, tokens)
            if not a or not b:
                problems.append(f"{theme.name} {mode}: cannot resolve {fg} or {bg} to a hex colour")
                continue
            c = contrast(a, b)
            if fg.startswith("--on-principle") and (worst is None or c < worst[0]):
                worst = (c, bg)
            if c < minimum:
                problems.append(f"{theme.name} {mode}: {fg} on {bg} is {c:.2f}:1 (needs {minimum}:1)")
        if worst:
            lines.append(f"{theme.name:10} {mode:9}  worst text on a principle fill: {worst[0]:.2f}:1 ({worst[1]})")
    return lines, problems


class _Balance(HTMLParser):
    VOID = {"br", "wbr", "img", "meta", "link", "input", "hr", "source", "path", "rect"}

    def __init__(self):
        super().__init__()
        self.stack, self.problems = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.problems.append(f"</{tag}> closes <{self.stack[-1] if self.stack else 'nothing'}> near line {self.getpos()[0]}")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


def check(deck: Deck) -> int:
    problems, notes = [], []
    styles = deck.src / "styles"
    tokens_css = (styles / "tokens.css").read_text(encoding="utf-8")
    base_css = (styles / "base.css").read_text(encoding="utf-8")
    comp_css = (styles / "components.css").read_text(encoding="utf-8")
    viz_css = (styles / "viz.css").read_text(encoding="utf-8") if (styles / "viz.css").exists() else ""
    looks_css = (styles / "looks.css").read_text(encoding="utf-8") if (styles / "looks.css").exists() else ""
    gallery = Deck(deck.src, gallery=True) if (deck.src / "gallery" / "gallery.toml").exists() else None
    gal_css = (gallery.slides_dir / "gallery.css").read_text(encoding="utf-8") if gallery else ""
    js_files = sorted((deck.src / "js").glob("*.js")) + ([gallery.slides_dir / "gallery.js"] if gallery else [])
    js = "\n".join(p.read_text(encoding="utf-8") for p in js_files)
    themes = {name: Theme(deck.src / "themes" / f"{name}.css") for name in deck.themes}
    if deck.meta.get("palette", "primary") not in PALETTE_MODES:
        problems.append(f"deck.toml: palette = {deck.meta.get('palette')!r}; use one of {', '.join(PALETTE_MODES)}")
    if deck.meta["theme"] not in themes:
        problems.append(f"deck.toml: default theme {deck.meta['theme']!r} is not in src/themes/")

    # principles
    ns = [p.get("n") for p in deck.principles]
    if ns != list(range(1, len(ns) + 1)):
        problems.append(f"principles.json: n must run 1..{len(ns)} in order, got {ns}")
    for p in deck.principles:
        for key in ("n", "name", "emoji", "color", "minutes", "statement", "builds_on"):
            if key not in p:
                problems.append(f"principles.json: principle {p.get('n')} has no {key!r}")

    # slides (deck and gallery): render every one (catches unknown layouts/fields/roles/markup
    # and bad viz blocks), ids, balance, hand-written viz figures
    markup = ""
    for book in [deck] + ([gallery] if gallery else []):
        part = ""
        try:
            r = SlideRenderer(book, book.meta.get("theme", "blueprint"))
            part = r.render_all() + "\n" + r.render_rail()
        except BuildError as e:
            problems.append(str(e))
        ids = re.findall(r'<section class="[^"]*" id="([^"]+)"', part)
        for dup in sorted({i for i in ids if ids.count(i) > 1}):
            problems.append(f"duplicate slide id {dup!r}")
        bal = _Balance()
        bal.feed(part)
        problems += [f"markup: {p}" for p in bal.problems] + ([f"markup: unclosed {bal.stack}"] if bal.stack else [])
        if re.search(r"#[0-9a-fA-F]{6}\b", re.sub(r'data-spec="[^"]*"', "", part)):
            problems.append("markup: literal hex colour in slide markup")
        for m in re.finditer(r'data-viz="(\w+)"(?:[^>]*?data-spec="([^"]*)")?', part):
            kind, raw = m.group(1), m.group(2)
            if kind == "mark":
                continue
            if kind not in VIZ_TYPES:
                problems.append(f"markup: unknown viz type {kind!r}")
            elif raw is not None and kind != "draw":
                try:
                    spec = json.loads(raw.replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))
                    problems += [f"markup: {x}" for x in validate_viz(kind, spec, book)]
                except json.JSONDecodeError:
                    problems.append(f"markup: data-spec of a {kind!r} figure is not JSON")
        if deck.qr:
            for s in book.slides:
                if s.get("layout") == "setup" and s.get("url") != deck.qr.get("url"):
                    problems.append(f"{s['_where']}: QR in src/assets/qr.json is for {deck.qr.get('url')!r}, not {s.get('url')!r}: run tools/qr.py")
        markup += part + "\n"

    # literal values outside the token files
    problems += literal_problems("styles/base.css", base_css) + literal_problems("styles/components.css", comp_css)
    problems += literal_problems("styles/viz.css", viz_css) + literal_problems("gallery/gallery.css", gal_css)
    problems += literal_problems("styles/looks.css", looks_css)
    if re.search(r"#[0-9a-fA-F]{3,8}\b", js):
        problems.append("js: literal hex colour")
    for name, t in themes.items():
        non_custom = [f"{prop}: {val}" for sel, prop, val in css_rules(t.text) if not prop.startswith("--") and prop != "color-scheme"]
        if non_custom:
            problems.append(f"themes/{name}.css: themes hold custom properties only, found {non_custom}")
        if not t.font_link:
            problems.append(f"themes/{name}.css: no 'font-link:' line")
        if re.search(r"data-theme|prefers-color-scheme", strip_comments(t.text)):
            problems.append(f"themes/{name}.css: write the alternate palette as :root[data-palette=\"alternate\"]; the build adds any OS or host rules")
        if not t.alternate:
            problems.append(f"themes/{name}.css: no alternate palette (:root[data-palette=\"alternate\"] {{ ... }})")
        for which, scheme in zip(("primary", "alternate"), t.schemes):
            if scheme is None:
                problems.append(f"themes/{name}.css: the {which} palette must say color-scheme: light or dark")

    # tokens: referenced but undefined, theme parity, dark-only, unused
    defaults = declarations(tokens_css)
    styles_all = base_css + comp_css + viz_css + gal_css + looks_css
    local = set(re.findall(r"(--[\w-]+)\s*:", strip_comments(styles_all))) | set(re.findall(r"(--[\w-]+)\s*:", markup)) | set(re.findall(r"(--[\w-]+):", js))
    refs = set(re.findall(r"var\((--[\w-]+)", tokens_css + styles_all + markup))
    refs |= {t for t in re.findall(r"'(--[\w-]+)'", js) if not t.endswith("-")} | {p["color"] for p in deck.principles}
    theme_refs = set()
    for t in themes.values():
        theme_refs |= set(re.findall(r"var\((--[\w-]+)", strip_comments(t.text)))
    all_theme_defs = set().union(*(set(t.primary) | set(t.alternate) for t in themes.values())) if themes else set()
    for ref in sorted(refs | theme_refs):
        if ref not in defaults and ref not in local and ref not in all_theme_defs:
            problems.append(f"token {ref} is used but never defined")
    # A token used outside the themes with no default must be in every theme. Tokens a
    # theme uses only inside itself (its palette) are its own business.
    required = {r for r in refs if r not in defaults and r not in local}
    for name, t in themes.items():
        own = set(t.primary) | set(t.alternate)
        for tok in sorted(required - own):
            problems.append(f"themes/{name}.css: missing {tok} (other files use it and it has no default)")
        for tok in sorted(set(t.alternate) - set(t.primary) - set(defaults)):
            problems.append(f"themes/{name}.css: {tok} is set for the alternate palette only")
        for ref in sorted(set(re.findall(r"var\((--[\w-]+)", strip_comments(t.text))) - own - set(defaults)):
            problems.append(f"themes/{name}.css: uses {ref}, which it does not define")
    used = refs | theme_refs
    unused = sorted(tok for tok in set(defaults) | all_theme_defs if tok not in used)
    if unused:
        notes.append(f"unused tokens (not an error): {', '.join(unused)}")

    # contrast
    for t in themes.values():
        lines, probs = contrast_report(deck, t)
        notes += lines
        problems += probs

    # every theme builds, deck and gallery
    for name, t in themes.items():
        for book in [deck] + ([gallery] if gallery else []):
            try:
                build(book, name, True)
                build(book, name, False)
            except BuildError as e:
                problems.append(f"theme {name}{' (gallery)' if book.gallery else ''}: {e}")

    # a looks build of every theme, deck and gallery: builds, one switcher button per look, every look scoped
    if len(themes) > 1:
        names = list(themes)
        for book in [deck] + ([gallery] if gallery else []):
            try:
                page = build(book, names[0], False, names)
                if page.count("data-look-btn=") != len(names):
                    problems.append(f"looks build{' (gallery)' if book.gallery else ''}: expected {len(names)} look buttons")
                for n in names:
                    if f':root[data-look="{n}"] {{' not in page or f':root[data-look="{n}"][data-palette="alternate"]' not in page:
                        problems.append(f"looks build: theme {n} is not scoped to data-look=\"{n}\" (both palettes)")
                if re.search(r"(?m)^:root\s*\{[^}]*--slide-bg\s*:", page):
                    problems.append("looks build: a theme's colours are on bare :root (they would leak into every look)")
            except BuildError as e:
                problems.append(f"looks build{' (gallery)' if book.gallery else ''}: {e}")

    if deck.src == SRC and deck.meta["theme"] in themes and not problems:
        if (HERE / "deck.html").read_text(encoding="utf-8") != build(deck, deck.meta["theme"], True):
            problems.append("deck.html is out of date: run python build.py")

    for n in notes:
        print("note:", n)
    for p in problems:
        print("PROBLEM:", p)
    print(f"check: {len(deck.slides)} slides{f' + {len(gallery.slides)} gallery slides' if gallery else ''}, {len(themes)} themes, {len(problems)} problems")
    return 1 if problems else 0


# ===========================================================================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--theme", help="build this theme into dist/ (the default theme also writes deck.html)")
    ap.add_argument("--all", action="store_true", help="build every theme")
    ap.add_argument("--check", action="store_true", help="validate sources and exit")
    ap.add_argument("--looks", help="comma-separated themes: one page with all of them and a switcher → dist/deck.looks.html (or gallery.looks.html)")
    ap.add_argument("--gallery", action="store_true", help="build the design-system gallery (src/gallery/) into dist/gallery.<theme>.html")
    a = ap.parse_args(argv)
    try:
        deck = Deck()
        if a.check:
            return check(deck)
        if a.gallery:
            deck = Deck(gallery=True)
        if a.looks:
            names = [n.strip() for n in a.looks.split(",") if n.strip()]
            unknown = [n for n in names if n not in deck.themes]
            if unknown or len(names) < 2:
                raise BuildError(f"--looks needs two or more of: {', '.join(deck.themes)} (unknown: {unknown})")
            write(looks_outputs(deck, names))
            return 0
        names = deck.themes if a.all else [a.theme or deck.meta.get("theme") or Deck().meta["theme"]]
        for name in names:
            if name not in deck.themes:
                raise BuildError(f"no theme {name!r} (have: {', '.join(deck.themes)})")
            write(outputs(deck, name))
        return 0
    except BuildError as e:
        print(f"build error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
