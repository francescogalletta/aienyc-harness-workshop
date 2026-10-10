"""Looking up standard definitions (SPEC 4.2 and 4.6).

The interviewer never reads the web itself. It hands a short term to a
researcher, and gets back a definition and its sources. The researcher is
told the term and nothing else about the person.

Lookups are slow and easy to repeat, so the interview does not talk to a
researcher directly. It talks to a `ResearchDesk`, which remembers every
answer in the database, and it starts from a plan made up front.
"""
import json
import re
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ..config import load_config
from ..model import ToolSpec

MAX_QUERY_LENGTH = 100
MAX_PLANNED = 6                 # the most terms the up-front plan may read up on


@dataclass(frozen=True)
class Lookup:
    query: str
    found: bool
    name: str = ""
    definition: str = ""
    sources: tuple[dict, ...] = ()      # each {"title": ..., "url": ...}
    origin: str = ""                    # the researcher that answered

    def as_dict(self) -> dict:
        return {"query": self.query, "found": self.found, "name": self.name,
                "definition": self.definition, "sources": list(self.sources),
                "origin": self.origin}


class Researcher(Protocol):
    def look_up(self, query: str) -> Lookup: ...


class ReferenceResearcher:
    """Answers from a saved file of terms. Works offline, and always the same."""

    def __init__(self, path):
        self.path = Path(path)

    def look_up(self, query: str) -> Lookup:
        wanted = term_key(query)
        for entry in json.loads(self.path.read_text(encoding="utf-8")):
            names = [entry["term"], *entry.get("aliases", [])]
            if wanted in {term_key(name) for name in names}:
                return Lookup(query=query, found=True, name=entry["term"],
                              definition=entry["definition"], sources=tuple(entry["sources"]),
                              origin="reference")
        return Lookup(query=query, found=False, origin="reference")


WIKIPEDIA = ("https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1"
             "&generator=search&gsrlimit=1&gsrsearch={query}"
             "&prop=extracts|info|pageprops&exintro=1&explaintext=1&inprop=url&ppprop=disambiguation")
USER_AGENT = "finance-harness-workshop/0.1 (local research tool)"


class WikipediaResearcher:
    """Looks a term up on Wikipedia: one request, no model (SPEC 4.6).

    Only the query is sent, which keeps ground rule 6: nothing else the
    person said reaches the web.
    """

    def __init__(self, fetch=None, timeout: float = 15):
        self.timeout = timeout
        self.fetch = fetch or self._fetch

    def _fetch(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8")

    def look_up(self, query: str) -> Lookup:
        reply = json.loads(self.fetch(WIKIPEDIA.format(query=urllib.parse.quote(query, safe=""))))
        pages = (reply.get("query") or {}).get("pages") or {}
        page = next(iter(pages.values()), {})
        extract = " ".join((page.get("extract") or "").split())
        ambiguous = "disambiguation" in (page.get("pageprops") or {})
        title, url = page.get("title") or "", page.get("fullurl") or ""
        if not extract or ambiguous or not title or not url:
            return Lookup(query=query, found=False, origin="wikipedia")
        sentences = re.split(r"(?<=[.!?])\s+", extract)
        return Lookup(query=query, found=True, name=title,
                      definition=" ".join(sentences[:3])[:500],
                      sources=({"title": f"{title} (Wikipedia)", "url": url},),
                      origin="wikipedia")


class ChainResearcher:
    """Asks each researcher in turn and returns the first lookup that is found (SPEC 4.6)."""

    def __init__(self, researchers):
        self.researchers = list(researchers)

    def look_up(self, query: str) -> Lookup:
        answered, reason = False, None
        for researcher in self.researchers:
            try:
                lookup = researcher.look_up(query)
            except Exception as error:          # this one cannot answer: try the next
                reason = error
                continue
            answered = True
            if lookup.found:
                return lookup
        if reason is not None and not answered:
            raise RuntimeError(_one_line(reason))
        return Lookup(query=query, found=False)


def term_key(text: str) -> str:
    """Lower case, with any run of spaces, hyphens or underscores as one space."""
    return " ".join(str(text).lower().replace("-", " ").replace("_", " ").split())


def _one_line(error) -> str:
    return " ".join(str(error).split()) or type(error).__name__


def _reference(config):
    return ReferenceResearcher(config.reference_path)


def _wikipedia(config):
    return WikipediaResearcher()


def _claude_code(config):
    from .claude_code_research import ClaudeCodeResearcher      # imported only when asked for
    return ClaudeCodeResearcher(config.model_name)


def _auto(config):
    """The checked file first, the web only when the file does not know the term."""
    return ChainResearcher([_reference(config), _wikipedia(config)])


# name -> function that takes the Config and returns a Researcher
RESEARCHERS = {
    "reference": _reference,
    "wikipedia": _wikipedia,
    "claude_code": _claude_code,
    "auto": _auto,
}


def get_researcher(name: str | None = None) -> Researcher:
    """Return the researcher called `name`, or the configured one."""
    config = load_config()
    name = name or config.researcher
    if name not in RESEARCHERS:
        known = ", ".join(sorted(RESEARCHERS))
        raise ValueError(f"unknown researcher: {name!r} (known: {known})")
    return RESEARCHERS[name](config)


class ResearchDesk:
    """What the interview talks to: a researcher with a memory (SPEC 4.6).

    Every found lookup is kept in the table `lookups`, so a term is fetched
    once, whichever interview asks for it. Answers are research entries:
    `{"query", "status", "name", "definition", "sources", "origin", "planned", "cached"}`,
    where `status` is `found`, `not_found` or `failed` (then with `error`).

    The database is only touched on the calling thread; the researcher is
    what runs side by side.
    """

    def __init__(self, researcher, conn):
        self.researcher = researcher
        self.conn = conn
        self._lock = threading.Lock()
        self._looking: list[str] = []       # queries with the researcher right now

    def look_up(self, query: str) -> dict:
        return self.look_up_many([query])[0]

    def look_up_many(self, queries) -> list[dict]:
        """Look the queries up side by side. The entries keep the order of the queries."""
        queries = list(queries)
        entries = {query: self._remembered(query) for query in queries}
        missing = {}        # term key -> query: one request per term, however it is spelled
        for query in queries:
            if entries[query] is None:
                missing.setdefault(term_key(query), query)
        if missing:
            with ThreadPoolExecutor(max_workers=min(len(missing), 6)) as pool:
                fresh = list(pool.map(self._ask, missing.values()))
            for entry in fresh:
                self._remember(entry)
            by_key = {term_key(entry["query"]): entry for entry in fresh}
            for query in queries:
                if entries[query] is None:
                    entries[query] = {**by_key[term_key(query)], "query": query}
        return [dict(entries[query]) for query in queries]

    def looking(self) -> list[str]:
        """The queries being looked up at this moment. Safe to call from any thread."""
        with self._lock:
            return list(self._looking)

    def _ask(self, query: str) -> dict:
        """Ask the researcher. Runs on a worker thread, so it stays away from the database."""
        with self._lock:
            self._looking.append(query)
        try:
            lookup = self.researcher.look_up(query)
        except Exception as error:
            return {**_entry(Lookup(query, False)), "status": "failed", "error": _one_line(error)}
        finally:
            with self._lock:
                self._looking.remove(query)
        return _entry(lookup)

    def _remembered(self, query: str) -> dict | None:
        row = self.conn.execute(
            "SELECT name, definition, sources, origin FROM lookups WHERE key = ?",
            (term_key(query),)).fetchone()
        if row is None:
            return None
        return {"query": query, "status": "found", "name": row[0], "definition": row[1],
                "sources": json.loads(row[2]), "origin": row[3], "planned": False, "cached": True}

    def _remember(self, entry: dict) -> None:
        """Store a found lookup under its query and under its name."""
        if entry["status"] != "found":
            return
        now = datetime.now(timezone.utc).isoformat()
        for key in {term_key(entry["query"]), term_key(entry["name"])} - {""}:
            self.conn.execute(
                "INSERT OR REPLACE INTO lookups (key, query, name, definition, sources, origin, looked_up_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key, entry["query"], entry["name"], entry["definition"],
                 json.dumps(entry["sources"]), entry["origin"], now))
        self.conn.commit()


def _entry(lookup: Lookup) -> dict:
    """A lookup as a research entry."""
    return {"query": lookup.query, "status": "found" if lookup.found else "not_found",
            "name": lookup.name, "definition": lookup.definition, "sources": list(lookup.sources),
            "origin": lookup.origin, "planned": False, "cached": False}


def as_lookup(entry: dict) -> dict:
    """A research entry as a lookup dict, the shape `validate_brief` and the model read."""
    return {"query": entry["query"], "found": entry["status"] == "found", "name": entry["name"],
            "definition": entry["definition"], "sources": entry["sources"], "origin": entry["origin"]}


PLANNER = Path(__file__).with_name("planner.md")

PLAN_RESEARCH = ToolSpec(
    name="plan_research",
    description="List the standard terms and methods worth reading up on before the interview starts.",
    input_schema={"type": "object",
                  "properties": {"terms": {"type": "array", "items": {"type": "string"}}},
                  "required": ["terms"]})


def plan_research(model, desk: ResearchDesk, opening: str, say=print) -> list[dict]:
    """Read up on the terms the person's request depends on, before the first question (SPEC 4.6).

    One model call picks the terms; the desk looks them all up at once.
    Returns their research entries, marked as planned. A model that names
    no terms, or cannot be reached, gives an empty plan.
    """
    try:
        response = model.complete(system=PLANNER.read_text(encoding="utf-8"),
                                  messages=[{"role": "user", "content": opening}],
                                  tools=(PLAN_RESEARCH,))
    except Exception:
        return []       # the interview goes ahead without a plan
    wanted = next((call.arguments.get("terms") for call in response.tool_calls
                   if call.name == "plan_research"), None)
    terms = {}          # key -> term, in the order given
    for term in wanted if isinstance(wanted, list) else []:
        term = term.strip() if isinstance(term, str) else ""
        if term and len(term) <= MAX_QUERY_LENGTH:
            terms.setdefault(term_key(term), term)
    terms = list(terms.values())[:MAX_PLANNED]
    if not terms:
        return []
    say(f"  (reading up on: {', '.join(terms)})")
    return [{**entry, "planned": True} for entry in desk.look_up_many(terms)]
