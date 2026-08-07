"""Server-owned bounded discovery and HTTPS retrieval for external evidence."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import math
import multiprocessing
import socket
import ssl
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


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise NetworkEvidenceError(f"duplicate network JSON key {key!r}")
        result[key] = value
    return result


@dataclass(frozen=True)
class FetchLimits:
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    total_timeout: float = 30.0
    max_redirects: int = 5
    max_compressed_bytes: int = 2 << 20
    max_decompressed_bytes: int = 2 << 20


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


class SearchProvider(Protocol):
    def search(self, query: str, *, limit: int = 5,
               limits: FetchLimits | None = None,
               on_attempt: Callable[[], None] | None = None,
               on_bytes: Callable[[int], None] | None = None,
               remaining_bytes: Callable[[], int] | None = None) -> list[SearchHit]: ...


class Transport(Protocol):
    def request(self, url: str, address: str, limits: FetchLimits,
                deadline: float, on_bytes: Callable[[int], None] | None = None
                ) -> TransportResponse: ...


Resolver = Callable[[str], Sequence[str]]


def _resolver_worker(resolver: Resolver, host: str, connection: object) -> None:
    try:
        connection.send((True, list(resolver(host))))  # type: ignore[attr-defined]
    except BaseException as exc:
        connection.send((False, f"{type(exc).__name__}: {exc}"))  # type: ignore[attr-defined]
    finally:
        connection.close()  # type: ignore[attr-defined]


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

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: socket.socket | None = None

    def cancel(self) -> None:
        with self._lock:
            if self._active is not None:
                try:
                    self._active.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._active.close()

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
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            raw = socket.socket(family, socket.SOCK_STREAM)
            raw.settimeout(timeout)
            with self._lock:
                self._active = raw
            raw.connect((address, port))
            context = ssl.create_default_context()
            wrapped = context.wrap_socket(raw, server_hostname=host)
            raw = None
            with self._lock:
                self._active = wrapped
            wrapped.settimeout(min(limits.read_timeout, max(0.1, deadline - time.monotonic())))
            path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            authority_host = f"[{host}]" if ":" in host else host
            host_header = authority_host if port == 443 else f"{authority_host}:{port}"
            request = (
                f"GET {path} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: paranoia-local/0.1\r\n"
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
                read_size = min(65536, limits.max_compressed_bytes - total + 1)
                chunk = response.read1(read_size)
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
            with self._lock:
                self._active = None
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
            # Many local/WSL environments have IPv4 connectivity but no IPv6 route even
            # when DNS returns AAAA records. Prefer a validated public IPv4 answer when
            # one exists; IPv6-only origins still use their validated IPv6 answer.
            selected = sorted(
                addresses,
                key=lambda item: (
                    ipaddress.ip_address(item).version != 4,
                    ipaddress.ip_address(item).packed,
                ),
            )[0]
            response = self._request_with_deadline(
                current, selected, limits, deadline, on_bytes
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
                on_output=on_bytes, deadline=deadline, clock=self.clock,
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
        if "fork" not in multiprocessing.get_all_start_methods():
            raise NetworkEvidenceError("cancellable DNS resolution requires fork support")
        context = multiprocessing.get_context("fork")
        parent, child = context.Pipe(duplex=False)
        worker = context.Process(
            target=_resolver_worker, args=(self.resolver, host, child), daemon=True,
        )
        worker.start()
        child.close()
        remaining = deadline - self.clock()
        if remaining <= 0:
            worker.kill()
            worker.join(timeout=0)
            raise NetworkEvidenceError("external DNS resolution exceeded total deadline")
        if not parent.poll(remaining):
            worker.kill()
            worker.join(timeout=0)
            parent.close()
            raise NetworkEvidenceError("external DNS resolution exceeded total deadline")
        ok, value = parent.recv()
        parent.close()
        worker.join(timeout=max(0.0, deadline - self.clock()))
        if not ok:
            raise NetworkEvidenceError(f"DNS resolution failed for {host}: {value}")
        return value

    def _request_with_deadline(
        self, url: str, address: str, limits: FetchLimits, deadline: float,
        on_bytes: Callable[[int], None] | None,
    ) -> TransportResponse:
        result: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)
        callbacks_active = threading.Event()
        callbacks_active.set()

        def bounded_bytes(size: int) -> None:
            if callbacks_active.is_set() and on_bytes is not None:
                on_bytes(size)

        def run() -> None:
            try:
                result.put((True, self.transport.request(
                    url, address, limits, deadline, on_bytes=bounded_bytes
                )))
            except BaseException as exc:
                result.put((False, exc))

        worker = threading.Thread(target=run, daemon=True, name="paranoia-https")
        worker.start()
        remaining = deadline - self.clock()
        if remaining <= 0:
            callbacks_active.clear()
            cancel = getattr(self.transport, "cancel", None)
            if callable(cancel):
                cancel()
            raise NetworkEvidenceError("external request total deadline expired")
        try:
            ok, value = result.get(timeout=remaining)
        except queue.Empty as exc:
            callbacks_active.clear()
            cancel = getattr(self.transport, "cancel", None)
            if callable(cancel):
                cancel()
            raise NetworkEvidenceError("external request exceeded total deadline") from exc
        if not ok:
            if isinstance(value, Exception):
                raise value
            raise NetworkEvidenceError("external request failed")
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
        deadline: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> bytes:
        encoding = encoding.strip().lower()
        try:
            if not encoding or encoding == "identity":
                body = data
            elif encoding == "gzip":
                body = _bounded_inflate(
                    data, limits.max_decompressed_bytes, 16 + zlib.MAX_WBITS, on_output,
                    deadline, clock,
                )
            elif encoding == "deflate":
                body = _bounded_inflate(
                    data, limits.max_decompressed_bytes, zlib.MAX_WBITS, on_output,
                    deadline, clock,
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


class NativeSearchProvider:
    """Bounded discovery through the selected reviewer's built-in web search.

    ``discover`` runs in the engine layer's search-only profile. Its result is only a
    list of candidate URLs; the server validates and fetches every candidate itself.
    """

    _MARKER = "=== SEARCH CANDIDATES ==="
    _PREFIX = "CANDIDATES-JSON: "
    _MAX_OUTPUT_BYTES = 64 << 10

    def __init__(
        self, discover: Callable[[str, int], str], client: SafeHttpClient,
    ) -> None:
        self.discover = discover
        self.client = client
        self.last_response_size = 0

    @staticmethod
    def _prompt(query: str, limit: int) -> str:
        return (
            "You are a neutral web-source discovery role. Use native web search only. "
            "Search results are leads, not evidence, and search rank is not authority. "
            "Prefer original specifications, official documentation, original research, "
            "regulator/government material, canonical repositories, releases, and datasets. "
            "Seek sources capable of testing the query, including materially supporting and "
            "contradicting sources; do not hunt only for confirmation. User-generated content "
            "may reveal leads but is never primary or authoritative for general factual claims. "
            f"Return at most {limit} distinct public HTTPS candidates for this query. Do not "
            "classify their authority and do not quote page content.\n\n"
            "QUERY-JSON: " + json.dumps(query, ensure_ascii=True) + "\n\n"
            "End with exactly two lines:\n"
            "=== SEARCH CANDIDATES ===\n"
            "CANDIDATES-JSON: <one-line JSON array of exact "
            '{"url":"https://...","title":"..."} objects>'
        )

    def search(self, query: str, *, limit: int = 5,
               limits: FetchLimits | None = None,
               on_attempt: Callable[[], None] | None = None,
               on_bytes: Callable[[int], None] | None = None,
               remaining_bytes: Callable[[], int] | None = None) -> list[SearchHit]:
        limits = limits or FetchLimits()
        self.last_response_size = 0
        if not query or len(query.encode("utf-8", errors="strict")) > 500 \
                or not (1 <= limit <= 10):
            raise NetworkEvidenceError("external search query exceeds bounds")
        if on_attempt is not None:
            on_attempt()
        try:
            output = self.discover(
                self._prompt(query, limit), max(1, math.ceil(limits.total_timeout)),
            )
        except NetworkEvidenceError:
            raise
        except Exception as exc:
            raise NetworkEvidenceError(f"native web discovery failed: {exc}") from exc
        if not isinstance(output, str):
            raise NetworkEvidenceError("native web discovery returned malformed output")
        encoded_size = len(output.encode("utf-8", errors="strict"))
        self.last_response_size = encoded_size
        if encoded_size > self._MAX_OUTPUT_BYTES \
                or remaining_bytes is not None and encoded_size > remaining_bytes():
            raise NetworkEvidenceError("native web discovery output exceeds byte cap")
        if on_bytes is not None:
            on_bytes(encoded_size)
        if output.count(self._MARKER) != 1:
            raise NetworkEvidenceError("native web discovery returned malformed output")
        tail = output.split(self._MARKER, 1)[1].lstrip("\n")
        line, _, rest = tail.partition("\n")
        if rest.strip() or not line.startswith(self._PREFIX):
            raise NetworkEvidenceError("native web discovery returned malformed output")
        try:
            rows = json.loads(line[len(self._PREFIX):], object_pairs_hook=_strict_object)
        except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
            raise NetworkEvidenceError("native web discovery returned malformed JSON") from exc
        if not isinstance(rows, list) or len(rows) > limit:
            raise NetworkEvidenceError("native web discovery returned malformed candidates")
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"url", "title"} \
                    or not isinstance(row.get("url"), str) \
                    or not isinstance(row.get("title"), str):
                raise NetworkEvidenceError("native web discovery candidate is malformed")
            self.client._validate_url(row["url"])
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            hits.append(SearchHit(row["url"], row["title"][:500]))
        return hits


def _bounded_inflate(
    data: bytes, limit: int, wbits: int,
    on_output: Callable[[int], None] | None = None,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> bytes:
    """Inflate with ``max_length`` so hostile ratios never allocate past the cap."""
    decoder = zlib.decompressobj(wbits)
    output = bytearray()
    pending = data
    while pending:
        if deadline is not None and clock() >= deadline:
            raise NetworkEvidenceError("response decompression exceeded total deadline")
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
    if deadline is not None and clock() >= deadline:
        raise NetworkEvidenceError("response decompression exceeded total deadline")
    flushed = decoder.flush(remaining + 1)
    if on_output is not None:
        on_output(len(flushed))
    output.extend(flushed)
    if len(output) > limit:
        raise NetworkEvidenceError("decompressed response exceeds byte cap")
    if not decoder.eof:
        raise NetworkEvidenceError("response decompression was incomplete")
    return bytes(output)
