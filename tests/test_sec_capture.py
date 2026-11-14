"""SEC header policy at capture's actual request/redirect boundary."""

from dataclasses import asdict
from email.message import Message
import json
import urllib.request

import pytest

from paranoia_local import external_sources as es
from .test_external_sources import Response, candidate, _http_error


IDENTITY = "ResearchTool alice+research@example.com"


@pytest.fixture(autouse=True)
def public_urls(monkeypatch):
    monkeypatch.setattr(es, "_validate_public_url", lambda url: None)


@pytest.mark.parametrize("url", ["https://sec.gov/a", "https://www.sec.gov/a",
                                "https://data.sec.gov/a", "https://WWW.SEC.GOV./a"])
def test_configured_identity_only_on_sec_hosts(monkeypatch, url):
    monkeypatch.setenv(es.SEC_USER_AGENT_ENV, IDENTITY)
    requests = []
    def open_call(request, timeout):
        requests.append(request)
        return Response(b"Official source text", "text/plain", url=url)
    captured = es.capture(candidate(url), opener=open_call)
    assert captured.usable and captured.status == 200
    assert requests[0].get_header("User-agent") == IDENTITY
    assert IDENTITY not in json.dumps(asdict(captured))


@pytest.mark.parametrize("url", ["https://sec.gov.evil.example/a", "https://notsec.gov/a",
                                "https://evilsec.gov/a", "https://sec-gov.example/a"])
def test_lookalikes_never_receive_identity(monkeypatch, url):
    monkeypatch.setenv(es.SEC_USER_AGENT_ENV, IDENTITY)
    calls = []
    def open_call(request, timeout):
        calls.append(request.get_header("User-agent"))
        if len(calls) == 1:
            raise _http_error(url, 403)
        return Response(b"Source text", "text/plain", url=url)
    assert es.capture(candidate(url), opener=open_call).usable
    assert calls == [es.BASE_REQUEST_HEADERS["User-Agent"], es.BROWSER_USER_AGENT]


@pytest.mark.parametrize("value", ["", "No contact", "a@localhost", "a@-example.com",
    "a@example-.com", "a..b@example.com", "a@example.comb@example.org",
    "Tool a@example.com\r\nInjected: yes", "Tool a@example.com\t", "Tool a@example.com\x7f",
    "Töol a@example.com", "x" * 493 + " a@example.commmmmmmmmm"])
def test_invalid_identity_is_value_free_and_never_dispatched(monkeypatch, value):
    monkeypatch.setenv(es.SEC_USER_AGENT_ENV, value)
    calls = []
    def open_call(request, timeout):
        calls.append(request.full_url)
        return Response(b"Source text", "text/plain", url=request.full_url)
    sec, other = es.capture_all([candidate("https://sec.gov/a"), candidate()],
        capture_one=lambda c: es.capture(c, opener=open_call))
    assert not sec.usable and sec.error == es.SEC_USER_AGENT_ERROR
    assert other.usable and calls == [other.candidate.url]
    assert sec.status is None and sec.text is None and not sec.fallback_attempted


@pytest.mark.parametrize("contact", ["alice+research@example.com", "<a.b@example.org>",
                                    "(a@sub.example.co.uk)"])
def test_practical_email_tokens_and_exact_length_boundary(monkeypatch, contact):
    value = "x" * (511 - len(contact)) + " " + contact
    assert len(value) == 512
    monkeypatch.setenv(es.SEC_USER_AGENT_ENV, value)
    def open_call(request, timeout):
        assert request.get_header("User-agent") == value
        return Response(b"Source text", "text/plain", url=request.full_url)
    assert es.capture(candidate("https://sec.gov/a"), opener=open_call).usable
    monkeypatch.setenv(es.SEC_USER_AGENT_ENV, "x" + value)
    got = es.capture(candidate("https://sec.gov/a"), opener=lambda *a: pytest.fail("dispatch"))
    assert not got.usable and got.error == es.SEC_USER_AGENT_ERROR


@pytest.mark.parametrize("browser", [False, True])
@pytest.mark.parametrize("configured", [False, True])
def test_redirects_replace_identity_in_both_directions(monkeypatch, browser, configured):
    identity = IDENTITY if configured else None
    base = es.BROWSER_USER_AGENT if browser else es.BASE_REQUEST_HEADERS["User-Agent"]
    handler = es._SafeRedirect(browser_compatible=browser, sec_user_agent=identity)
    request = urllib.request.Request("https://outside.example/a", headers={"User-Agent": base})
    for target, expected in [("https://www.sec.gov./b", identity or base),
                             ("https://data.sec.gov/c", identity or base),
                             ("https://sec.gov.evil.example/d", base)]:
        request = handler.redirect_request(request, None, 302, "Found", Message(), target)
        assert request.get_header("User-agent") == expected
        assert [k.lower() for k, v in request.header_items()].count("user-agent") == 1


def test_invalid_sec_redirect_stops_after_public_address_guard(monkeypatch):
    checked = []
    monkeypatch.setattr(es, "_validate_public_url", checked.append)
    handler = es._SafeRedirect(sec_user_agent="private invalid identity")
    with pytest.raises(es.RedirectRejected) as caught:
        handler.redirect_request(urllib.request.Request("https://outside.example/a"),
                                 None, 302, "Found", Message(), "https://sec.gov/b")
    assert checked == ["https://sec.gov/b"]
    assert str(caught.value) == "rejected final URL: " + es.SEC_USER_AGENT_ERROR
    assert caught.value.target == "https://sec.gov/b" and caught.value.status == 302


@pytest.mark.parametrize("persistent", [False, True])
def test_identity_frozen_across_redirects_and_retry(monkeypatch, persistent):
    monkeypatch.setenv(es.SEC_USER_AGENT_ENV, IDENTITY)
    handlers, requests = [], []
    class Opener:
        def __init__(self, handler):
            self.handler = handler
        def open(self, request, *, timeout):
            assert timeout > 0 and self.handler.count == 0
            assert request.get_header("User-agent") == IDENTITY
            monkeypatch.setenv(es.SEC_USER_AGENT_ENV, "Changed person changed@example.org")
            request = self.handler.redirect_request(request, None, 302, "Found", Message(),
                                                    "https://outside.example/a")
            expected = es.BROWSER_USER_AGENT if len(handlers) == 2 else es.BASE_REQUEST_HEADERS["User-Agent"]
            assert request.get_header("User-agent") == expected
            request = self.handler.redirect_request(request, None, 302, "Found", Message(),
                                                    "https://data.sec.gov/final")
            assert request.get_header("User-agent") == IDENTITY
            requests.append(request)
            if len(requests) == 1 or persistent:
                raise _http_error(request.full_url, 403)
            return Response(b"Official text", "text/plain", url=request.full_url)
    def build(handler):
        handlers.append(handler)
        return Opener(handler)
    monkeypatch.setattr(es.urllib.request, "build_opener", build)
    got = es.capture(candidate("https://sec.gov/start"))
    assert got.fallback_attempted and len(requests) == len(handlers) == 2
    assert handlers[0] is not handlers[1]
    assert got.usable is (not persistent)
    if persistent:
        assert got.status == 403 and "configured SEC identity retry attempted" in got.error
        assert "browser-compatible" not in got.error
    assert IDENTITY not in json.dumps(asdict(got))
    assert "changed@example.org" not in json.dumps(asdict(got))


def test_configured_retry_keeps_absolute_deadline(monkeypatch):
    monkeypatch.setenv(es.SEC_USER_AGENT_ENV, IDENTITY)
    now, calls = [0.0], []
    def open_call(request, timeout):
        calls.append(timeout)
        now[0] = 5.0
        raise _http_error(request.full_url, 403)
    got = es.capture(candidate("https://sec.gov/a"), opener=open_call,
                     deadline=5.0, clock=lambda: now[0])
    assert calls == [5.0] and got.status == 403 and not got.fallback_attempted
    assert "configured SEC identity retry not attempted" in got.error
    assert "deadline expired" in got.error and IDENTITY not in got.error


def test_unset_sec_identity_keeps_generic_browser_retry(monkeypatch):
    monkeypatch.delenv(es.SEC_USER_AGENT_ENV, raising=False)
    calls = []
    def open_call(request, timeout):
        calls.append(request.get_header("User-agent"))
        raise _http_error(request.full_url, 403)
    got = es.capture(candidate("https://sec.gov/a"), opener=open_call)
    assert calls == [es.BASE_REQUEST_HEADERS["User-Agent"], es.BROWSER_USER_AGENT]
    assert got.status == 403 and "browser-compatible retry attempted" in got.error
