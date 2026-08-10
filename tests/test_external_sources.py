from email.message import Message

from paranoia_local import external_sources as es


def candidate(url="https://docs.example.com/page", kind="primary"):
    return es.CandidateSource(url, "Docs", "Example", kind, "Example defines it", "supports_claim")


def test_known_ugc_is_mechanically_demoted():
    got = es.normalize_candidate(candidate("https://www.reddit.com/r/x", "primary"))
    assert got.source_kind == "ugc"
    assert not es.structurally_governing(got)


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
    assert seen["timeout"] == es.CONNECT_TIMEOUT_SEC + es.READ_TIMEOUT_SEC


def test_oversized_response_is_visible_non_governing(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda _url: None)
    body = b"x" * (es.MAX_RESPONSE_BYTES + 1)
    got = es.capture(candidate(), opener=lambda _request, _timeout: Response(body, "text/plain"))
    assert not got.usable
    assert "exceeds" in got.error
