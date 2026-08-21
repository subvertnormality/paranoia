from email.message import Message
import hashlib
import threading
import time
import urllib.error

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

    def __init__(self, body: bytes, content_type="text/html", *, url=None):
        self.body = body
        self.url = url or "https://docs.example.com/page"
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

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
    assert got.final_url == "https://docs.example.com/page"
    assert got.status == 200
    assert got.content_type == "text/plain"
    assert got.content_sha256 == hashlib.sha256(body).hexdigest()
    assert got.text_sha256 is None


def test_extraction_failure_retains_known_response_provenance(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    body = b"   \n\t"
    got = es.capture(candidate(), opener=lambda _request, _timeout: Response(body))
    assert not got.usable
    assert got.final_url == "https://docs.example.com/page"
    assert got.status == 200
    assert got.content_type == "text/html"
    assert got.content_sha256 == hashlib.sha256(body).hexdigest()
    assert got.text_sha256 is None
    assert "no text" in got.error


def test_rejected_final_url_retains_actual_destination_and_headers(monkeypatch):
    original = candidate("https://official.example/redirect")
    rejected = "http://127.0.0.1/private"

    def validate(url):
        if url == original.url:
            return
        raise es.SourceError("non-public final address")

    monkeypatch.setattr(es, "_validate_public_url", validate)
    got = es.capture(
        original,
        opener=lambda _request, _timeout: Response(
            b"must not be read", "text/plain", url=rejected,
        ),
    )
    assert not got.usable
    assert got.final_url == rejected
    assert got.status == 200
    assert got.content_type == "text/plain"
    assert got.content_sha256 is None
    assert got.text_sha256 is None
    assert "non-public final address" in got.error


def test_default_redirect_handler_retains_rejected_target_and_response_metadata(
    monkeypatch,
):
    original = candidate("https://official.example/redirect")
    rejected = "http://127.0.0.1/private"
    redirect_headers = Message()
    redirect_headers["Content-Type"] = "text/plain; charset=utf-8"

    def validate(url):
        if url == original.url:
            return
        raise es.SourceError("source host resolves to non-public address 127.0.0.1")

    class Opener:
        def __init__(self, handler):
            self.handler = handler

        def open(self, request, timeout):
            return self.handler.redirect_request(
                request, None, 302, "Found", redirect_headers, rejected,
            )

    monkeypatch.setattr(es, "_validate_public_url", validate)
    monkeypatch.setattr(
        es.urllib.request, "build_opener", lambda handler: Opener(handler),
    )
    got = es.capture(original)
    assert not got.usable
    assert got.final_url == rejected
    assert got.status == 302
    assert got.content_type == "text/plain"
    assert got.content_sha256 is None
    assert got.text_sha256 is None
    assert "non-public address 127.0.0.1" in got.error


def test_raw_response_reader_admits_exact_byte_boundary():
    body = b"x" * es.MAX_RESPONSE_BYTES
    got = es._read_body(Response(body), deadline=1.0, clock=lambda: 0.0)
    assert len(got) == es.MAX_RESPONSE_BYTES


def test_large_extracted_page_keeps_deep_evidence(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    passage = "The governing behavior is stated near the end."
    body = (("x" * 70_000) + "\n" + passage).encode()
    got = es.capture(candidate(), opener=lambda _request, _timeout: Response(body, "text/plain"))
    assert got.usable
    assert len(got.text) > 40_000
    assert es.passage_matches(passage, got.text)


def test_extracted_character_cap_admits_boundary_and_rejects_next_character():
    assert len(es._extract(b"x" * es.MAX_EXTRACTED_CHARS, "text/plain")) == 1_000_000
    with pytest.raises(es.SourceError, match="extracted page has 1000001 characters"):
        es._extract(b"x" * (es.MAX_EXTRACTED_CHARS + 1), "text/plain")


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    headers = Message()
    headers["Content-Type"] = "text/html"
    return urllib.error.HTTPError(url, code, "Forbidden", headers, None)


def test_capture_sends_compatible_headers_and_retries_403_once(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    requests = []

    def opener(request, _timeout):
        requests.append(request)
        if len(requests) == 1:
            raise _http_error("https://docs.example.com/blocked", 403)
        return Response(b"Authoritative text", "text/plain", url="https://docs.example.com/final")

    got = es.capture(candidate(), opener=opener)
    assert got.usable
    assert got.fallback_attempted
    assert got.final_url == "https://docs.example.com/final"
    assert len(requests) == 2
    assert requests[0].get_header("User-agent") == es.BASE_REQUEST_HEADERS["User-Agent"]
    assert requests[1].get_header("User-agent") == es.BROWSER_USER_AGENT
    for name in ("Accept", "Accept-language", "Accept-encoding"):
        assert requests[0].get_header(name) == requests[1].get_header(name)


def test_persistent_403_retains_status_url_and_retry_provenance(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    calls = []

    def opener(request, _timeout):
        calls.append(request)
        raise _http_error("https://docs.example.com/forbidden", 403)

    got = es.capture(candidate(), opener=opener)
    assert not got.usable
    assert got.final_url == "https://docs.example.com/forbidden"
    assert got.status == 403
    assert got.fallback_attempted
    assert "browser-compatible retry attempted" in got.error
    assert len(calls) == 2


def test_non_403_http_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    calls = []

    def opener(request, _timeout):
        calls.append(request)
        raise _http_error("https://docs.example.com/missing", 404)

    got = es.capture(candidate(), opener=opener)
    assert got.status == 404
    assert not got.fallback_attempted
    assert len(calls) == 1


def test_403_retry_does_not_reset_or_outlive_deadline(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    now = [0.0]
    calls = []

    def opener(request, _timeout):
        calls.append(request)
        now[0] = 5.0
        raise _http_error("https://docs.example.com/forbidden", 403)

    got = es.capture(candidate(), opener=opener, deadline=5.0, clock=lambda: now[0])
    assert got.status == 403
    assert not got.fallback_attempted
    assert "deadline expired" in got.error
    assert len(calls) == 1


def test_default_403_retry_uses_fresh_redirect_handler(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    handlers = []

    class Opener:
        def __init__(self, handler):
            self.handler = handler

        def open(self, _request, *, timeout):
            assert timeout > 0
            if len(handlers) == 1:
                raise _http_error("https://docs.example.com/forbidden", 403)
            return Response(b"Authoritative text", "text/plain")

    def build_opener(handler):
        handlers.append(handler)
        return Opener(handler)

    monkeypatch.setattr(es.urllib.request, "build_opener", build_opener)
    got = es.capture(candidate())
    assert got.usable
    assert got.fallback_attempted
    assert len(handlers) == 2
    assert handlers[0] is not handlers[1]


def test_403_fallback_rejects_non_public_final_url(monkeypatch):
    def validate(url):
        if url == "http://127.0.0.1/private":
            raise es.SourceError("source host resolves to non-public address 127.0.0.1")

    monkeypatch.setattr(es, "_validate_public_url", validate)
    calls = []

    def opener(request, _timeout):
        calls.append(request)
        if len(calls) == 1:
            raise _http_error("https://docs.example.com/forbidden", 403)
        return Response(b"private", "text/plain", url="http://127.0.0.1/private")

    got = es.capture(candidate(), opener=opener)
    assert not got.usable
    assert got.fallback_attempted
    assert "non-public address" in got.error
    assert len(calls) == 2


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
