"""Bounded native Git blob batches with exact object identity.

Process policy belongs to inert_git. This module owns only request grouping and
the documented cat-file byte framing; it has no cache or filesystem authority.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from . import inert_git

MAX_BATCH_OBJECTS = 128
MAX_BATCH_BYTES = 8 * 1024 * 1024


def validate_oid(oid: str) -> None:
    if len(oid) not in (40, 64) or any(c not in "0123456789abcdef" for c in oid):
        raise RuntimeError(f"invalid full Git object id: {oid!r}")


def blob_oid(data: bytes, oid_length: int) -> str:
    algorithm = {40: "sha1", 64: "sha256"}.get(oid_length)
    if algorithm is None:
        raise RuntimeError(f"unsupported Git object id length: {oid_length}")
    digest = hashlib.new(algorithm)
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


@dataclass(frozen=True)
class BlobRequest:
    oid: str
    size: int

    def __post_init__(self) -> None:
        validate_oid(self.oid)
        if type(self.size) is not int or self.size < 0:
            raise RuntimeError("blob size must be a nonnegative integer")


def batches(requests: Iterable[BlobRequest]) -> Iterator[tuple[BlobRequest, ...]]:
    """Group complete objects; an oversized object gets a dedicated batch."""
    pending: list[BlobRequest] = []
    size = 0
    for request in requests:
        if pending and (
            len(pending) == MAX_BATCH_OBJECTS or size + request.size > MAX_BATCH_BYTES
        ):
            yield tuple(pending)
            pending = []
            size = 0
        pending.append(request)
        size += request.size
        if size >= MAX_BATCH_BYTES:
            yield tuple(pending)
            pending = []
            size = 0
    if pending:
        yield tuple(pending)


def decode_batch(raw: bytes, requests: Sequence[BlobRequest]) -> tuple[bytes, ...]:
    """Validate all frames before returning any payload from this batch."""
    offset = 0
    result = []
    for request in requests:
        # Constructing the exact header bounds framing as well as type, size and ID.
        header = f"{request.oid} blob {request.size}\n".encode("ascii")
        if not raw.startswith(header, offset):
            raise RuntimeError(f"missing or invalid blob frame for {request.oid}")
        start = offset + len(header)
        end = start + request.size
        if end >= len(raw) or raw[end:end + 1] != b"\n":
            raise RuntimeError(f"truncated blob frame for {request.oid}")
        data = raw[start:end]
        if blob_oid(data, len(request.oid)) != request.oid:
            raise RuntimeError(f"blob digest mismatch for {request.oid}")
        result.append(data)
        offset = end + 1
    if offset != len(raw):
        raise RuntimeError("unexpected trailing Git batch output")
    return tuple(result)


def read_batch(repo: Path, requests: Sequence[BlobRequest]) -> tuple[bytes, ...]:
    if not requests:
        return ()
    # IDs, never repository path bytes, are the native protocol's line-delimited input.
    raw = inert_git.run(
        repo, ["cat-file", "--batch"],
        input_bytes=b"".join(request.oid.encode("ascii") + b"\n" for request in requests),
    )
    return decode_batch(raw, requests)


def read_blobs(repo: Path, requests: Iterable[BlobRequest]) -> Iterator[bytes]:
    """Release each completed batch before acquiring the next one."""
    for batch in batches(requests):
        yield from read_batch(repo, batch)
