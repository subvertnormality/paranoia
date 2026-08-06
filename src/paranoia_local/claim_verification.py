"""Impure, bounded evidence collection for plan claim closure."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .evidence_store import EvidenceStore, EvidenceStoreError
from .external_evidence import (
    EndpointSearchProvider, FetchLimits, NetworkEvidenceError, SafeHttpClient,
)
from .plan_snapshot import PlanRepositorySnapshot, SnapshotUnavailable
from . import plan_claims as pc

REQUEST_MARKER = "=== EVIDENCE REQUESTS ==="
REQUESTS_PREFIX = "REQUESTS-JSON: "
MAX_REQUESTS = 20
MAX_FETCHES = 8
MAX_PER_CLAIM = 2
MAX_AGGREGATE_BYTES = 5 << 20
MAX_PASSAGE_BYTES = 4096


class EvidenceRequestError(ValueError):
    pass


class EvidenceBudgetExceeded(EvidenceRequestError):
    """The shared round budget is exhausted; callers must not treat this as stale data."""


@dataclass(frozen=True)
class EvidenceRequest:
    op: str
    data: dict[str, Any]


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    claim_id: str
    kind: str
    source: str
    blob_digest: str | None
    source_sha256: str
    source_size: int
    passage_start: int
    passage_end: int
    passage_sha256: str
    display_passage: str
    metadata: dict[str, Any]


@dataclass
class EvidenceBudget:
    """One budget shared by every evidence phase in a closure round."""

    requests: int = 0
    fetch_attempts: int = 0
    aggregate_bytes: int = 0
    per_claim: dict[str, int] = field(default_factory=dict)

    def copy(self) -> "EvidenceBudget":
        return EvidenceBudget(
            self.requests, self.fetch_attempts, self.aggregate_bytes,
            dict(self.per_claim),
        )

    def debit_requests(self, requests: Sequence[EvidenceRequest]) -> None:
        if self.requests + len(requests) > MAX_REQUESTS:
            raise EvidenceBudgetExceeded("review evidence request budget exceeded")
        for request in requests:
            claim_id = request.data["claim_id"]
            count = self.per_claim.get(claim_id, 0) + 1
            if count > MAX_PER_CLAIM:
                raise EvidenceBudgetExceeded(
                    f"claim {claim_id} exceeds shared per-round request budget"
                )
            self.per_claim[claim_id] = count
        self.requests += len(requests)

    def debit_fetch(self) -> None:
        if self.fetch_attempts >= MAX_FETCHES:
            raise EvidenceBudgetExceeded("external fetch-attempt budget exceeded")
        self.fetch_attempts += 1

    def debit_bytes(self, size: int) -> None:
        if size < 0 or self.aggregate_bytes + size > MAX_AGGREGATE_BYTES:
            raise EvidenceBudgetExceeded("review evidence aggregate byte budget exceeded")
        self.aggregate_bytes += size

    @property
    def remaining_bytes(self) -> int:
        return MAX_AGGREGATE_BYTES - self.aggregate_bytes


_REQUEST_FIELDS = {
    "LIST_TREE": {"op", "claim_id", "prefix", "limit"},
    "READ_BLOB": {"op", "claim_id", "path", "offset", "max_bytes"},
    "SEARCH_LITERAL": {"op", "claim_id", "pattern", "paths", "limit"},
    "HISTORY": {"op", "claim_id", "ref", "path", "limit"},
    "RUN_ADAPTER": {"op", "claim_id", "adapter", "paths"},
    "SEARCH_EXTERNAL": {"op", "claim_id", "query", "limit"},
}


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise EvidenceRequestError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def parse_requests(text: str, active_claim_ids: set[str]) -> list[EvidenceRequest]:
    if text.count(REQUEST_MARKER) != 1:
        raise EvidenceRequestError("expected exactly one EVIDENCE REQUESTS block")
    tail = text.split(REQUEST_MARKER, 1)[1].lstrip("\n")
    line, _, rest = tail.partition("\n")
    if rest.strip() or not line.startswith(REQUESTS_PREFIX):
        raise EvidenceRequestError("evidence request block must be one terminal JSON line")
    try:
        raw = json.loads(line[len(REQUESTS_PREFIX):], object_pairs_hook=_pairs)
    except EvidenceRequestError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise EvidenceRequestError(f"REQUESTS-JSON is invalid: {exc}") from exc
    if not isinstance(raw, list) or len(raw) > MAX_REQUESTS:
        raise EvidenceRequestError(f"REQUESTS-JSON must be an array of at most {MAX_REQUESTS}")
    requests: list[EvidenceRequest] = []
    per_claim: dict[str, int] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("op"), str) \
                or item.get("op") not in _REQUEST_FIELDS:
            raise EvidenceRequestError("unknown evidence request operation")
        op = item["op"]
        if set(item) != _REQUEST_FIELDS[op]:
            raise EvidenceRequestError(f"{op} has missing or unknown fields")
        claim_id = item.get("claim_id")
        if not isinstance(claim_id, str) or claim_id not in active_claim_ids:
            raise EvidenceRequestError("evidence request references an unknown claim")
        per_claim[claim_id] = per_claim.get(claim_id, 0) + 1
        if per_claim[claim_id] > MAX_PER_CLAIM:
            raise EvidenceRequestError(f"claim {claim_id} exceeds per-round request budget")
        _validate_request(op, item)
        requests.append(EvidenceRequest(op, item))
    return requests


def _validate_request(op: str, item: Mapping[str, Any]) -> None:
    limit = item.get("limit")
    if op not in {"READ_BLOB", "RUN_ADAPTER"} and (
        not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200
    ):
        raise EvidenceRequestError(f"{op}.limit is out of bounds")
    if op == "READ_BLOB":
        if not isinstance(item.get("path"), str) or not item["path"]:
            raise EvidenceRequestError("READ_BLOB.path is required")
        size = item.get("max_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 1 << 20:
            raise EvidenceRequestError("READ_BLOB.max_bytes is out of bounds")
        offset = item.get("offset")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise EvidenceRequestError("READ_BLOB.offset is out of bounds")
    if op == "SEARCH_LITERAL":
        if not isinstance(item.get("pattern"), str) or not item["pattern"] or len(item["pattern"]) > 256:
            raise EvidenceRequestError("SEARCH_LITERAL.pattern is out of bounds")
        if not isinstance(item.get("paths"), list) or len(item["paths"]) > 50 \
                or any(not isinstance(path, str) or not path for path in item["paths"]):
            raise EvidenceRequestError("SEARCH_LITERAL.paths is out of bounds")
    if op == "LIST_TREE" and not isinstance(item.get("prefix"), str):
        raise EvidenceRequestError("LIST_TREE.prefix must be a string")
    if op == "SEARCH_EXTERNAL":
        if not isinstance(item.get("query"), str) or not item["query"] or len(item["query"]) > 500:
            raise EvidenceRequestError("SEARCH_EXTERNAL.query is out of bounds")
        if limit > 10:
            raise EvidenceRequestError("SEARCH_EXTERNAL.limit is out of bounds")
    if op == "HISTORY":
        if not isinstance(item.get("ref"), str) or not item["ref"]:
            raise EvidenceRequestError("HISTORY.ref is required")
        if not isinstance(item.get("path"), str) or not item["path"] or limit > 50:
            raise EvidenceRequestError("HISTORY path/limit is out of bounds")
    if op == "RUN_ADAPTER":
        if item.get("adapter") != "PYTHON_COMPILE":
            raise EvidenceRequestError("RUN_ADAPTER supports only PYTHON_COMPILE")
        if not isinstance(item.get("paths"), list) or not 1 <= len(item["paths"]) <= 20 \
                or any(not isinstance(path, str) or not path for path in item["paths"]):
            raise EvidenceRequestError("RUN_ADAPTER.paths must contain 1..20 paths")
    git_operands = [
        item[key] for key in ("prefix", "path", "ref", "pattern")
        if isinstance(item.get(key), str)
    ]
    if isinstance(item.get("paths"), list):
        git_operands.extend(path for path in item["paths"] if isinstance(path, str))
    if any("\0" in value for value in git_operands):
        raise EvidenceRequestError(f"{op} Git operands may not contain NUL")


def collect_evidence(
    requests: Sequence[EvidenceRequest],
    *,
    snapshot: PlanRepositorySnapshot,
    store: EvidenceStore,
    run_id: str,
    search_provider: EndpointSearchProvider | None = None,
    http_client: SafeHttpClient | None = None,
    budget: EvidenceBudget | None = None,
) -> list[EvidenceRecord]:
    budget = budget or EvidenceBudget()
    budget.debit_requests(requests)
    records: list[EvidenceRecord] = []
    for request in requests:
        data = request.data
        claim_id = data["claim_id"]
        if request.op == "LIST_TREE":
            paths = snapshot.list_tree(
                data["prefix"], limit=data["limit"], debit_bytes=budget.debit_bytes,
                remaining_bytes=lambda: budget.remaining_bytes,
            )
            body = json.dumps(paths, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8", errors="surrogateescape"
            )
            budget.debit_bytes(len(body))
            records.append(_record(store, run_id, claim_id, "repository-list",
                                   snapshot.commit_id, body, {
                                       "prefix": data["prefix"],
                                       "snapshot_commit": snapshot.commit_id,
                                   }))
        elif request.op == "READ_BLOB":
            try:
                _blob_oid, whole_size = snapshot.blob_identity(data["path"])
                source_size = min(data["max_bytes"], max(0, whole_size - data["offset"]))
                budget.debit_bytes(source_size)
                body = snapshot.read_blob(
                    data["path"], offset=data["offset"], max_bytes=max(1, source_size),
                )
            except SnapshotUnavailable as exc:
                if "gitlinks are unavailable" in str(exc):
                    continue
                raise
            blob_oid, whole_size = snapshot.blob_identity(data["path"])
            records.append(_record(store, run_id, claim_id, "repository-blob",
                                   data["path"], body,
                                   {"snapshot_commit": snapshot.commit_id, "path": data["path"],
                                    "blob_oid": blob_oid, "whole_size": whole_size,
                                    "offset": data["offset"], "length": len(body)}))
        elif request.op == "SEARCH_LITERAL":
            matches = snapshot.search_literal(data["pattern"], paths=data["paths"],
                                               limit=min(data["limit"], 50),
                                               debit_bytes=budget.debit_bytes,
                                               remaining_bytes=lambda: budget.remaining_bytes)
            body = json.dumps(matches, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8", errors="surrogateescape"
            )
            budget.debit_bytes(len(body))
            records.append(_record(store, run_id, claim_id, "repository-search",
                                   snapshot.commit_id, body,
                                   {"pattern": data["pattern"], "paths": data["paths"],
                                    "snapshot_commit": snapshot.commit_id}))
        elif request.op == "HISTORY":
            rows = snapshot.history(
                data["ref"], data["path"], limit=data["limit"],
                debit_bytes=budget.debit_bytes,
                remaining_bytes=lambda: budget.remaining_bytes,
            )
            body = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
            budget.debit_bytes(len(body))
            records.append(_record(
                store, run_id, claim_id, "repository-history", data["ref"], body,
                {"ref": data["ref"], "path": data["path"],
                 "history_oid": snapshot.history_oid(data["ref"]), "limit": data["limit"],
                 "snapshot_commit": snapshot.commit_id},
            ))
        elif request.op == "RUN_ADAPTER":
            rows: list[dict[str, Any]] = []
            inputs: dict[str, str] = {}
            for path in data["paths"]:
                _oid, input_size = snapshot.blob_identity(path)
                if input_size > 1 << 20:
                    raise EvidenceRequestError("empirical adapter input exceeds 1 MiB")
                budget.debit_bytes(input_size)
                source = snapshot.read_blob(
                    path, max_bytes=max(1, input_size)
                )
                inputs[path] = hashlib.sha256(source).hexdigest()
                try:
                    compile(source, path, "exec")
                    rows.append({"path": path, "compiled": True, "error": None})
                except (SyntaxError, ValueError, TypeError) as exc:
                    rows.append({"path": path, "compiled": False,
                                 "error": f"{type(exc).__name__}: {exc}"[:1000]})
            body = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
            budget.debit_bytes(len(body))
            records.append(_record(
                store, run_id, claim_id, "empirical", "PYTHON_COMPILE", body,
                {
                    "argv": [sys.executable, "<server PYTHON_COMPILE adapter>"],
                    "runtime": sys.version,
                    "snapshot_commit": snapshot.commit_id,
                    "input_hashes": inputs,
                    "exit_status": 0 if all(row["compiled"] for row in rows) else 1,
                    "falsifying_result": any(not row["compiled"] for row in rows),
                },
            ))
        else:
            if search_provider is None or http_client is None:
                # Absence is explicit abstention, never a fabricated evidence record.
                continue
            try:
                hits = search_provider.search(
                    data["query"], limit=min(data["limit"], 2),
                    limits=_fetch_limits(budget.remaining_bytes),
                    on_attempt=budget.debit_fetch,
                    on_bytes=budget.debit_bytes,
                    remaining_bytes=lambda: budget.remaining_bytes,
                )
            except NetworkEvidenceError as exc:
                records.append(_abstention(claim_id, "external-search", data["query"], str(exc)))
                continue
            for hit in hits:
                try:
                    response = http_client.fetch(
                        hit.url, _fetch_limits(budget.remaining_bytes),
                        on_attempt=budget.debit_fetch,
                        on_bytes=budget.debit_bytes,
                        remaining_bytes=lambda: budget.remaining_bytes,
                    )
                except NetworkEvidenceError as exc:
                    records.append(_abstention(claim_id, "external-fetch", hit.url, str(exc)))
                    continue
                records.append(_record(
                    store, run_id, claim_id, "external", response.final_url, response.body,
                    {
                        "requested_url": response.requested_url,
                        "final_url": response.final_url,
                        "retrieved_at": response.retrieved_at,
                        "http_status": response.status,
                        "media_type": response.media_type,
                        "redirects": list(response.redirects),
                        "publisher_domain": _domain(response.final_url),
                        "source_class": "unclassified-external",
                        "independence_groups": [
                            "domain:" + _domain(response.final_url),
                            "content:" + response.sha256,
                        ],
                        "conflicts": [],
                    },
                ))
    return records


def _fetch_limits(remaining: int) -> FetchLimits:
    if remaining < 1:
        raise EvidenceRequestError("review evidence aggregate byte budget exceeded")
    return FetchLimits(
        max_compressed_bytes=min(1 << 20, remaining),
        max_decompressed_bytes=min(1 << 20, remaining),
    )


def collect_supplied_evidence(
    supplied: Sequence[Mapping[str, Any]], *, claims: pc.ClaimState,
    store: EvidenceStore, run_id: str, budget: EvidenceBudget | None = None,
) -> list[EvidenceRecord]:
    """Hash bounded caller artifacts and bind them to one exact registered claim."""
    if len(supplied) > 20:
        raise EvidenceRequestError("supplied_evidence exceeds 20 records")
    records: list[EvidenceRecord] = []
    budget = budget or EvidenceBudget()
    for item in supplied:
        if set(item) != {"claim", "source", "content"}:
            raise EvidenceRequestError(
                "supplied evidence needs exactly claim, source, and content"
            )
        proposition, source, content = item["claim"], item["source"], item["content"]
        if not all(isinstance(value, str) and value for value in (proposition, source, content)):
            raise EvidenceRequestError("supplied evidence fields must be nonempty strings")
        matches = [claim for claim in claims.claims.values() if claim.claim == proposition]
        if len(matches) != 1:
            raise EvidenceRequestError("supplied evidence claim must match one registered claim")
        body = content.encode("utf-8", errors="surrogateescape")
        if len(body) > 1 << 20:
            raise EvidenceRequestError("supplied evidence exceeds byte budget")
        budget.debit_bytes(len(body))
        records.append(_record(
            store, run_id, matches[0].claim_id, "supplied-artifact", source, body,
            {"source": source, "caller_supplied": True},
        ))
    return records


def _record(store: EvidenceStore, run_id: str, claim_id: str, kind: str, source: str,
            body: bytes, metadata: dict[str, Any]) -> EvidenceRecord:
    digest = store.stage(run_id, body)
    passage = body[:MAX_PASSAGE_BYTES]
    identity = _evidence_identity(claim_id, kind, source, digest, metadata)
    return EvidenceRecord(
        evidence_id="e" + identity,
        claim_id=claim_id,
        kind=kind,
        source=source,
        blob_digest=digest,
        source_sha256=digest,
        source_size=len(body),
        passage_start=0,
        passage_end=len(passage),
        passage_sha256=hashlib.sha256(passage).hexdigest(),
        display_passage=passage.decode("utf-8", errors="replace"),
        metadata=metadata,
    )


def _evidence_identity(
    claim_id: str, kind: str, source: str, digest: str, metadata: Mapping[str, Any]
) -> str:
    scope = json.dumps(
        metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(
        (claim_id + "\0" + kind + "\0" + source + "\0" + digest + "\0" + scope).encode(
            "utf-8", errors="surrogateescape"
        )
    ).hexdigest()[:12]


def _abstention(claim_id: str, kind: str, source: str, reason: str) -> EvidenceRecord:
    digest = hashlib.sha256((claim_id + "\0" + kind + "\0" + source + "\0" + reason).encode()).hexdigest()
    return EvidenceRecord(
        evidence_id="a" + digest[:12], claim_id=claim_id, kind="abstention",
        source=source, blob_digest=None, source_sha256=digest, source_size=0,
        passage_start=0, passage_end=0, passage_sha256=hashlib.sha256(b"").hexdigest(),
        display_passage="", metadata={"stage": kind, "reason": reason[:1000]},
    )


def render_evidence(
    records: Sequence[EvidenceRecord], *, include_passages: bool,
    debit_bytes: Callable[[int], None] | None = None,
) -> str:
    lines = ["=== SERVER EVIDENCE RECORDS ==="]
    if not records:
        rendered = lines[0] + "\nNONE — verification must abstain."
        if debit_bytes is not None:
            debit_bytes(len(rendered.encode("utf-8")))
        return rendered
    for record in records:
        record_lines = [
            "RECORD=" + json.dumps(
                {
                    "evidence_id": record.evidence_id,
                    "claim_id": record.claim_id,
                    "kind": record.kind,
                    "source": record.source,
                    "sha256": record.source_sha256,
                    "bytes": record.source_size,
                },
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            )
        ]
        if record.metadata:
            record_lines.append(
                "  metadata=" + json.dumps(
                    record.metadata, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True,
                )[:2000]
            )
        if include_passages:
            record_lines.append(
                "  UNTRUSTED-DATA-JSON="
                + json.dumps(record.display_passage, ensure_ascii=True)
            )
        lines.extend(record_lines)
    rendered = "\n".join(lines)
    if debit_bytes is not None:
        debit_bytes(len(rendered.encode("utf-8")))
    return rendered


def records_to_json(records: Sequence[EvidenceRecord]) -> list[dict[str, Any]]:
    return [asdict(record) for record in records]


def records_from_json(rows: Sequence[Mapping[str, Any]]) -> list[EvidenceRecord]:
    if not isinstance(rows, list) or len(rows) > 1000:
        raise EvidenceRequestError("persisted evidence records must be a bounded array")
    expected = {item.name for item in EvidenceRecord.__dataclass_fields__.values()}
    records: list[EvidenceRecord] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise EvidenceRequestError("persisted evidence record has missing or unknown fields")
        row = dict(raw)
        for key in (
            "evidence_id", "claim_id", "kind", "source", "source_sha256",
            "passage_sha256", "display_passage",
        ):
            if not isinstance(row.get(key), str):
                raise EvidenceRequestError(f"persisted evidence {key} is malformed")
        if not row["evidence_id"] or row["evidence_id"] in seen or not row["claim_id"]:
            raise EvidenceRequestError("persisted evidence identity is malformed")
        seen.add(row["evidence_id"])
        for key in ("source_sha256", "passage_sha256"):
            if len(row[key]) != 64 or any(c not in "0123456789abcdef" for c in row[key]):
                raise EvidenceRequestError(f"persisted evidence {key} is malformed")
        digest = row.get("blob_digest")
        if digest is not None and (
            not isinstance(digest, str) or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise EvidenceRequestError("persisted evidence blob digest is malformed")
        if row["kind"] != "abstention" and digest is None:
            raise EvidenceRequestError("persisted non-abstention evidence must root exact bytes")
        for key in ("source_size", "passage_start", "passage_end"):
            if not isinstance(row.get(key), int) or isinstance(row[key], bool) or row[key] < 0:
                raise EvidenceRequestError(f"persisted evidence {key} is malformed")
        if row["passage_start"] > row["passage_end"] or row["passage_end"] > row["source_size"]:
            raise EvidenceRequestError("persisted evidence passage bounds are malformed")
        if not isinstance(row.get("metadata"), dict):
            raise EvidenceRequestError("persisted evidence metadata is malformed")
        _validate_metadata(row["kind"], row["metadata"])
        records.append(EvidenceRecord(**row))
    return records


def _validate_metadata(kind: str, metadata: Mapping[str, Any]) -> None:
    schemas = {
        "repository-list": {"prefix", "snapshot_commit"},
        "repository-blob": {
            "snapshot_commit", "path", "blob_oid", "whole_size", "offset", "length",
        },
        "repository-search": {"pattern", "paths", "snapshot_commit"},
        "repository-history": {"ref", "path", "history_oid", "limit", "snapshot_commit"},
        "empirical": {
            "argv", "runtime", "snapshot_commit", "input_hashes", "exit_status",
            "falsifying_result",
        },
        "external": {
            "requested_url", "final_url", "retrieved_at", "http_status", "media_type",
            "redirects", "publisher_domain", "source_class", "independence_groups", "conflicts",
        },
        "supplied-artifact": {"source", "caller_supplied"},
        "abstention": {"stage", "reason"},
    }
    expected = schemas.get(kind)
    if expected is None or set(metadata) != expected:
        raise EvidenceRequestError(f"persisted {kind} metadata has missing or unknown fields")
    string_fields = {
        "prefix", "snapshot_commit", "path", "blob_oid", "pattern", "ref", "history_oid",
        "runtime", "requested_url", "final_url", "retrieved_at", "media_type",
        "publisher_domain", "source_class", "source", "stage", "reason",
    }
    for key in expected.intersection(string_fields):
        if not isinstance(metadata.get(key), str):
            raise EvidenceRequestError(f"persisted {kind}.{key} must be a string")
    for key in expected.intersection({"whole_size", "offset", "length", "limit", "exit_status", "http_status"}):
        value = metadata.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise EvidenceRequestError(f"persisted {kind}.{key} must be a nonnegative integer")
    for key in expected.intersection({"caller_supplied", "falsifying_result"}):
        if not isinstance(metadata.get(key), bool):
            raise EvidenceRequestError(f"persisted {kind}.{key} must be boolean")
    for key in expected.intersection({"paths", "argv", "redirects", "independence_groups", "conflicts"}):
        value = metadata.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise EvidenceRequestError(f"persisted {kind}.{key} must be a string array")
    if "input_hashes" in expected:
        hashes = metadata.get("input_hashes")
        if not isinstance(hashes, dict) or any(
            not isinstance(path, str) or not isinstance(digest, str)
            or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
            for path, digest in hashes.items()
        ):
            raise EvidenceRequestError("persisted empirical.input_hashes is malformed")


def validate_cached_records(
    records: Sequence[EvidenceRecord], *, snapshot: PlanRepositorySnapshot,
    store: EvidenceStore, state: pc.ClaimState, high_stakes: bool = False,
    now: datetime | None = None, budget: EvidenceBudget | None = None,
) -> list[EvidenceRecord]:
    """Revalidate identities/freshness and stale every claim that depended on a miss."""
    clock = now or datetime.now(timezone.utc)
    valid: list[EvidenceRecord] = []
    invalid_ids: set[str] = set()
    budget = budget or EvidenceBudget()
    for record in records:
        try:
            if record.kind == "abstention":
                raise EvidenceRequestError("abstention records are round-local")
            if record.blob_digest:
                budget.debit_bytes(record.source_size)
                body = store.read(record.blob_digest, max_bytes=record.source_size)
                if hashlib.sha256(body).hexdigest() != record.source_sha256:
                    raise EvidenceRequestError("cached evidence source hash mismatch")
                passage = body[:MAX_PASSAGE_BYTES]
                if (
                    record.source_size != len(body)
                    or record.passage_start != 0
                    or record.passage_end != len(passage)
                    or record.passage_sha256 != hashlib.sha256(passage).hexdigest()
                    or record.display_passage != passage.decode("utf-8", errors="replace")
                    or record.evidence_id != "e" + _evidence_identity(
                        record.claim_id, record.kind, record.source,
                        record.source_sha256, record.metadata,
                    )
                ):
                    raise EvidenceRequestError("cached evidence derived fields are inconsistent")
            if record.kind == "repository-blob":
                path = record.metadata["path"]
                offset = record.metadata["offset"]
                length = record.metadata["length"]
                if path != record.source or not isinstance(offset, int) \
                        or isinstance(offset, bool) or not isinstance(length, int) \
                        or isinstance(length, bool) or length != record.source_size:
                    raise EvidenceRequestError("repository blob cache metadata is malformed")
                oid, whole_size = snapshot.blob_identity(path)
                if oid != record.metadata.get("blob_oid") \
                        or whole_size != record.metadata.get("whole_size"):
                    raise EvidenceRequestError("repository blob object identity changed")
                budget.debit_bytes(length)
                current = snapshot.read_blob(path, offset=offset, max_bytes=max(1, length))
                if hashlib.sha256(current).hexdigest() != record.source_sha256:
                    raise EvidenceRequestError("repository evidence blob changed")
            elif record.kind == "repository-history":
                ref = record.metadata["ref"]
                path = record.metadata["path"]
                limit = record.metadata["limit"]
                if not isinstance(ref, str) or not isinstance(path, str) \
                        or not isinstance(limit, int) or isinstance(limit, bool) \
                        or ref != record.source \
                        or snapshot.history_oid(ref) != record.metadata["history_oid"]:
                    raise EvidenceRequestError("repository history ref identity changed")
                current = json.dumps(
                    snapshot.history(
                        ref, path, limit=limit, debit_bytes=budget.debit_bytes,
                        remaining_bytes=lambda: budget.remaining_bytes,
                    ),
                    ensure_ascii=False, separators=(",", ":"),
                ).encode()
                budget.debit_bytes(len(current))
                if hashlib.sha256(current).hexdigest() != record.source_sha256:
                    raise EvidenceRequestError("repository history result changed")
            elif record.kind.startswith("repository"):
                if record.metadata.get("snapshot_commit", snapshot.commit_id) != snapshot.commit_id:
                    raise EvidenceRequestError("repository query scope changed")
            elif record.kind == "empirical":
                if record.metadata.get("runtime") != sys.version:
                    raise EvidenceRequestError("empirical adapter runtime changed")
                for path, expected in record.metadata.get("input_hashes", {}).items():
                    _oid, input_size = snapshot.blob_identity(path)
                    if input_size > 1 << 20:
                        raise EvidenceRequestError("empirical adapter input changed")
                    budget.debit_bytes(input_size)
                    if hashlib.sha256(snapshot.read_blob(path)).hexdigest() != expected:
                        raise EvidenceRequestError("empirical adapter input changed")
            elif record.kind == "external":
                stamp = datetime.fromisoformat(str(record.metadata["retrieved_at"]))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                ttl_hours = 24 if high_stakes else 168
                if (clock - stamp).total_seconds() > ttl_hours * 3600:
                    raise EvidenceRequestError("external evidence expired")
            valid.append(record)
        except EvidenceBudgetExceeded:
            raise
        except (EvidenceRequestError, EvidenceStoreError, SnapshotUnavailable,
                KeyError, TypeError, ValueError):
            invalid_ids.add(record.evidence_id)
    if invalid_ids:
        for claim in state.claims.values():
            if invalid_ids.intersection(claim.evidence_ids):
                claim.status = pc.STALE
            for field_name in (
                "truth_authorization", "bearing_authorization", "dispute_authorization",
                "deferral_authorization",
            ):
                info = getattr(claim, field_name) or {}
                if invalid_ids.intersection(info.get("evidence_ids", [])):
                    info["status"] = "pending"
                    setattr(claim, field_name, info)
    valid_bindings = {record.evidence_id: record.claim_id for record in valid}
    for claim in state.claims.values():
        if claim.status == pc.SUPERSEDED:
            continue
        dependencies = set(claim.evidence_ids)
        for field_name in (
            "truth_authorization", "bearing_authorization", "dispute_authorization",
            "deferral_authorization",
        ):
            dependencies.update((getattr(claim, field_name) or {}).get("evidence_ids", []))
        missing = {
            evidence_id for evidence_id in dependencies
            if valid_bindings.get(evidence_id) != claim.claim_id
        }
        if missing:
            claim.status = pc.STALE
            for field_name in (
                "truth_authorization", "bearing_authorization", "dispute_authorization",
                "deferral_authorization",
            ):
                info = getattr(claim, field_name) or {}
                if missing.intersection(info.get("evidence_ids", [])):
                    info["status"] = "pending"
                    setattr(claim, field_name, info)
    return valid


def _domain(url: str) -> str:
    from urllib.parse import urlsplit
    return urlsplit(url).hostname or ""
