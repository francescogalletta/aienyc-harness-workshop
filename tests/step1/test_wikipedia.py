"""SPEC 4.6: the Wikipedia researcher and the chain. No test here reaches the web."""
import json
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from harness.grounding import ChainResearcher, Lookup, WikipediaResearcher

EXTRACT = ("A sinking fund is a fund established by an economic entity by setting aside revenue over a "
           "period of time. It funds a future capital expense, or the repayment of a long-term debt.\n"
           "In North America it is used for bonds! Is it common? Yes.")


class FakeFetch:
    def __init__(self, page=None, body=None):
        pages = {"1234": page} if page is not None else None
        self.body = body if body is not None else json.dumps(
            {"batchcomplete": "", "query": {"pages": pages}} if pages else {"batchcomplete": ""})
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return self.body


def page(**changes):
    return {"pageid": 1234, "title": "Sinking fund", "extract": EXTRACT,
            "fullurl": "https://en.wikipedia.org/wiki/Sinking_fund", **changes}


def test_a_page_with_an_extract_is_found():
    lookup = WikipediaResearcher(fetch=FakeFetch(page())).look_up("sinking fund")
    assert lookup == Lookup(
        query="sinking fund", found=True, name="Sinking fund",
        definition=("A sinking fund is a fund established by an economic entity by setting aside revenue over "
                    "a period of time. It funds a future capital expense, or the repayment of a long-term "
                    "debt. In North America it is used for bonds!"),
        sources=({"title": "Sinking fund (Wikipedia)", "url": "https://en.wikipedia.org/wiki/Sinking_fund"},),
        origin="wikipedia")


def test_a_long_definition_is_cut_at_500_characters():
    lookup = WikipediaResearcher(fetch=FakeFetch(page(extract="word " * 300))).look_up("word")
    assert lookup.found and len(lookup.definition) == 500


def test_only_the_query_is_sent():
    """Ground rule 6: one request, and nothing in it but the term."""
    fetch = FakeFetch(page())
    WikipediaResearcher(fetch=fetch).look_up("pay yourself first & save 10%?")
    encoded = quote("pay yourself first & save 10%?", safe="")
    assert encoded == "pay%20yourself%20first%20%26%20save%2010%25%3F"
    assert fetch.urls == [
        "https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&generator=search"
        f"&gsrlimit=1&gsrsearch={encoded}&prop=extracts|info|pageprops&exintro=1&explaintext=1"
        "&inprop=url&ppprop=disambiguation"]
    sent = parse_qs(urlsplit(fetch.urls[0]).query)
    assert sent["gsrsearch"] == ["pay yourself first & save 10%?"]
    assert sorted(sent) == ["action", "exintro", "explaintext", "format", "generator", "gsrlimit",
                            "gsrsearch", "inprop", "ppprop", "prop", "redirects"]


@pytest.mark.parametrize("fetch", [
    FakeFetch(page(pageprops={"disambiguation": ""})),          # a list of meanings is not a definition
    FakeFetch(page(extract="")),
    FakeFetch(page(extract="   \n")),
    FakeFetch({"pageid": 1, "title": "No text"}),
    FakeFetch(page(fullurl="")),                                # a source needs an address
    FakeFetch(),                                                # the search found no page
])
def test_anything_else_is_not_found(fetch):
    assert WikipediaResearcher(fetch=fetch).look_up("zzz") == Lookup("zzz", False, origin="wikipedia")


def test_pageprops_without_disambiguation_do_not_matter():
    assert WikipediaResearcher(fetch=FakeFetch(page(pageprops={"wikibase_item": "Q1"}))).look_up("x").found


def test_a_request_that_fails_raises():
    def offline(url):
        raise OSError("network is unreachable")

    with pytest.raises(OSError):
        WikipediaResearcher(fetch=offline).look_up("sinking fund")
    with pytest.raises(ValueError):
        WikipediaResearcher(fetch=FakeFetch(body="<html>not json</html>")).look_up("sinking fund")


def test_the_default_fetch_is_a_plain_request_with_a_user_agent(monkeypatch):
    import harness.grounding.research as research
    seen = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({"query": {"pages": {"1": page()}}}).encode("utf-8")

    def urlopen(request, timeout):
        seen.update(url=request.full_url, agent=request.get_header("User-agent"), timeout=timeout)
        return Reply()

    monkeypatch.setattr(research.urllib.request, "urlopen", urlopen)
    assert WikipediaResearcher().look_up("sinking fund").found
    assert seen["agent"] == "finance-harness-workshop/0.1 (local research tool)"
    assert seen["timeout"] == 15 and "gsrsearch=sinking%20fund&" in seen["url"]


class Fixed:
    def __init__(self, answer):
        self.answer, self.queries = answer, []

    def look_up(self, query):
        self.queries.append(query)
        if isinstance(self.answer, Exception):
            raise self.answer
        return Lookup(query, self.answer, name="Name" if self.answer else "", origin="fixed")


def test_the_chain_returns_the_first_lookup_that_is_found():
    first, second, third = Fixed(False), Fixed(True), Fixed(True)
    lookup = ChainResearcher([first, second, third]).look_up("a term")
    assert lookup.found and lookup.origin == "fixed"
    assert (first.queries, second.queries, third.queries) == (["a term"], ["a term"], [])


def test_the_chain_skips_a_researcher_that_raises():
    assert ChainResearcher([Fixed(RuntimeError("down")), Fixed(True)]).look_up("a term").found
    # One of them answered, so this is "not found", not a failure.
    assert ChainResearcher([Fixed(False), Fixed(RuntimeError("down"))]).look_up("x") == Lookup("x", False)
    assert ChainResearcher([Fixed(RuntimeError("down")), Fixed(False)]).look_up("x") == Lookup("x", False)
    assert ChainResearcher([Fixed(False), Fixed(False)]).look_up("x") == Lookup("x", False)


def test_the_chain_fails_only_when_every_researcher_failed():
    chain = ChainResearcher([Fixed(RuntimeError("first reason")), Fixed(OSError("last\nreason"))])
    with pytest.raises(RuntimeError, match="^last reason$"):
        chain.look_up("x")
