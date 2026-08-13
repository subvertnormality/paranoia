from email.message import Message
import threading
import time

import pytest

from paranoia_local import external_sources as es


def candidate(url="https://docs.example.com/page", kind="primary"):
    return es.CandidateSource(url, "Docs", "Example", kind, "Example defines it", "supports_claim")


def test_parallel_capture_failure_retains_completed_sibling():
    first = candidate("https://docs.example.com/first")
    second = candidate("https://docs.example.com/second")
    completed = threading.Event()

    def capture_one(item):
        if item is second:
            assert completed.wait(2)
            raise RuntimeError("second capture exploded")
        result = es.Capture(
            item, item.url, 200, "text/html", "a" * 64, "b" * 64, "captured text",
        )
        completed.set()
        return result

    with pytest.raises(es.CaptureGroupError) as caught:
        es.capture_all([first, second], capture_one=capture_one, workers=2)
    assert [item.candidate.url for item in caught.value.completed] == [first.url]


def test_parallel_capture_failure_waits_for_running_sibling_record():
    first = candidate("https://docs.example.com/first")
    second = candidate("https://docs.example.com/second")
    sibling_started = threading.Event()
    failed = threading.Event()

    def capture_one(item):
        if item is first:
            assert sibling_started.wait(2)
            failed.set()
            raise RuntimeError("first capture exploded")
        sibling_started.set()
        assert failed.wait(2)
        time.sleep(0.05)
        return es.Capture(
            item, item.url, 200, "text/html", "a" * 64, "b" * 64, "captured text",
        )

    with pytest.raises(es.CaptureGroupError) as caught:
        es.capture_all([first, second], capture_one=capture_one, workers=2)
    assert [item.candidate.url for item in caught.value.completed] == [second.url]


def test_known_ugc_is_mechanically_demoted():
    got = es.normalize_candidate(candidate("https://www.reddit.com/r/x", "primary"))
    assert got.source_kind == "ugc"
    assert not es.structurally_governing(got)


def test_redirect_to_ugc_cannot_make_a_bound_source_governing():
    original = candidate("https://official.example/redirect", "primary")
    capture = es.Capture(
        original, "https://www.reddit.com/r/example", 200, "text/html",
        "a" * 64, "b" * 64, "A matching passage.",
    )
    bound = es.BoundSource(original, capture, "post", "A matching passage.")
    assert not bound.governing


def test_exact_passage_matching_is_unicode_and_whitespace_conservative():
    assert es.passage_matches("Café supports  this", "Heading\nCafe\u0301 supports this.\n")
    assert not es.passage_matches("café refutes this", "Cafe\u0301 supports this.")


class Response:
    status = 200

    def __init__(self, body: bytes, content_type="text/html"):
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return "https://docs.example.com/page"

    def read(self, size):
        return self.body[:size]


def test_server_capture_uses_trafilatura_and_records_digests(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    body = b"<html><body><main><h1>Rule</h1><p>The API retries twice.</p></main></body></html>"
    got = es.capture(candidate(), opener=lambda _request, _timeout: Response(body))
    assert got.usable
    assert "The API retries twice." in got.text
    assert got.content_sha256 and got.text_sha256


def test_default_urllib_opener_receives_timeout_as_keyword(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    seen = {}

    class Opener:
        def open(self, request, *, timeout):
            seen["timeout"] = timeout
            return Response(b"Authoritative plain text", "text/plain")

    monkeypatch.setattr(es.urllib.request, "build_opener", lambda handler: Opener())
    got = es.capture(candidate())
    assert got.usable
    assert 0 < seen["timeout"] <= es.CONNECT_TIMEOUT_SEC + es.READ_TIMEOUT_SEC


def test_oversized_response_is_visible_non_governing(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    body = b"x" * (es.MAX_RESPONSE_BYTES + 1)
    got = es.capture(candidate(), opener=lambda _request, _timeout: Response(body, "text/plain"))
    assert not got.usable
    assert "exceeds" in got.error


def test_slow_stream_cannot_outlive_capture_deadline(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    now = [0.0]

    class SlowResponse(Response):
        def read1(self, _size):
            now[0] += 3.0
            return b"x"

    got = es.capture(
        candidate(), opener=lambda _request, _timeout: SlowResponse(b"", "text/plain"),
        deadline=5.0, clock=lambda: now[0],
    )
    assert not got.usable
    assert "deadline expired" in got.error
