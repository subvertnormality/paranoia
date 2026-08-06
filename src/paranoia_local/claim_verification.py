"""Impure, bounded evidence collection for plan claim closure."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .evidence_store import EvidenceStore, EvidenceStoreError
from .external_evidence import EndpointSearchProvider, NetworkEvidenceError, SafeHttpClient
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


_REQUEST_FIELDS = {
    "LIST_TREE": {"op", "claim_id", "prefix", "limit"},
    "READ_BLOB": {"op", "claim_id", "path", "max_bytes"},
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
    except json.JSONDecodeError as exc:
        raise EvidenceRequestError(f"REQUESTS-JSON is invalid: {exc}") from exc
    if not isinstance(raw, list) or len(raw) > MAX_REQUESTS:
        raise EvidenceRequestError(f"REQUESTS-JSON must be an array of at most {MAX_REQUESTS}")
    requests: list[EvidenceRequest] = []
    per_claim: dict[str, int] = {}
    for item in raw:
        if not isinstance(item, dict) or item.get("op") not in _REQUEST_FIELDS:
            raise EvidenceRequestError("unknown evidence request operation")
        op = item["op"]
        if set(item) != _REQUEST_FIELDS[op]:
            raise EvidenceRequestError(f"{op} has missing or unknown fields")
        claim_id = item.get("claim_id")
        if claim_id not in active_claim_ids:
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
        size = item.get("max_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 1 << 20:
            raise EvidenceRequestError("READ_BLOB.max_bytes is out of bounds")
    if op == "SEARCH_LITERAL":
        if not isinstance(item.get("pattern"), str) or not item["pattern"] or len(item["pattern"]) > 256:
            raise EvidenceRequestError("SEARCH_LITERAL.pattern is out of bounds")
        if not isinstance(item.get("paths"), list) or len(item["paths"]) > 50:
            raise EvidenceRequestError("SEARCH_LITERAL.paths is out of bounds")
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


def collect_evidence(
    requests: Sequence[EvidenceRequest],
    *,
    snapshot: PlanRepositorySnapshot,
    store: EvidenceStore,
    run_id: str,
    search_provider: EndpointSearchProvider | None = None,
    http_client: SafeHttpClient | None = None,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    aggregate = 0
    fetches = 0
    for request in requests:
        data = request.data
        claim_id = data["claim_id"]
        if request.op == "LIST_TREE":
            paths = snapshot.list_tree(data["prefix"], limit=data["limit"])
            body = json.dumps(paths, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8", errors="surrogateescape"
            )
            records.append(_record(store, run_id, claim_id, "repository-list",
                                   snapshot.commit_id, body, {
                                       "prefix": data["prefix"],
                                       "snapshot_commit": snapshot.commit_id,
                                   }))
            aggregate += len(body)
        elif request.op == "READ_BLOB":
            try:
                body = snapshot.read_blob(data["path"], max_bytes=data["max_bytes"])
            except SnapshotUnavailable as exc:
                if "gitlinks are unavailable" in str(exc):
                    continue
                raise
            records.append(_record(store, run_id, claim_id, "repository-blob",
                                   data["path"], body,
                                   {"snapshot_commit": snapshot.commit_id, "path": data["path"]}))
            aggregate += len(body)
        elif request.op == "SEARCH_LITERAL":
            matches = snapshot.search_literal(data["pattern"], paths=data["paths"],
                                               limit=min(data["limit"], 50))
            body = json.dumps(matches, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8", errors="surrogateescape"
            )
            records.append(_record(store, run_id, claim_id, "repository-search",
                                   snapshot.commit_id, body,
                                   {"pattern": data["pattern"], "paths": data["paths"],
                                    "snapshot_commit": snapshot.commit_id}))
            aggregate += len(body)
        elif request.op == "HISTORY":
            rows = snapshot.history(data["ref"], data["path"], limit=data["limit"])
            body = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
            records.append(_record(
                store, run_id, claim_id, "repository-history", data["ref"], body,
                {"ref": data["ref"], "path": data["path"],
                 "snapshot_commit": snapshot.commit_id},
            ))
            aggregate += len(body)
        elif request.op == "RUN_ADAPTER":
            rows: list[dict[str, Any]] = []
            inputs: dict[str, str] = {}
            for path in data["paths"]:
                source = snapshot.read_blob(path, max_bytes=1 << 20)
                inputs[path] = hashlib.sha256(source).hexdigest()
                try:
                    compile(source, path, "exec")
                    rows.append({"path": path, "compiled": True, "error": None})
                except (SyntaxError, ValueError, TypeError) as exc:
                    rows.append({"path": path, "compiled": False,
                                 "error": f"{type(exc).__name__}: {exc}"[:1000]})
            body = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
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
            aggregate += len(body)
        else:
            if search_provider is None or http_client is None:
                # Absence is explicit abstention, never a fabricated evidence record.
                continue
            try:
                hits = search_provider.search(data["query"], limit=min(data["limit"], 2))
            except NetworkEvidenceError as exc:
                records.append(_abstention(claim_id, "external-search", data["query"], str(exc)))
                continue
            for hit in hits:
                if fetches >= MAX_FETCHES:
                    raise EvidenceRequestError("external fetch budget exceeded")
                try:
                    response = http_client.fetch(hit.url)
                except NetworkEvidenceError as exc:
                    records.append(_abstention(claim_id, "external-fetch", hit.url, str(exc)))
                    continue
                fetches += 1
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
                aggregate += len(response.body)
        if aggregate > MAX_AGGREGATE_BYTES:
            raise EvidenceRequestError("review evidence aggregate byte budget exceeded")
    return records


def collect_supplied_evidence(
    supplied: Sequence[Mapping[str, Any]], *, claims: pc.ClaimState,
    store: EvidenceStore, run_id: str,
) -> list[EvidenceRecord]:
    """Hash bounded caller artifacts and bind them to one exact registered claim."""
    if len(supplied) > 20:
        raise EvidenceRequestError("supplied_evidence exceeds 20 records")
    records: list[EvidenceRecord] = []
    total = 0
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
        total += len(body)
        if len(body) > 1 << 20 or total > MAX_AGGREGATE_BYTES:
            raise EvidenceRequestError("supplied evidence exceeds byte budget")
        records.append(_record(
            store, run_id, matches[0].claim_id, "supplied-artifact", source, body,
            {"source": source, "caller_supplied": True},
        ))
    return records


def _record(store: EvidenceStore, run_id: str, claim_id: str, kind: str, source: str,
            body: bytes, metadata: dict[str, Any]) -> EvidenceRecord:
    digest = store.stage(run_id, body)
    passage = body[:MAX_PASSAGE_BYTES]
    identity = hashlib.sha256(
        (claim_id + "\0" + kind + "\0" + source + "\0" + digest).encode(
            "utf-8", errors="surrogateescape"
        )
    ).hexdigest()[:12]
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


def _abstention(claim_id: str, kind: str, source: str, reason: str) -> EvidenceRecord:
    digest = hashlib.sha256((claim_id + "\0" + kind + "\0" + source + "\0" + reason).encode()).hexdigest()
    return EvidenceRecord(
        evidence_id="a" + digest[:12], claim_id=claim_id, kind="abstention",
        source=source, blob_digest=None, source_sha256=digest, source_size=0,
        passage_start=0, passage_end=0, passage_sha256=hashlib.sha256(b"").hexdigest(),
        display_passage="", metadata={"stage": kind, "reason": reason[:1000]},
    )


def render_evidence(records: Sequence[EvidenceRecord], *, include_passages: bool) -> str:
    lines = ["=== SERVER EVIDENCE RECORDS ==="]
    if not records:
        return lines[0] + "\nNONE — verification must abstain."
    for record in records:
        lines.append(
            f"[{record.evidence_id}] claim={record.claim_id} kind={record.kind} "
            f"source={record.source} sha256={record.source_sha256} bytes={record.source_size}"
        )
        if record.metadata:
            lines.append(
                "  metadata=" + json.dumps(
                    record.metadata, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False,
                )[:2000]
            )
        if include_passages:
            lines.append("  UNTRUSTED-DATA-BEGIN")
            lines.append("  " + record.display_passage.replace("\n", "\n  "))
            lines.append("  UNTRUSTED-DATA-END")
    return "\n".join(lines)


def records_to_json(records: Sequence[EvidenceRecord]) -> list[dict[str, Any]]:
    return [asdict(record) for record in records]


def records_from_json(rows: Sequence[Mapping[str, Any]]) -> list[EvidenceRecord]:
    return [EvidenceRecord(**dict(row)) for row in rows]


def validate_cached_records(
    records: Sequence[EvidenceRecord], *, snapshot: PlanRepositorySnapshot,
    store: EvidenceStore, state: pc.ClaimState, high_stakes: bool = False,
    now: datetime | None = None,
) -> list[EvidenceRecord]:
    """Revalidate identities/freshness and stale every claim that depended on a miss."""
    clock = now or datetime.now(timezone.utc)
    valid: list[EvidenceRecord] = []
    invalid_ids: set[str] = set()
    for record in records:
        try:
            if record.kind == "abstention":
                raise EvidenceRequestError("abstention records are round-local")
            if record.blob_digest:
                body = store.read(record.blob_digest)
                if hashlib.sha256(body).hexdigest() != record.source_sha256:
                    raise EvidenceRequestError("cached evidence source hash mismatch")
            if record.kind == "repository-blob":
                path = str(record.metadata["path"])
                current = snapshot.read_blob(path)
                if hashlib.sha256(current).hexdigest() != record.source_sha256:
                    raise EvidenceRequestError("repository evidence blob changed")
            elif record.kind.startswith("repository"):
                if record.metadata.get("snapshot_commit", snapshot.commit_id) != snapshot.commit_id:
                    raise EvidenceRequestError("repository query scope changed")
            elif record.kind == "empirical":
                if record.metadata.get("runtime") != sys.version:
                    raise EvidenceRequestError("empirical adapter runtime changed")
                for path, expected in record.metadata.get("input_hashes", {}).items():
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
        except (EvidenceRequestError, EvidenceStoreError, SnapshotUnavailable,
                KeyError, TypeError, ValueError):
            invalid_ids.add(record.evidence_id)
    if invalid_ids:
        for claim in state.claims.values():
            if invalid_ids.intersection(claim.evidence_ids):
                claim.status = pc.STALE
            info = claim.independent_check or {}
            if invalid_ids.intersection(info.get("evidence_ids", [])):
                info["status"] = "pending"
                claim.independent_check = info
    return valid


def _domain(url: str) -> str:
    from urllib.parse import urlsplit
    return urlsplit(url).hostname or ""
