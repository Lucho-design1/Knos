"""Evidence must be a STATIC page: every referee host fetches it itself and signs the sha256 of exactly its bytes, so a
page whose bytes change between loads (an echo service such as httpbin.org/anything, which writes the request's own
headers into the page) gives every host another digest and can never be released. The server fetches twice and refuses
such a page up front, with a message that says what to use instead."""
import itertools

import pytest

from knos_wanted import preorder, valley

CLAIM = "knos-idea:" + "a" * 32
REC = {"claim_id": CLAIM}


def test_a_page_that_changes_on_every_load_is_refused_with_a_clear_message():
    n = itertools.count()
    echo = lambda url: f'{{"url": "{url}", "headers": {{"X-Amzn-Trace-Id": "Root=1-{next(n)}"}}, "claim": "{CLAIM}"}}'.encode()  # noqa: E731
    with pytest.raises(preorder.NotVerified, match="changes on every load.*static page"):
        preorder.static_evidence("https://httpbin.org/anything/" + CLAIM, echo)
    calls = []
    page = lambda url: calls.append(url) or f"<p>result for {CLAIM}</p>".encode()  # noqa: E731
    assert preorder.static_evidence("https://gist.githubusercontent.com/x/y/raw/m.txt", page) == f"<p>result for {CLAIM}</p>".encode()
    assert len(calls) == 2


def test_verify_fetches_twice_and_refuses_an_echo_page(monkeypatch):
    n = itertools.count()
    monkeypatch.setattr(preorder, "fetch_evidence", lambda url, opener=None, resolve=None: f"{CLAIM} trace {next(n)}".encode())
    with pytest.raises(preorder.NotVerified, match="changes on every load"):
        preorder.verify(REC, "https://httpbin.org/anything/" + CLAIM)
    monkeypatch.setattr(preorder, "fetch_evidence", lambda url, opener=None, resolve=None: f"{CLAIM} measured".encode())
    ev, body = preorder.verify(REC, "https://example.org/result")
    assert ev["contains_claim_id"] and body == f"{CLAIM} measured".encode()


def test_a_project_attempt_refuses_an_echo_page_too():
    import inspect
    assert "preorder.static_evidence(url, fetch)" in inspect.getsource(valley.post)        # the same check before a result is kept
