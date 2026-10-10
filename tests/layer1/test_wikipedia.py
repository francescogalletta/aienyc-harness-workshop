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
    FakeFetch(page(fullurl="")),                                # a source needs an address
    FakeFetch(),                                                # the search found no page
])
def test_anything_else_is_not_found(fetch):
    assert WikipediaResearcher(fetch=fetch).look_up("zzz") == Lookup("zzz", False, origin="wikipedia")


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
