"""Server-owned bounded discovery and HTTPS retrieval for external evidence."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import string
import queue
import threading
import time
import urllib.parse
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Protocol, Sequence


class NetworkEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchLimits:
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    total_timeout: float = 30.0
    max_redirects: int = 5
    max_compressed_bytes: int = 1 << 20
    max_decompressed_bytes: int = 1 << 20


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: dict[str, str]
    chunks: Iterable[bytes]
    peer_ip: str


@dataclass(frozen=True)
class RawResponse:
    requested_url: str
    final_url: str
    retrieved_at: str
    status: int
    media_type: str
    body: bytes
    sha256: str
    size: int
    redirects: tuple[str, ...]


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str


class Transport(Protocol):
    def request(self, url: str, address: str, limits: FetchLimits,
                deadline: float, on_bytes: Callable[[int], None] | None = None
                ) -> TransportResponse: ...


Resolver = Callable[[str], Sequence[str]]


def system_resolver(host: str) -> list[str]:
    try:
        return sorted({row[4][0] for row in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})
    except OSError as exc:
        raise NetworkEvidenceError(f"DNS resolution failed for {host}: {exc}") from exc


def _public(address: str) -> bool:
    try:
        value = ipaddress.ip_address(address)
    except ValueError:
        return False
    return value.is_global and not (
        value.is_private or value.is_loopback or value.is_link_local
        or value.is_multicast or value.is_unspecified or value.is_reserved
    )


class HttpsTransport:
    """Connect to the selected IP while TLS authenticates the original hostname."""

    def request(self, url: str, address: str, limits: FetchLimits,
                deadline: float, on_bytes: Callable[[int], None] | None = None
                ) -> TransportResponse:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ""
        port = parsed.port or 443
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise NetworkEvidenceError("external request total deadline expired")
        timeout = min(limits.connect_timeout, remaining)
        raw: socket.socket | None = None
        wrapped: ssl.SSLSocket | None = None
        try:
            raw = socket.create_connection((address, port), timeout=timeout)
            context = ssl.create_default_context()
            wrapped = context.wrap_socket(raw, server_hostname=host)
            raw = None
            wrapped.settimeout(min(limits.read_timeout, max(0.1, deadline - time.monotonic())))
            path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            request = (
                f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: paranoia-local/0.1\r\n"
                "Accept: text/plain,text/html,application/json,application/xml;q=0.8\r\n"
                "Accept-Encoding: gzip,deflate\r\nConnection: close\r\n\r\n"
            ).encode("ascii")
            wrapped.sendall(request)
            response = http.client.HTTPResponse(wrapped)
            response.begin()
            headers = {key.lower(): value.strip() for key, value in response.getheaders()}
            chunks: list[bytes] = []
            total = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise NetworkEvidenceError("external request total deadline expired")
                wrapped.settimeout(min(limits.read_timeout, max(0.1, remaining)))
                chunk = response.read1(
                    min(65536, limits.max_compressed_bytes - total + 1)
                )
                if not chunk:
                    break
                total += len(chunk)
                if on_bytes is not None:
                    on_bytes(len(chunk))
                if total > limits.max_compressed_bytes:
                    raise NetworkEvidenceError("compressed response exceeds byte cap")
                chunks.append(chunk)
            peer = wrapped.getpeername()[0]
            return TransportResponse(response.status, headers, chunks, peer)
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise NetworkEvidenceError(f"HTTPS request failed: {exc}") from exc
        finally:
            if wrapped is not None:
                wrapped.close()
            if raw is not None:
                raw.close()


class SafeHttpClient:
    def __init__(self, *, resolver: Resolver = system_resolver,
                 transport: Transport | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.resolver = resolver
        self.transport = transport or HttpsTransport()
        self.clock = clock

    def fetch(
        self, url: str, limits: FetchLimits | None = None, *,
        on_attempt: Callable[[], None] | None = None,
        on_bytes: Callable[[int], None] | None = None,
        remaining_bytes: Callable[[], int] | None = None,
    ) -> RawResponse:
        limits = limits or FetchLimits()
        requested = url
        current = url
        redirects: list[str] = []
        deadline = self.clock() + limits.total_timeout
        for hop in range(limits.max_redirects + 1):
            parsed = self._validate_url(current)
            if on_attempt is not None:
                on_attempt()
            addresses = list(dict.fromkeys(
                self._resolve(parsed.hostname or "", deadline)
            ))
            if not addresses or any(not _public(address) for address in addresses):
                raise NetworkEvidenceError("DNS returned an empty or non-public address set")
            selected = sorted(addresses, key=lambda item: ipaddress.ip_address(item).packed)[0]
            response = self.transport.request(
                current, selected, limits, deadline, on_bytes=on_bytes
            )
            if response.peer_ip != selected or not _public(response.peer_ip):
                raise NetworkEvidenceError("connected peer did not match the selected public address")
            headers = {key.lower(): value for key, value in response.headers.items()}
            compressed = b"".join(response.chunks)
            if len(compressed) > limits.max_compressed_bytes:
                raise NetworkEvidenceError("compressed response exceeds byte cap")
            if response.status in {301, 302, 303, 307, 308}:
                location = headers.get("location")
                if not location:
                    raise NetworkEvidenceError("redirect response has no Location")
                if hop >= limits.max_redirects:
                    raise NetworkEvidenceError("redirect limit exceeded")
                current = urllib.parse.urljoin(current, location)
                redirects.append(current)
                continue
            if not 200 <= response.status < 300:
                raise NetworkEvidenceError(f"external source returned HTTP {response.status}")
            decode_limits = limits
            if remaining_bytes is not None:
                decode_limits = FetchLimits(
                    limits.connect_timeout, limits.read_timeout, limits.total_timeout,
                    limits.max_redirects, limits.max_compressed_bytes,
                    min(limits.max_decompressed_bytes, max(0, remaining_bytes())),
                )
            body = self._decode(
                compressed, headers.get("content-encoding", ""), decode_limits,
                on_output=on_bytes,
            )
            media = headers.get("content-type", "text/plain").split(";", 1)[0].lower().strip()
            if not self._text_media(media):
                raise NetworkEvidenceError(f"unsupported external media type {media!r}")
            return RawResponse(
                requested_url=requested,
                final_url=current,
                retrieved_at=datetime.now(timezone.utc).isoformat(),
                status=response.status,
                media_type=media,
                body=body,
                sha256=hashlib.sha256(body).hexdigest(),
                size=len(body),
                redirects=tuple(redirects),
            )
        raise NetworkEvidenceError("redirect limit exceeded")

    def _resolve(self, host: str, deadline: float) -> Sequence[str]:
        result: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

        def run() -> None:
            try:
                result.put((True, self.resolver(host)))
            except BaseException as exc:  # transported to the owning request thread
                result.put((False, exc))

        worker = threading.Thread(target=run, daemon=True, name="paranoia-dns")
        worker.start()
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise NetworkEvidenceError("external request total deadline expired")
        try:
            ok, value = result.get(timeout=remaining)
        except queue.Empty as exc:
            raise NetworkEvidenceError("external DNS resolution exceeded total deadline") from exc
        if not ok:
            if isinstance(value, NetworkEvidenceError):
                raise value
            raise NetworkEvidenceError(f"DNS resolution failed for {host}: {value}")
        return value  # type: ignore[return-value]

    @staticmethod
    def _validate_url(url: str) -> urllib.parse.SplitResult:
        if not isinstance(url, str) or any(
            ord(char) < 0x20 or ord(char) == 0x7F or ord(char) > 0x7E for char in url
        ):
            raise NetworkEvidenceError(
                "external evidence URL must contain printable ASCII with non-ASCII data percent-encoded"
            )
        try:
            parsed = urllib.parse.urlsplit(url)
            _ = parsed.port
        except ValueError as exc:
            raise NetworkEvidenceError(f"invalid external URL: {exc}") from exc
        if parsed.scheme != "https" or not parsed.hostname:
            raise NetworkEvidenceError("external evidence URL must use HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise NetworkEvidenceError("external evidence URL may not contain credentials")
        if parsed.fragment:
            parsed = parsed._replace(fragment="")
        return parsed

    @staticmethod
    def _decode(
        data: bytes, encoding: str, limits: FetchLimits,
        *, on_output: Callable[[int], None] | None = None,
    ) -> bytes:
        encoding = encoding.strip().lower()
        try:
            if not encoding or encoding == "identity":
                body = data
            elif encoding == "gzip":
                body = _bounded_inflate(
                    data, limits.max_decompressed_bytes, 16 + zlib.MAX_WBITS, on_output
                )
            elif encoding == "deflate":
                body = _bounded_inflate(
                    data, limits.max_decompressed_bytes, zlib.MAX_WBITS, on_output
                )
            else:
                raise NetworkEvidenceError(f"unsupported content encoding {encoding!r}")
        except (OSError, zlib.error) as exc:
            raise NetworkEvidenceError(f"response decompression failed: {exc}") from exc
        if len(body) > limits.max_decompressed_bytes:
            raise NetworkEvidenceError("decompressed response exceeds byte cap")
        return body

    @staticmethod
    def _text_media(media: str) -> bool:
        return media.startswith("text/") or media in {
            "application/json", "application/xml", "application/xhtml+xml",
            "application/javascript", "application/ld+json",
        }


class EndpointSearchProvider:
    """A bounded configurable HTTPS JSON search endpoint.

    The endpoint template must contain ``{query}`` and may contain ``{limit}``.  It
    returns ``{"hits":[{"url":"https://...","title":"..."}]}``.
    """

    def __init__(self, endpoint_template: str, client: SafeHttpClient) -> None:
        if not isinstance(endpoint_template, str):
            raise NetworkEvidenceError("search endpoint template must be a string")
        try:
            parsed_fields = list(string.Formatter().parse(endpoint_template))
        except ValueError as exc:
            raise NetworkEvidenceError(f"search endpoint template is malformed: {exc}") from exc
        fields = [field for _literal, field, _spec, _conversion in parsed_fields if field]
        if "query" not in fields or any(field not in {"query", "limit"} for field in fields):
            raise NetworkEvidenceError(
                "search endpoint template must use {query} and optional {limit} only"
            )
        if any(spec or conversion for _literal, _field, spec, conversion in parsed_fields):
            raise NetworkEvidenceError("search endpoint template formats/conversions are forbidden")
        try:
            rendered = endpoint_template.format(query="probe", limit=1)
        except (KeyError, IndexError, ValueError) as exc:
            raise NetworkEvidenceError(f"search endpoint template is malformed: {exc}") from exc
        client._validate_url(rendered)
        self.endpoint_template = endpoint_template
        self.client = client
        self.last_response_size = 0

    def search(self, query: str, *, limit: int = 5,
               limits: FetchLimits | None = None,
               on_attempt: Callable[[], None] | None = None,
               on_bytes: Callable[[int], None] | None = None,
               remaining_bytes: Callable[[], int] | None = None) -> list[SearchHit]:
        self.last_response_size = 0
        if not query or len(query) > 500 or not (1 <= limit <= 10):
            raise NetworkEvidenceError("external search query exceeds bounds")
        try:
            url = self.endpoint_template.format(
                query=urllib.parse.quote_plus(query), limit=limit,
            )
        except (KeyError, IndexError, ValueError) as exc:
            raise NetworkEvidenceError(f"search endpoint formatting failed: {exc}") from exc
        response = self.client.fetch(
            url, limits, on_attempt=on_attempt, on_bytes=on_bytes,
            remaining_bytes=remaining_bytes,
        )
        self.last_response_size = response.size
        if response.media_type not in {"application/json", "application/ld+json"}:
            raise NetworkEvidenceError("search endpoint did not return JSON")
        try:
            payload = json.loads(response.body)
            rows = payload["hits"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise NetworkEvidenceError("search endpoint returned malformed JSON") from exc
        if not isinstance(rows, list) or len(rows) > 100:
            raise NetworkEvidenceError("search endpoint hits must be a bounded array")
        hits: list[SearchHit] = []
        for row in rows[:limit]:
            if not isinstance(row, dict) or not isinstance(row.get("url"), str):
                raise NetworkEvidenceError("search endpoint hit is malformed")
            self.client._validate_url(row["url"])
            title = row.get("title", "")
            if not isinstance(title, str):
                raise NetworkEvidenceError("search endpoint hit title is malformed")
            hits.append(SearchHit(row["url"], title[:500]))
        return hits


def _bounded_inflate(
    data: bytes, limit: int, wbits: int,
    on_output: Callable[[int], None] | None = None,
) -> bytes:
    """Inflate with ``max_length`` so hostile ratios never allocate past the cap."""
    decoder = zlib.decompressobj(wbits)
    output = bytearray()
    pending = data
    while pending:
        remaining = limit - len(output)
        piece = decoder.decompress(pending, remaining + 1)
        if on_output is not None:
            on_output(len(piece))
        output.extend(piece)
        if len(output) > limit:
            raise NetworkEvidenceError("decompressed response exceeds byte cap")
        pending = decoder.unconsumed_tail
        if not pending:
            break
    remaining = limit - len(output)
    flushed = decoder.flush(remaining + 1)
    if on_output is not None:
        on_output(len(flushed))
    output.extend(flushed)
    if len(output) > limit:
        raise NetworkEvidenceError("decompressed response exceeds byte cap")
    if not decoder.eof:
        raise NetworkEvidenceError("response decompression was incomplete")
    return bytes(output)
