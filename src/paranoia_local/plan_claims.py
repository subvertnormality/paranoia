"""Pure claim-closure core for plan review.

Only the terminal JSON registers are model-authored.  IDs, raw-byte anchors,
evidence identity, transition authorization, and the blocking verdict are
server-owned.  This module performs no I/O so the fail-closed rules can be
tested directly and mutation-tested cheaply.
"""

from __future__ import annotations

import copy
import base64
import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Iterable, Mapping, Sequence

RESEARCH_ROLE = "research"
VERIFIER_ROLE = "verifier"
STRUCTURAL_ROLE = "structural"

FACT, DECISION = "fact", "decision"
ASSERTED, ASSUMPTION, ESTIMATE = "asserted", "assumption", "estimate"
BLOCKING, ADVISORY = "blocking", "advisory"
PROPOSED, CONFIRMED = "proposed", "confirmed"
UNVERIFIED, VERIFIED, CONTRADICTED, DISPUTED, DEFERRED, STALE = (
    "unverified", "verified", "contradicted", "disputed", "deferred", "stale"
)
MALFORMED, UNCHECKED, NOT_APPLICABLE, SUPERSEDED = (
    "malformed", "unchecked", "not-applicable", "superseded"
)

RESEARCH_MARKER = "=== RESEARCH REGISTER ==="
VERIFICATION_MARKER = "=== VERIFICATION REGISTER ==="
PLAN_MARKER = "=== PLAN REGISTER ==="
EVENTS_PREFIX = "EVENTS-JSON: "

MAX_ACTIVE_CLAIMS = 50


class ClaimRegisterError(ValueError):
    """A model-authored register was absent, ambiguous, or malformed."""


class ClaimTransitionError(ClaimRegisterError):
    """A syntactically valid event was not authorized by current state."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class PlanSpan:
    span_id: str
    start: int
    end: int
    sha256: str
    display: str
    raw: bytes = field(repr=False)


@dataclass(frozen=True)
class ResolvedAnchor:
    first_span: str
    last_span: str
    start: int
    end: int
    sha256: str


def segment_plan(raw: bytes, *, max_span_bytes: int = 1024) -> list[PlanSpan]:
    """Mint ordered IDs over exact raw bytes while rendering bounded lossy text.

    Newlines are retained.  Oversized physical lines are split into bounded chunks.
    IDs encode order, not content, so identical/replacement-colliding displays remain
    unambiguous to the server and to a model looking at the numbered packet.
    """
    if max_span_bytes < 1:
        raise ValueError("max_span_bytes must be >= 1")
    pieces: list[bytes] = []
    for line in raw.splitlines(keepends=True):
        pieces.extend(line[i:i + max_span_bytes] for i in range(0, len(line), max_span_bytes))
    if not pieces and raw:
        pieces = [raw[i:i + max_span_bytes] for i in range(0, len(raw), max_span_bytes)]
    if not pieces:
        pieces = [b""]
    spans: list[PlanSpan] = []
    offset = 0
    for index, piece in enumerate(pieces, 1):
        end = offset + len(piece)
        spans.append(
            PlanSpan(
                span_id=f"p{index:06d}",
                start=offset,
                end=end,
                sha256=sha256(piece),
                display=piece.decode("utf-8", errors="replace"),
                raw=piece,
            )
        )
        offset = end
    return spans


def render_spans(spans: Sequence[PlanSpan]) -> str:
    return "\n".join(
        "SPAN=" + json.dumps(
            {"span_id": span.span_id, "display": span.display},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        )
        for span in spans
    )


def resolve_anchor(raw: Mapping[str, Any], spans: Sequence[PlanSpan]) -> ResolvedAnchor:
    if not isinstance(raw, Mapping):
        raise ClaimRegisterError("plan_anchor must be an object")
    if set(raw) != {"first_span", "last_span"}:
        raise ClaimRegisterError("plan_anchor needs exactly first_span and last_span")
    positions = {span.span_id: i for i, span in enumerate(spans)}
    first, last = raw.get("first_span"), raw.get("last_span")
    if not isinstance(first, str) or not isinstance(last, str):
        raise ClaimRegisterError("plan anchor span IDs must be strings")
    if first not in positions or last not in positions:
        raise ClaimRegisterError("plan anchor references an unknown server span")
    a, b = positions[first], positions[last]
    if a > b:
        raise ClaimRegisterError("plan anchor span range is reversed")
    chosen = spans[a:b + 1]
    # Segment construction is contiguous. Recheck rather than trusting callers that
    # injected a hand-built span list into the pure API.
    if any(left.end != right.start for left, right in zip(chosen, chosen[1:])):
        raise ClaimRegisterError("plan anchor span range is noncontiguous")
    range_hash = sha256(b"".join(span.raw for span in chosen))
    return ResolvedAnchor(first, last, chosen[0].start, chosen[-1].end, range_hash)


@dataclass(frozen=True)
class Event:
    op: str
    data: dict[str, Any]


@dataclass(frozen=True)
class VendorCheck:
    vendor: str
    model: str
    event_digest: str
    evidence_ids: tuple[str, ...]
    accepted: bool
    checked_at: str


@dataclass
class Claim:
    claim_id: str
    claim: str
    kind: str
    assertion_mode: str
    plan_anchor: ResolvedAnchor
    anchor_excerpt_b64: str
    origin_role: str
    first_round: int = 1
    bearing: str = BLOCKING
    kind_classification: str = PROPOSED
    status: str = UNCHECKED
    evidence_ids: list[str] = field(default_factory=list)
    truth_evidence_ids: list[str] = field(default_factory=list)
    bearing_evidence_ids: list[str] = field(default_factory=list)
    dispute_evidence_ids: list[str] = field(default_factory=list)
    reason: str | None = None
    deferral: dict[str, Any] | None = None
    disputed_evidence_ids: list[str] = field(default_factory=list)
    pending_replacement_id: str | None = None
    superseded_by: str | None = None
    truth_authorization: dict[str, Any] | None = None
    bearing_authorization: dict[str, Any] | None = None
    dispute_authorization: dict[str, Any] | None = None
    deferral_authorization: dict[str, Any] | None = None
    pending_transition: dict[str, Any] | None = None


@dataclass
class ClaimState:
    lineage_id: str
    next_seq: int = 1
    claims: dict[str, Claim] = field(default_factory=dict)
    debt: dict[str, Any] | None = None
    evidence_records: list[dict[str, Any]] = field(default_factory=list)
    plan_sha256: str | None = None
    authorization_policy: dict[str, Any] | None = None

    def copy(self) -> "ClaimState":
        return copy.deepcopy(self)


_SCHEMAS: dict[str, frozenset[str]] = {
    "ADD": frozenset({"op", "temp_id", "claim", "kind", "assertion_mode", "plan_anchor"}),
    "VERIFY": frozenset({"op", "claim_id", "evidence_ids", "reason"}),
    "CONTRADICT": frozenset({"op", "claim_id", "evidence_ids", "reason"}),
    "DEFER": frozenset({"op", "claim_id", "verification_anchor", "dependent_anchors",
                         "completion_evidence", "failure_condition", "stop_action"}),
    "DISPUTE": frozenset({"op", "claim_id", "evidence_ids", "reason"}),
    "RESOLVE_DISPUTE": frozenset({
        "op", "claim_id", "outcome", "evidence_ids", "reason",
    }),
    "SET_BEARING": frozenset({"op", "claim_id", "bearing", "evidence_ids", "reason"}),
    "CONFIRM_KIND": frozenset({"op", "claim_id", "kind", "reason"}),
    "SUPERSEDE": frozenset({"op", "claim_id", "replacement", "reason"}),
}

_ROLE_OPS = {
    RESEARCH_ROLE: frozenset({"ADD"}),
    STRUCTURAL_ROLE: frozenset({"ADD", "DISPUTE", "CONFIRM_KIND"}),
    VERIFIER_ROLE: frozenset(_SCHEMAS) - {"ADD", "DISPUTE"},
}


def _no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ClaimRegisterError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _marker_for(role: str) -> str:
    if role == RESEARCH_ROLE:
        return RESEARCH_MARKER
    if role == VERIFIER_ROLE:
        return VERIFICATION_MARKER
    if role == STRUCTURAL_ROLE:
        return PLAN_MARKER
    raise ClaimRegisterError(f"unknown register role {role!r}")


def parse_role_register(text: str, role: str) -> list[Event]:
    marker = _marker_for(role)
    if text.count(marker) != 1:
        raise ClaimRegisterError(f"expected exactly one {marker} block")
    tail = text.split(marker, 1)[1]
    line, sep, rest = tail.lstrip("\n").partition("\n")
    if not line.startswith(EVENTS_PREFIX):
        raise ClaimRegisterError(f"{marker} must be followed by {EVENTS_PREFIX.strip()}")
    # Research/verifier blocks own the tail. Structural parsing passes only the part
    # before CLASS REGISTER, so any remaining text is always malformed.
    if rest.strip():
        raise ClaimRegisterError("claim register has trailing data")
    payload = line[len(EVENTS_PREFIX):]
    try:
        raw = json.loads(payload, object_pairs_hook=_no_duplicate_pairs)
    except ClaimRegisterError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ClaimRegisterError(f"EVENTS-JSON is invalid: {exc}") from exc
    if not isinstance(raw, list):
        raise ClaimRegisterError("EVENTS-JSON must be an array")
    events: list[Event] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("op"), str):
            raise ClaimRegisterError("each claim event must be an object with string op")
        op = item["op"]
        if op not in _SCHEMAS:
            raise ClaimRegisterError(f"unknown claim event {op!r}")
        if op not in _ROLE_OPS[role]:
            raise ClaimRegisterError(f"role {role} may not emit {op}")
        actual, expected = set(item), set(_SCHEMAS[op])
        if actual != expected:
            extra, missing = sorted(actual - expected), sorted(expected - actual)
            detail = []
            if extra:
                detail.append(f"unknown fields {extra}")
            if missing:
                detail.append(f"missing fields {missing}")
            raise ClaimRegisterError(f"{op} has " + "; ".join(detail))
        _validate_scalars(op, item)
        events.append(Event(op, item))
    return events


def parse_structural_register(text: str, class_marker: str) -> tuple[list[Event], str]:
    if text.count(PLAN_MARKER) != 1 or text.count(class_marker) != 1:
        raise ClaimRegisterError("structural reply needs exactly one PLAN and CLASS register")
    if text.index(PLAN_MARKER) > text.index(class_marker):
        raise ClaimRegisterError("PLAN REGISTER must precede CLASS REGISTER")
    before, class_tail = text.split(class_marker, 1)
    events = parse_role_register(before.rstrip(), STRUCTURAL_ROLE)
    return events, class_marker + class_tail


def _validate_scalars(op: str, item: Mapping[str, Any]) -> None:
    for key, value in item.items():
        if key in {"plan_anchor", "replacement", "dependent_anchors", "evidence_ids",
                   "verification_anchor"}:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ClaimRegisterError(f"{op}.{key} must be a nonempty string")
    if "evidence_ids" in item and (
        not isinstance(item["evidence_ids"], list)
        or any(not isinstance(v, str) or not v for v in item["evidence_ids"])
    ):
        raise ClaimRegisterError(f"{op}.evidence_ids must be a string array")


def mint_claim_id(lineage_id: str, seq: int, proposition: str) -> str:
    return hashlib.sha256(f"{lineage_id}\0{seq}\0{proposition}".encode()).hexdigest()[:10]


def event_digest(event: Event) -> str:
    canonical = json.dumps(event.data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(canonical.encode())


def apply_events(
    state: ClaimState,
    events: Iterable[Event],
    *,
    role: str,
    spans: Sequence[PlanSpan],
    round_no: int = 1,
    evidence_ids: Mapping[str, str] | None = None,
    independent_required: bool = False,
    vendor_checks: Sequence[VendorCheck] = (),
) -> dict[str, str]:
    """Apply a role register to ``state``. Callers apply to a copied draft."""
    available = evidence_ids or {}
    minted: dict[str, str] = {}
    seen_temp: set[str] = set()
    for event in events:
        if event.op not in _ROLE_OPS.get(role, ()):
            raise ClaimTransitionError(f"role {role} may not emit {event.op}")
        data = event.data
        if event.op == "ADD":
            _add_claim(state, data, role, spans, round_no, minted, seen_temp)
            continue
        claim_id = data.get("claim_id")
        claim = state.claims.get(claim_id)
        if claim is None or claim.status == SUPERSEDED:
            raise ClaimTransitionError(f"unknown or superseded claim {claim_id!r}")
        if claim.pending_transition is not None and claim.pending_transition != data:
            raise ClaimTransitionError(
                "claim has a different independently authorized transition pending"
            )
        if event.op == "CONFIRM_KIND":
            if claim.kind_classification != PROPOSED:
                raise ClaimTransitionError("claim kind is already confirmed")
            if claim.origin_role == role:
                raise ClaimTransitionError("a role may not self-confirm its claim kind")
            kind = data["kind"]
            if kind not in {FACT, DECISION}:
                raise ClaimTransitionError("kind must be fact or decision")
            claim.kind, claim.kind_classification = kind, CONFIRMED
            claim.reason = data["reason"]
            claim.status = NOT_APPLICABLE if kind == DECISION else UNVERIFIED
        elif event.op in {"VERIFY", "CONTRADICT", "RESOLVE_DISPUTE", "SET_BEARING"}:
            ids = _validated_evidence(data, available, claim.claim_id)
            if event.op in {"VERIFY", "CONTRADICT"}:
                _require_fact(claim)
            elif event.op == "RESOLVE_DISPUTE" and claim.status != DISPUTED:
                raise ClaimTransitionError("only a disputed claim can resolve a dispute")
            elif event.op == "SET_BEARING":
                if data["bearing"] not in {BLOCKING, ADVISORY}:
                    raise ClaimTransitionError("bearing must be blocking or advisory")
                if data["bearing"] == ADVISORY and not ids:
                    raise ClaimTransitionError("advisory bearing requires evidence")
            if not _authorize_independent(
                claim, event, ids, independent_required, vendor_checks
            ):
                claim.pending_transition = copy.deepcopy(event.data)
                claim.reason = data["reason"]
                continue
            claim.pending_transition = None
            if event.op == "VERIFY":
                claim.status, claim.truth_evidence_ids = VERIFIED, ids
                _refresh_evidence_dependencies(claim)
            elif event.op == "CONTRADICT":
                claim.status, claim.truth_evidence_ids = CONTRADICTED, ids
                _refresh_evidence_dependencies(claim)
            elif event.op == "RESOLVE_DISPUTE":
                if data["outcome"] not in {VERIFIED, CONTRADICTED}:
                    raise ClaimTransitionError(
                        "dispute outcome must be verified or contradicted"
                    )
                claim.status = data["outcome"]
                claim.truth_evidence_ids = ids
                claim.dispute_evidence_ids = ids
                claim.disputed_evidence_ids = []
                _refresh_evidence_dependencies(claim)
            else:
                claim.bearing, claim.bearing_evidence_ids = data["bearing"], ids
                _refresh_evidence_dependencies(claim)
            claim.reason = data["reason"]
        elif event.op == "DISPUTE":
            _require_fact(claim)
            ids = _validated_evidence(data, available, claim.claim_id)
            claim.status, claim.disputed_evidence_ids = DISPUTED, ids
            claim.dispute_evidence_ids = ids
            _refresh_evidence_dependencies(claim)
            claim.reason = data["reason"]
        elif event.op == "DEFER":
            _require_fact(claim)
            if not _authorize_independent(
                claim, event, [], independent_required, vendor_checks
            ):
                claim.pending_transition = copy.deepcopy(event.data)
                continue
            claim.pending_transition = None
            verification = resolve_anchor(data["verification_anchor"], spans)
            dependents_raw = data["dependent_anchors"]
            if not isinstance(dependents_raw, list) or not dependents_raw:
                raise ClaimTransitionError("DEFER needs dependent_anchors")
            dependents = [resolve_anchor(anchor, spans) for anchor in dependents_raw]
            if any(verification.end > anchor.start for anchor in dependents):
                raise ClaimTransitionError("verification step must precede every dependency")
            claim.status = DEFERRED
            claim.deferral = {
                "verification_anchor": asdict(verification),
                "dependent_anchors": [asdict(a) for a in dependents],
                "completion_evidence": data["completion_evidence"],
                "failure_condition": data["failure_condition"],
                "stop_action": data["stop_action"],
                "plan_sha256": sha256(b"".join(span.raw for span in spans)),
            }
        elif event.op == "SUPERSEDE":
            if role != VERIFIER_ROLE:
                raise ClaimTransitionError("only verifier may propose supersession")
            replacement = data["replacement"]
            if not isinstance(replacement, dict):
                raise ClaimTransitionError("SUPERSEDE replacement must be an ADD object")
            replacement = {"op": "ADD", **replacement}
            if set(replacement) != set(_SCHEMAS["ADD"]):
                raise ClaimTransitionError("SUPERSEDE replacement must have ADD fields")
            local: dict[str, str] = {}
            _add_claim(state, replacement, role, spans, round_no, local, seen_temp)
            replacement_id = next(iter(local.values()))
            state.claims[replacement_id].bearing = BLOCKING
            claim.pending_replacement_id = replacement_id
            claim.reason = data["reason"]
        else:  # pragma: no cover - schema and role tables make this unreachable
            raise ClaimTransitionError(f"unhandled event {event.op}")
    _complete_supersessions(state)
    if len([c for c in state.claims.values() if c.status != SUPERSEDED]) > MAX_ACTIVE_CLAIMS:
        raise ClaimTransitionError(f"active claim cap exceeds {MAX_ACTIVE_CLAIMS}")
    return minted


def _add_claim(state: ClaimState, data: Mapping[str, Any], role: str,
               spans: Sequence[PlanSpan], round_no: int, minted: dict[str, str],
               seen_temp: set[str]) -> None:
    temp_id = data.get("temp_id")
    if not isinstance(temp_id, str) or not temp_id or temp_id in seen_temp:
        raise ClaimTransitionError("ADD temp_id must be nonempty and unique per register")
    proposition = data.get("claim")
    if not isinstance(proposition, str) or not proposition.strip():
        raise ClaimTransitionError("ADD claim must be nonempty")
    kind, assertion = data.get("kind"), data.get("assertion_mode")
    if kind not in {FACT, DECISION}:
        raise ClaimTransitionError("ADD kind must be fact or decision")
    if assertion not in {ASSERTED, ASSUMPTION, ESTIMATE}:
        raise ClaimTransitionError("invalid assertion_mode")
    anchor = resolve_anchor(data.get("plan_anchor", {}), spans)
    claim_id = mint_claim_id(state.lineage_id, state.next_seq, proposition)
    state.next_seq += 1
    state.claims[claim_id] = Claim(
        claim_id=claim_id, claim=proposition.strip(), kind=kind,
        assertion_mode=assertion, plan_anchor=anchor,
        anchor_excerpt_b64=base64.b64encode(_anchor_bytes(anchor, spans)).decode("ascii"),
        origin_role=role,
        first_round=round_no,
    )
    minted[temp_id] = claim_id
    seen_temp.add(temp_id)


def _validated_evidence(
    data: Mapping[str, Any], available: Mapping[str, str], claim_id: str
) -> list[str]:
    ids = list(dict.fromkeys(data.get("evidence_ids", [])))
    if not ids or any(available.get(item) != claim_id for item in ids):
        raise ClaimTransitionError(
            "transition evidence must exist and be bound to the exact claim"
        )
    return ids


def _require_fact(claim: Claim) -> None:
    if claim.kind_classification != CONFIRMED or claim.kind != FACT:
        raise ClaimTransitionError("truth transitions require a confirmed factual claim")


def _authorize_independent(claim: Claim, event: Event, evidence_ids: list[str],
                           required: bool, checks: Sequence[VendorCheck]) -> bool:
    slot = (
        "bearing_authorization" if event.op == "SET_BEARING"
        else "dispute_authorization" if event.op == "RESOLVE_DISPUTE"
        else "deferral_authorization" if event.op == "DEFER"
        else "truth_authorization"
    )
    if not required:
        setattr(claim, slot, {
            "required": False, "status": "not-required",
            "event_digest": event_digest(event), "event": copy.deepcopy(event.data),
            "evidence_ids": evidence_ids, "checks": [],
        })
        return True
    digest = event_digest(event)
    matching = [
        check for check in checks
        if check.accepted and check.event_digest == digest
        and tuple(evidence_ids) == check.evidence_ids
    ]
    vendors = {check.vendor for check in matching}
    authorization = {
        "required": True,
        "status": "complete" if len(vendors) >= 2 else "pending",
        "event_digest": digest,
        "event": copy.deepcopy(event.data),
        "evidence_ids": evidence_ids,
        "checks": [asdict(check) for check in matching],
    }
    setattr(claim, slot, authorization)
    if event.op == "RESOLVE_DISPUTE":
        claim.truth_authorization = copy.deepcopy(authorization)
    return len(vendors) >= 2


def _complete_supersessions(state: ClaimState) -> None:
    for claim in state.claims.values():
        target = state.claims.get(claim.pending_replacement_id or "")
        if target and target.status in {VERIFIED, DEFERRED} and target.kind_classification == CONFIRMED:
            claim.status, claim.superseded_by = SUPERSEDED, target.claim_id


def _authorization_valid(info: dict[str, Any] | None, *, must_be_required: bool = False) -> bool:
    if not info:
        return not must_be_required
    if not info.get("required"):
        return not must_be_required and info.get("status") == "not-required"
    if info.get("status") != "complete":
        return False
    digest, evidence = info.get("event_digest"), tuple(info.get("evidence_ids", []))
    checks = info.get("checks", [])
    vendors = {
        item.get("vendor") for item in checks
        if item.get("accepted") is True and item.get("event_digest") == digest
        and tuple(item.get("evidence_ids", [])) == evidence
    }
    return None not in vendors and len(vendors) >= 2


def claim_blocks(claim: Claim) -> bool:
    if claim.status == SUPERSEDED:
        return False
    if claim.pending_transition is not None:
        return True
    if claim.kind_classification != CONFIRMED:
        return True
    if claim.kind == DECISION:
        return claim.status != NOT_APPLICABLE
    if claim.bearing == ADVISORY:
        return not _authorization_valid(claim.bearing_authorization, must_be_required=True)
    if claim.status == VERIFIED:
        return not _authorization_valid(claim.truth_authorization)
    if claim.status == DEFERRED:
        return not _authorization_valid(claim.deferral_authorization)
    return True


def _refresh_evidence_dependencies(claim: Claim) -> None:
    claim.evidence_ids = list(dict.fromkeys([
        *claim.truth_evidence_ids,
        *claim.bearing_evidence_ids,
        *claim.dispute_evidence_ids,
        *claim.disputed_evidence_ids,
    ]))


def blocking_claims(state: ClaimState) -> list[Claim]:
    return [claim for claim in state.claims.values() if claim_blocks(claim)]


def reconcile_plan(state: ClaimState, raw: bytes, spans: Sequence[PlanSpan]) -> None:
    """Relocate exact claim excerpts; ambiguity or deletion invalidates safely."""
    for claim in state.claims.values():
        if claim.status == SUPERSEDED:
            continue
        try:
            excerpt = base64.b64decode(claim.anchor_excerpt_b64, validate=True)
        except (ValueError, TypeError):
            claim.status = STALE
            continue
        offsets: list[int] = []
        start = 0
        while True:
            found = raw.find(excerpt, start)
            if found < 0:
                break
            offsets.append(found)
            start = found + 1
            if len(offsets) > 1:
                break
        if len(offsets) != 1:
            claim.status = STALE
            continue
        begin, end = offsets[0], offsets[0] + len(excerpt)
        chosen = [span for span in spans if span.end > begin and span.start < end]
        if not chosen:
            claim.status = STALE
            continue
        claim.plan_anchor = ResolvedAnchor(
            chosen[0].span_id, chosen[-1].span_id, begin, end, sha256(excerpt)
        )
        # Deferred dependencies have their own exact ordering contract. Until all of
        # those excerpts are independently relocatable, any plan edit invalidates them.
        if claim.status == DEFERRED and claim.deferral and claim.deferral.get("plan_sha256") != sha256(raw):
            claim.status = STALE


def _anchor_bytes(anchor: ResolvedAnchor, spans: Sequence[PlanSpan]) -> bytes:
    positions = {span.span_id: i for i, span in enumerate(spans)}
    return b"".join(
        span.raw for span in spans[
            positions[anchor.first_span]:positions[anchor.last_span] + 1
        ]
    )


def state_to_json(state: ClaimState) -> dict[str, Any]:
    return {
        "next_seq": state.next_seq,
        "claims": [
            {
                **asdict(claim),
                "plan_anchor": asdict(claim.plan_anchor),
            }
            for claim in state.claims.values()
        ],
        "debt": state.debt,
        "evidence_records": state.evidence_records,
        "plan_sha256": state.plan_sha256,
        "authorization_policy": state.authorization_policy,
    }


def state_from_json(lineage_id: str, raw: Mapping[str, Any] | None) -> ClaimState:
    if raw is None:
        return ClaimState(lineage_id)
    if not isinstance(raw, Mapping):
        raise ClaimRegisterError("claim state must be an object")
    allowed = {
        "next_seq", "claims", "debt", "evidence_records", "plan_sha256",
        "authorization_policy",
    }
    if not set(raw).issubset(allowed):
        raise ClaimRegisterError("claim state has unknown fields")
    next_seq = raw.get("next_seq", 1)
    if not isinstance(next_seq, int) or isinstance(next_seq, bool) or next_seq < 1:
        raise ClaimRegisterError("claim state next_seq must be a positive integer")
    rows = raw.get("claims", [])
    if not isinstance(rows, list) or len(rows) > MAX_ACTIVE_CLAIMS * 4:
        raise ClaimRegisterError("claim state claims must be a bounded array")
    claims: dict[str, Claim] = {}
    expected_claim_fields = {item.name for item in fields(Claim)}
    for item in rows:
        if not isinstance(item, Mapping) or set(item) != expected_claim_fields:
            raise ClaimRegisterError("persisted claim has missing or unknown fields")
        row = dict(item)
        anchor = row.get("plan_anchor")
        if not isinstance(anchor, Mapping) or set(anchor) != {
            "first_span", "last_span", "start", "end", "sha256"
        }:
            raise ClaimRegisterError("persisted claim anchor is malformed")
        if (
            not all(isinstance(anchor.get(key), str) and anchor.get(key)
                    for key in ("first_span", "last_span"))
            or not isinstance(anchor.get("start"), int)
            or isinstance(anchor.get("start"), bool)
            or not isinstance(anchor.get("end"), int)
            or isinstance(anchor.get("end"), bool)
            or anchor["start"] < 0 or anchor["end"] < anchor["start"]
            or not isinstance(anchor.get("sha256"), str)
            or not _digest(anchor["sha256"])
        ):
            raise ClaimRegisterError("persisted claim anchor values are malformed")
        row["plan_anchor"] = ResolvedAnchor(**anchor)
        _validate_persisted_claim(row)
        claim = Claim(**row)
        if claim.claim_id in claims:
            raise ClaimRegisterError("persisted claim IDs must be unique")
        claims[claim.claim_id] = claim
    debt = raw.get("debt")
    if debt is not None and not isinstance(debt, dict):
        raise ClaimRegisterError("claim state debt must be an object or null")
    evidence_records = raw.get("evidence_records", [])
    if not isinstance(evidence_records, list) or any(
        not isinstance(item, Mapping) for item in evidence_records
    ):
        raise ClaimRegisterError("claim evidence records must be an object array")
    plan_sha = raw.get("plan_sha256")
    if plan_sha is not None and (not isinstance(plan_sha, str) or not _digest(plan_sha)):
        raise ClaimRegisterError("claim plan_sha256 is malformed")
    policy = raw.get("authorization_policy")
    if policy is not None and (
        not isinstance(policy, dict)
        or set(policy) != {"version", "independent_check", "high_stakes"}
        or policy.get("version") != 1
        or policy.get("independent_check") not in {"auto", "require"}
        or not isinstance(policy.get("high_stakes"), bool)
    ):
        raise ClaimRegisterError("claim authorization policy is malformed")
    for claim in claims.values():
        if claim.kind_classification == PROPOSED and claim.status != UNCHECKED:
            raise ClaimRegisterError("proposed persisted claim has unreachable status")
        if claim.kind_classification == CONFIRMED and claim.kind == DECISION \
                and claim.status not in {NOT_APPLICABLE, STALE, DISPUTED, SUPERSEDED}:
            raise ClaimRegisterError("confirmed persisted decision has unreachable status")
        if claim.kind_classification == CONFIRMED and claim.kind == FACT \
                and claim.status == NOT_APPLICABLE:
            raise ClaimRegisterError("confirmed persisted fact has unreachable status")
        if claim.status == SUPERSEDED:
            target = claims.get(claim.superseded_by or "")
            if claim.pending_replacement_id != claim.superseded_by or target is None \
                    or target.claim_id == claim.claim_id \
                    or target.kind_classification != CONFIRMED \
                    or target.status not in {VERIFIED, DEFERRED}:
                raise ClaimRegisterError("persisted supersession graph is inconsistent")
        elif claim.superseded_by is not None:
            raise ClaimRegisterError("active persisted claim has a superseded target")
    return ClaimState(
        lineage_id, next_seq, claims, debt,
        list(evidence_records), plan_sha, policy,
    )


def _digest(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _validate_persisted_claim(row: Mapping[str, Any]) -> None:
    for key in ("claim_id", "claim", "anchor_excerpt_b64", "origin_role"):
        if not isinstance(row.get(key), str) or (key != "anchor_excerpt_b64" and not row[key]):
            raise ClaimRegisterError(f"persisted claim {key} is malformed")
    try:
        base64.b64decode(row["anchor_excerpt_b64"], validate=True)
    except (ValueError, TypeError) as exc:
        raise ClaimRegisterError("persisted claim anchor excerpt is malformed") from exc
    if row.get("kind") not in {FACT, DECISION}:
        raise ClaimRegisterError("persisted claim kind is malformed")
    if row.get("assertion_mode") not in {ASSERTED, ASSUMPTION, ESTIMATE}:
        raise ClaimRegisterError("persisted assertion mode is malformed")
    if row.get("origin_role") not in {RESEARCH_ROLE, VERIFIER_ROLE, STRUCTURAL_ROLE}:
        raise ClaimRegisterError("persisted origin role is malformed")
    if row.get("bearing") not in {BLOCKING, ADVISORY}:
        raise ClaimRegisterError("persisted bearing is malformed")
    if row.get("kind_classification") not in {PROPOSED, CONFIRMED}:
        raise ClaimRegisterError("persisted kind classification is malformed")
    if row.get("status") not in {
        UNVERIFIED, VERIFIED, CONTRADICTED, DISPUTED, DEFERRED, STALE,
        MALFORMED, UNCHECKED, NOT_APPLICABLE, SUPERSEDED,
    }:
        raise ClaimRegisterError("persisted status is malformed")
    first_round = row.get("first_round")
    if not isinstance(first_round, int) or isinstance(first_round, bool) or first_round < 1:
        raise ClaimRegisterError("persisted first_round is malformed")
    for key in (
        "evidence_ids", "truth_evidence_ids", "bearing_evidence_ids",
        "dispute_evidence_ids", "disputed_evidence_ids",
    ):
        value = row.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise ClaimRegisterError(f"persisted {key} is malformed")
    for key in ("reason", "pending_replacement_id", "superseded_by"):
        value = row.get(key)
        if value is not None and not isinstance(value, str):
            raise ClaimRegisterError(f"persisted {key} is malformed")
    for key in (
        "deferral", "truth_authorization", "bearing_authorization",
        "dispute_authorization", "deferral_authorization", "pending_transition",
    ):
        value = row.get(key)
        if value is not None and not isinstance(value, dict):
            raise ClaimRegisterError(f"persisted {key} is malformed")
    if row.get("status") == DEFERRED:
        deferral = row.get("deferral")
        if not isinstance(deferral, dict) or set(deferral) != {
            "verification_anchor", "dependent_anchors", "completion_evidence",
            "failure_condition", "stop_action", "plan_sha256",
        }:
            raise ClaimRegisterError("persisted deferral is malformed")
        if not isinstance(deferral.get("dependent_anchors"), list) \
                or not deferral["dependent_anchors"]:
            raise ClaimRegisterError("persisted deferral dependencies are malformed")
        anchors = [deferral.get("verification_anchor"), *deferral["dependent_anchors"]]
        if any(not _persisted_anchor(anchor) for anchor in anchors):
            raise ClaimRegisterError("persisted deferral anchor is malformed")
        if not isinstance(deferral.get("plan_sha256"), str) or not _digest(deferral["plan_sha256"]):
            raise ClaimRegisterError("persisted deferral plan digest is malformed")
        if any(not isinstance(deferral.get(key), str) or not deferral[key]
               for key in ("completion_evidence", "failure_condition", "stop_action")):
            raise ClaimRegisterError("persisted deferral rule is malformed")
    if row.get("status") in {VERIFIED, CONTRADICTED} and not row.get("truth_evidence_ids"):
        raise ClaimRegisterError("persisted truth transition has no evidence")
    if row.get("bearing") == ADVISORY and not row.get("bearing_evidence_ids"):
        raise ClaimRegisterError("persisted advisory claim has no evidence")
    if row.get("status") in {VERIFIED, CONTRADICTED} \
            and row.get("truth_authorization") is None:
        raise ClaimRegisterError("persisted truth transition has no authorization")
    if row.get("bearing") == ADVISORY and row.get("bearing_authorization") is None:
        raise ClaimRegisterError("persisted advisory claim has no authorization")
    if row.get("status") == DEFERRED and row.get("deferral_authorization") is None:
        raise ClaimRegisterError("persisted deferral has no authorization")
    retained = list(dict.fromkeys([
        *row["truth_evidence_ids"], *row["bearing_evidence_ids"],
        *row["dispute_evidence_ids"], *row["disputed_evidence_ids"],
    ]))
    if row.get("evidence_ids") != retained:
        raise ClaimRegisterError("persisted claim evidence dependency union is inconsistent")
    pending = row.get("pending_transition")
    if pending is not None:
        if not isinstance(pending.get("op"), str) or pending["op"] not in _SCHEMAS \
                or set(pending) != set(_SCHEMAS[pending["op"]]):
            raise ClaimRegisterError("persisted pending transition is malformed")
        _validate_scalars(pending["op"], pending)
    for authorization_key in (
        "truth_authorization", "bearing_authorization", "dispute_authorization",
        "deferral_authorization",
    ):
        info = row.get(authorization_key)
        if info is None:
            continue
        allowed = {
            "required", "status", "event_digest", "event", "evidence_ids", "checks", "reason",
        }
        if not set(info).issubset(allowed) or not isinstance(info.get("required"), bool) \
                or info.get("status") not in {"not-required", "pending", "complete"}:
            raise ClaimRegisterError("persisted independent authorization is malformed")
        if (info["required"] and info["status"] == "not-required") \
                or (not info["required"] and info["status"] != "not-required") \
                or ("reason" in info and not isinstance(info["reason"], str)):
            raise ClaimRegisterError("persisted independent authorization state is inconsistent")
        ids = info.get("evidence_ids", [])
        checks = info.get("checks", [])
        digest = info.get("event_digest")
        event = info.get("event")
        if not isinstance(digest, str) or not _digest(digest) \
                or not isinstance(event, dict) \
                or hashlib.sha256(json.dumps(
                    event, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()).hexdigest() != digest \
                or not isinstance(ids, list) \
                or any(not isinstance(item, str) or not item for item in ids) \
                or not isinstance(checks, list):
            raise ClaimRegisterError("persisted independent authorization inputs are malformed")
        slot_ops = {
            "truth_authorization": {"VERIFY", "CONTRADICT"},
            "bearing_authorization": {"SET_BEARING"},
            "dispute_authorization": {"RESOLVE_DISPUTE"},
            "deferral_authorization": {"DEFER"},
        }
        if event.get("op") not in slot_ops[authorization_key] \
                or event.get("claim_id") != row.get("claim_id") \
                or list(dict.fromkeys(event.get("evidence_ids", []))) != ids:
            raise ClaimRegisterError("persisted authorization is bound to the wrong transition")
        if not info["required"] and checks:
            raise ClaimRegisterError("non-required authorization may not retain vendor checks")
        for check in checks:
            if not isinstance(check, dict) or set(check) != {
                "vendor", "model", "event_digest", "evidence_ids", "accepted", "checked_at"
            }:
                raise ClaimRegisterError("persisted vendor check is malformed")
            if any(not isinstance(check.get(key), str) or not check[key]
                   for key in ("vendor", "model", "event_digest", "checked_at")) \
                    or not _digest(check["event_digest"]) \
                    or not isinstance(check.get("evidence_ids"), (list, tuple)) \
                    or any(not isinstance(item, str) or not item for item in check["evidence_ids"]) \
                    or not isinstance(check.get("accepted"), bool):
                raise ClaimRegisterError("persisted vendor check values are malformed")


def _persisted_anchor(anchor: Any) -> bool:
    return isinstance(anchor, Mapping) and set(anchor) == {
        "first_span", "last_span", "start", "end", "sha256"
    } and all(isinstance(anchor.get(key), str) and anchor[key]
              for key in ("first_span", "last_span")) \
        and isinstance(anchor.get("start"), int) and not isinstance(anchor.get("start"), bool) \
        and isinstance(anchor.get("end"), int) and not isinstance(anchor.get("end"), bool) \
        and anchor["start"] >= 0 and anchor["end"] >= anchor["start"] \
        and isinstance(anchor.get("sha256"), str) and _digest(anchor["sha256"])


def render_claim_summary(state: ClaimState) -> str:
    lines = ["=== ACTIVE CLAIMS ==="]
    for claim in state.claims.values():
        if claim.status == SUPERSEDED:
            continue
        lines.append(
            "CLAIM=" + json.dumps(
                {
                    "claim_id": claim.claim_id,
                    "claim": claim.claim,
                    "kind": claim.kind,
                    "kind_classification": claim.kind_classification,
                    "bearing": claim.bearing,
                    "status": claim.status,
                    "evidence_ids": claim.evidence_ids,
                    "pending_transition": claim.pending_transition,
                    "pending_authorizations": {
                        name: info.get("event") for name, info in {
                            "truth": claim.truth_authorization,
                            "bearing": claim.bearing_authorization,
                            "dispute": claim.dispute_authorization,
                            "deferral": claim.deferral_authorization,
                        }.items() if info and info.get("status") == "pending"
                    },
                },
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            )
        )
    if len(lines) == 1:
        lines.append("NONE")
    return "\n".join(lines)
