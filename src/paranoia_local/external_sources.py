"""Shared source policy and server-controlled web capture.

Provider search discovers URLs.  Only bytes downloaded and extracted here may become
governing evidence; provider summaries and WebFetch output never do.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse

import trafilatura


SOURCE_KINDS = frozenset({"primary", "authoritative", "secondary", "ugc"})
AUTHORITATIVE_KINDS = frozenset({"primary", "authoritative"})
RELATIONS = frozenset({"supports_claim", "refutes_claim", "supports_replacement", "context"})
UGC_HOSTS = (
    "reddit.com", "quora.com", "stackoverflow.com", "stackexchange.com",
    "medium.com", "substack.com", "x.com", "twitter.com", "facebook.com",
    "instagram.com", "tiktok.com", "youtube.com", "wikipedia.org",
)

MAX_RESPONSE_BYTES = 5_000_000
MAX_EXTRACTED_CHARS = 1_000_000
CONNECT_TIMEOUT_SEC = 20
READ_TIMEOUT_SEC = 40
MAX_REDIRECTS = 5
READ_CHUNK_BYTES = 64 * 1024
BASE_REQUEST_HEADERS = {
    "User-Agent": "paranoia-local/0.1 evidence-capture",
    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
    "Accept-Language": "en-US,en;q=0.8",
    "Accept-Encoding": "identity",
}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)
MAX_CAPTURE_ERROR_CHARS = 1200
BINDING_BUDGET_ERROR = (
    "capture excluded from binding input because its serialized captured text exceeds "
    "the available binding budget"
)


class SourceError(ValueError):
    pass


class RedirectRejected(SourceError):
    """A redirect response whose computed target cannot be followed safely."""

    def __init__(
        self, target: str, status: int, content_type: str | None, reason: str,
    ) -> None:
        super().__init__(f"rejected final URL: {reason}")
        self.target = target
        self.status = status
        self.content_type = content_type


class CaptureGroupError(RuntimeError):
    """A capture task failed unexpectedly after zero or more siblings completed."""

    def __init__(self, message: str, completed: tuple["Capture", ...]):
        super().__init__(message)
        self.completed = completed


@dataclass(frozen=True)
class CandidateSource:
    url: str
    title: str
    publisher: str
    source_kind: str
    authority_basis: str
    relation: str


@dataclass(frozen=True)
class Capture:
    candidate: CandidateSource
    final_url: str | None
    status: int | None
    content_type: str | None
    content_sha256: str | None
    text_sha256: str | None
    text: str | None
    error: str | None = None
    fallback_attempted: bool = False

    @property
    def usable(self) -> bool:
        return self.error is None and bool(self.text)


@dataclass(frozen=True)
class BoundSource:
    candidate: CandidateSource
    capture: Capture
    location: str
    passage: str

    @property
    def governing(self) -> bool:
        effective = replace(
            self.candidate, url=self.capture.final_url or self.candidate.url,
        )
        return structurally_governing(effective) and self.capture.usable


def is_ugc_host(host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == suffix or host.endswith("." + suffix) for suffix in UGC_HOSTS)


def normalize_candidate(candidate: CandidateSource) -> CandidateSource:
    parsed = urlparse(candidate.url)
    host = (parsed.hostname or "").lower().rstrip(".")
    kind = candidate.source_kind
    relation = candidate.relation
    if kind not in SOURCE_KINDS:
        raise SourceError(f"unknown source kind: {kind!r}")
    if relation not in RELATIONS:
        raise SourceError(f"unknown source relation: {relation!r}")
    if parsed.scheme not in {"http", "https"} or not host:
        relation = "context"
    if is_ugc_host(host):
        kind = "ugc"
    return replace(candidate, source_kind=kind, relation=relation)


def structurally_governing(candidate: CandidateSource) -> bool:
    candidate = normalize_candidate(candidate)
    parsed = urlparse(candidate.url)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and candidate.source_kind in AUTHORITATIVE_KINDS
        and candidate.relation in {"supports_claim", "refutes_claim", "supports_replacement"}
    )


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def passage_matches(passage: str, captured_text: str) -> bool:
    needle = normalize_text(passage)
    return bool(needle) and needle in normalize_text(captured_text)


def numbered_lines(lines: Iterable[str]) -> str:
    return "\n".join(f"{index:05d}: {line}" for index, line in enumerate(lines, 1))


def numbered_plan_lines(lines: Iterable[str]) -> str:
    """Render plan coordinates without a colon that can resemble line:column."""
    return "\n".join(
        f"[PLAN-LINE {index:05d}] {line}" for index, line in enumerate(lines, 1)
    )


def numbered_text(text: str) -> str:
    return numbered_lines(text.splitlines())


def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise SourceError("source URL must be public HTTP(S) without userinfo")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443)}
    except OSError as exc:
        raise SourceError(f"cannot resolve source host: {exc}") from exc
    if not addresses:
        raise SourceError("source host resolved to no addresses")
    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if not address.is_global:
            raise SourceError(f"source host resolves to non-public address {address}")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        self.count += 1
        target = urljoin(req.full_url, newurl)
        content_type = headers.get_content_type().lower() if headers else None
        if self.count > MAX_REDIRECTS:
            raise RedirectRejected(target, int(code), content_type, "too many redirects")
        try:
            _validate_public_url(target)
        except SourceError as exc:
            raise RedirectRejected(
                target, int(code), content_type, _bounded_error(exc),
            ) from exc
        return super().redirect_request(req, fp, code, msg, headers, target)


def _extract(body: bytes, content_type: str) -> str:
    if content_type.startswith("text/plain"):
        text = body.decode("utf-8", errors="replace")
    else:
        text = trafilatura.extract(
            body, output_format="txt", include_comments=False, include_tables=True,
            favor_precision=True,
        ) or ""
    text = text.strip()
    if not text:
        raise SourceError("page extraction produced no text")
    if len(text) > MAX_EXTRACTED_CHARS:
        raise SourceError(
            f"extracted page has {len(text)} characters; limit is {MAX_EXTRACTED_CHARS}"
        )
    return text


def _read_body(response: object, *, deadline: float, clock: Callable[[], float]) -> bytes:
    """Read a real urllib response in bounded chunks under one wall-clock deadline."""
    read1 = getattr(response, "read1", None)
    if not callable(read1):
        body = response.read(MAX_RESPONSE_BYTES + 1)  # type: ignore[attr-defined]
        if clock() > deadline:
            raise SourceError("source capture deadline expired while reading response")
        return body
    body = bytearray()
    while len(body) <= MAX_RESPONSE_BYTES:
        remaining = deadline - clock()
        if remaining <= 0:
            raise SourceError("source capture deadline expired while reading response")
        # HTTPResponse.read1 performs at most one buffered/raw read, so the deadline is
        # checked between chunks rather than being reset indefinitely by a trickle stream.
        chunk = read1(min(READ_CHUNK_BYTES, MAX_RESPONSE_BYTES + 1 - len(body)))
        if clock() > deadline:
            raise SourceError("source capture deadline expired while reading response")
        if not chunk:
            break
        body.extend(chunk)
    return bytes(body)


def _bounded_error(value: object) -> str:
    text = " ".join(str(value).split()) or type(value).__name__
    if len(text) <= MAX_CAPTURE_ERROR_CHARS:
        return text
    return text[: MAX_CAPTURE_ERROR_CHARS - 1] + "…"


def _http_error_capture(
    candidate: CandidateSource,
    error: urllib.error.HTTPError,
    *,
    fallback_attempted: bool,
    detail: str | None = None,
) -> Capture:
    final_url: str | None = None
    try:
        proposed = error.geturl()
        _validate_public_url(proposed)
        final_url = proposed
    except (SourceError, OSError, ValueError) as exc:
        detail = f"HTTP {error.code}; rejected final URL: {_bounded_error(exc)}"
    content_type = None
    if error.headers is not None:
        content_type = error.headers.get_content_type().lower()
    message = detail or _bounded_error(error)
    if fallback_attempted and error.code == 403:
        message = f"{message}; browser-compatible retry attempted"
    return Capture(
        candidate, final_url, int(error.code), content_type, None, None, None,
        _bounded_error(message), fallback_attempted,
    )


def capture(
    candidate: CandidateSource,
    *,
    opener: Callable[[urllib.request.Request, float], object] | None = None,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Capture:
    candidate = normalize_candidate(candidate)
    fallback_attempted = False
    final_url: str | None = None
    status: int | None = None
    content_type: str | None = None
    content_sha256: str | None = None
    text_sha256: str | None = None
    try:
        started = clock()
        capture_deadline = started + CONNECT_TIMEOUT_SEC + READ_TIMEOUT_SEC
        if deadline is not None:
            capture_deadline = min(capture_deadline, deadline)
        if capture_deadline <= started:
            raise SourceError("source capture deadline expired before request")
        _validate_public_url(candidate.url)
        remaining = capture_deadline - clock()
        if remaining <= 0:
            raise SourceError("source capture deadline expired before request")
        response = None
        first_403: urllib.error.HTTPError | None = None
        for browser_compatible in (False, True):
            remaining = capture_deadline - clock()
            if remaining <= 0:
                if browser_compatible and first_403 is not None:
                    return _http_error_capture(
                        candidate, first_403, fallback_attempted=False,
                        detail=(
                            "HTTP 403; browser-compatible retry not attempted because the "
                            "source capture deadline expired"
                        ),
                    )
                raise SourceError("source capture deadline expired before request")
            headers = dict(BASE_REQUEST_HEADERS)
            if browser_compatible:
                headers["User-Agent"] = BROWSER_USER_AGENT
                fallback_attempted = True
            request = urllib.request.Request(candidate.url, headers=headers)
            if opener is None:
                handler = _SafeRedirect()
                built_opener = urllib.request.build_opener(handler)

                def open_call(req: urllib.request.Request, timeout: float):
                    return built_opener.open(req, timeout=timeout)
            else:
                open_call = opener
            try:
                response = open_call(
                    request, min(CONNECT_TIMEOUT_SEC + READ_TIMEOUT_SEC, remaining),
                )
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 403 and not browser_compatible:
                    first_403 = exc
                    continue
                return _http_error_capture(
                    candidate, exc, fallback_attempted=fallback_attempted,
                )
        assert response is not None
        with response:  # type: ignore[attr-defined]
            final_url = response.geturl()
            status = int(getattr(response, "status", 200))
            content_type = response.headers.get_content_type().lower()
            _validate_public_url(final_url)
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise SourceError(f"unsupported content type {content_type!r}")
            body = _read_body(response, deadline=capture_deadline, clock=clock)
            content_sha256 = hashlib.sha256(body).hexdigest()
            if len(body) > MAX_RESPONSE_BYTES:
                raise SourceError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
        text = _extract(body, content_type)
        text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return Capture(
            candidate=candidate,
            final_url=final_url,
            status=status,
            content_type=content_type,
            content_sha256=content_sha256,
            text_sha256=text_sha256,
            text=text,
            fallback_attempted=fallback_attempted,
        )
    except RedirectRejected as exc:
        return Capture(
            candidate=candidate,
            final_url=exc.target,
            status=exc.status,
            content_type=exc.content_type,
            content_sha256=content_sha256,
            text_sha256=text_sha256,
            text=None,
            error=_bounded_error(exc),
            fallback_attempted=fallback_attempted,
        )
    except (SourceError, urllib.error.URLError, OSError, ValueError) as exc:
        return Capture(
            candidate=candidate,
            final_url=final_url,
            status=status,
            content_type=content_type,
            content_sha256=content_sha256,
            text_sha256=text_sha256,
            text=None,
            error=_bounded_error(exc),
            fallback_attempted=fallback_attempted,
        )


def capture_all(
    candidates: Iterable[CandidateSource],
    *,
    capture_one: Callable[[CandidateSource], Capture] = capture,
    workers: int = 4,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> list[Capture]:
    from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed

    rows = list(candidates)
    invoke = (
        (lambda candidate: capture(candidate, deadline=deadline, clock=clock))
        if capture_one is capture else capture_one
    )
    completed: dict[int, Capture] = {}
    failure: Exception | None = None
    with ThreadPoolExecutor(max_workers=min(workers, max(1, len(rows)))) as pool:
        futures = {pool.submit(invoke, row): index for index, row in enumerate(rows)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                completed[index] = future.result()
            except CancelledError:
                continue
            except Exception as exc:  # unexpected capture implementation failure
                if failure is None:
                    failure = exc
                    for pending in futures:
                        pending.cancel()
    ordered = tuple(completed[index] for index in sorted(completed))
    if failure is not None:
        raise CaptureGroupError(f"{type(failure).__name__}: {failure}", ordered) from failure
    return list(ordered)


def packet_id(proposition: str, source: BoundSource) -> str:
    body = "\0".join(
        [
            normalize_text(proposition), source.capture.final_url or source.candidate.url,
            source.capture.text_sha256 or "", normalize_text(source.passage),
            source.candidate.publisher, source.candidate.relation,
        ]
    )
    return "src-" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
