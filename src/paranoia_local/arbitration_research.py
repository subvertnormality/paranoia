"""Pure parsing and normalization for bounded pre-vote research."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Sequence

from . import external_sources as sources


def _unfence(raw: str) -> str:
    """Narrowly unwrap an optional JSON markdown fence."""
    if not raw.startswith("```"):
        return raw
    newline = raw.find("\n")
    if newline == -1:
        return raw
    language = raw[3:newline].strip()
    if language and not language.isidentifier():
        return raw
    closing = raw.rfind("```")
    if closing <= newline:
        return raw
    return raw[newline + 1:closing].strip()


DISCOVERY_MARKER = "=== RESEARCH DISCOVERY JSON ==="
BINDING_MARKER = "=== EVIDENCE BINDING JSON ==="
CLAIM_KINDS = frozenset({"fact", "design_principle", "behavior"})
MAX_CLAIMS_PER_RESEARCHER = 12
MAX_PROPOSITION_CHARS = 1200
MAX_BINDING_INPUT_CHARS = 400_000
MAX_UNION_PACKETS = 24
MAX_UNION_CHARS = 200_000


class ResearchError(ValueError):
    pass


@dataclass(frozen=True)
class DiscoveryClaim:
    kind: str
    proposition: str
    candidate: sources.CandidateSource


@dataclass(frozen=True)
class Packet:
    packet_id: str
    kind: str
    proposition: str
    source: sources.BoundSource

    @property
    def governing(self) -> bool:
        return self.source.governing


def _one_line(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchError(f"{field} must be a non-empty string")
    text = " ".join(value.split())
    if len(text) > limit:
        raise ResearchError(f"{field} exceeds {limit} characters")
    return text


def _json_after(text: str, marker: str) -> object:
    if text.count(marker) != 1:
        raise ResearchError(f"expected exactly one {marker!r} marker")
    # Engines intermittently wrap the object in a markdown fence despite the
    # prompt asking for bare JSON, and `raw_decode` stops at the first backtick.
    # Measured 2026-08-13: two arbitrations failed here with `ROUNDS: 0`, so the
    # deciders never voted and the run was lost to formatting. Same tolerance,
    # same helper, as the settlement and lane parsers.
    tail = _unfence(text.split(marker, 1)[1].strip())
    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(tail)
    except json.JSONDecodeError as exc:
        # Claude has repeatedly emitted a complete binding array while omitting
        # only the outer object's final `}` — including on the one permitted
        # correction. Accept that single mechanically unambiguous truncation;
        # schema and exact-row validation still run below. Do not guess at an
        # internal quote, comma, bracket, or any multi-character repair.
        if tail.startswith("{") and not tail.endswith("}"):
            try:
                value, end = decoder.raw_decode(tail + "}")
                tail += "}"
            except json.JSONDecodeError:
                raise ResearchError(f"invalid JSON after {marker}: {exc}") from exc
        else:
            raise ResearchError(f"invalid JSON after {marker}: {exc}") from exc
    if tail[end:].strip():
        raise ResearchError(f"unexpected text after {marker} JSON")
    return value


def parse_discovery(text: str, *, forbidden: Iterable[str] = ()) -> tuple[DiscoveryClaim, ...]:
    value = _json_after(text, DISCOVERY_MARKER)
    if not isinstance(value, dict) or set(value) != {"claims"}:
        raise ResearchError("discovery must contain exactly a claims array")
    raw_claims = value["claims"]
    if not isinstance(raw_claims, list) or len(raw_claims) > MAX_CLAIMS_PER_RESEARCHER:
        raise ResearchError(f"claims must contain at most {MAX_CLAIMS_PER_RESEARCHER} items")
    blocked = tuple(token for token in forbidden if token)
    claims: list[DiscoveryClaim] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_claims):
        if not isinstance(item, dict) or set(item) != {"kind", "proposition", "candidate"}:
            raise ResearchError(f"claim {index} has invalid fields")
        kind = item["kind"]
        if kind not in CLAIM_KINDS:
            raise ResearchError(f"claim {index} kind must be one of {sorted(CLAIM_KINDS)}")
        proposition = _one_line(item["proposition"], "proposition", MAX_PROPOSITION_CHARS)
        normalized = sources.normalize_text(proposition).casefold()
        if normalized in seen:
            raise ResearchError(f"duplicate normalized proposition at claim {index}")
        seen.add(normalized)
        if any(token in proposition for token in blocked):
            raise ResearchError(f"claim {index} leaks a reserved option token")
        raw_source = item["candidate"]
        required = {"url", "title", "publisher", "source_kind", "authority_basis", "relation"}
        if not isinstance(raw_source, dict) or set(raw_source) != required:
            raise ResearchError(f"claim {index} candidate fields are invalid")
        candidate = sources.normalize_candidate(sources.CandidateSource(
            url=_one_line(raw_source["url"], "url", 2048),
            title=_one_line(raw_source["title"], "title", 400),
            publisher=_one_line(raw_source["publisher"], "publisher", 200),
            source_kind=_one_line(raw_source["source_kind"], "source_kind", 30),
            authority_basis=_one_line(raw_source["authority_basis"], "authority_basis", 600),
            relation=_one_line(raw_source["relation"], "relation", 40),
        ))
        claims.append(DiscoveryClaim(kind, proposition, candidate))
    return tuple(claims)


def binding_input(claims: Sequence[DiscoveryClaim], captures: Sequence[sources.Capture]) -> str:
    if len(claims) != len(captures):
        raise ResearchError("capture count does not match discovery count")
    rows: list[dict[str, object]] = []
    seen_captures: dict[tuple[str | None, str | None, str | None], int] = {}
    for index, (claim, capture) in enumerate(zip(claims, captures, strict=True)):
        identity = (capture.final_url, capture.content_sha256, capture.text_sha256)
        referenceable = capture.usable and all(identity)
        capture_ref = seen_captures.get(identity) if referenceable else None
        if referenceable and capture_ref is None:
            seen_captures[identity] = index
        rows.append({
            "claim_index": index,
            "proposition": claim.proposition,
            "candidate": {
                "url": claim.candidate.url,
                "title": claim.candidate.title,
                "publisher": claim.candidate.publisher,
                "source_kind": claim.candidate.source_kind,
                "authority_basis": claim.candidate.authority_basis,
                "relation": claim.candidate.relation,
            },
            "capture": {
                "usable": capture.usable,
                "final_url": capture.final_url,
                "status": capture.status,
                "content_type": capture.content_type,
                "content_sha256": capture.content_sha256,
                "text_sha256": capture.text_sha256,
                "error": capture.error,
                "fallback_attempted": capture.fallback_attempted,
                "capture_ref": capture_ref,
                "capture_ref_semantics": (
                    "non-null names an earlier claim_index in this input with identical "
                    "final URL and content/text digests; use that row's line-numbered text"
                ),
                "line_numbered_text": (
                    "" if capture_ref is not None
                    else sources.numbered_text(capture.text or "")
                ),
            },
        })
    rendered = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    if len(rendered) > MAX_BINDING_INPUT_CHARS:
        raise ResearchError(f"binding input exceeds {MAX_BINDING_INPUT_CHARS} characters")
    return rendered


def parse_binding(
    text: str,
    claims: Sequence[DiscoveryClaim],
    captures: Sequence[sources.Capture],
) -> tuple[sources.BoundSource | None, ...]:
    value = _json_after(text, BINDING_MARKER)
    if not isinstance(value, dict) or set(value) != {"bindings"}:
        raise ResearchError("binding must contain exactly a bindings array")
    raw_bindings = value["bindings"]
    if not isinstance(raw_bindings, list) or len(raw_bindings) != len(claims):
        raise ResearchError("binding must return exactly one item per discovery claim")
    bound: list[sources.BoundSource | None] = [None] * len(claims)
    seen: set[int] = set()
    for item in raw_bindings:
        if not isinstance(item, dict) or set(item) != {"claim_index", "usable", "location", "passage"}:
            raise ResearchError("binding item fields are invalid")
        index = item["claim_index"]
        if not isinstance(index, int) or not 0 <= index < len(claims) or index in seen:
            raise ResearchError("binding claim_index is invalid or duplicated")
        seen.add(index)
        usable = item["usable"]
        if not isinstance(usable, bool):
            raise ResearchError("binding usable must be boolean")
        if not usable:
            if item["location"] is not None or item["passage"] is not None:
                raise ResearchError("unusable binding must have null location and passage")
            continue
        capture = captures[index]
        if not capture.usable or not capture.text:
            raise ResearchError("binding marked an unavailable capture usable")
        location = _one_line(item["location"], "location", 400)
        passage = _one_line(item["passage"], "passage", 1200)
        if not sources.passage_matches(passage, capture.text):
            raise ResearchError(f"binding passage for claim {index} is not in captured text")
        bound[index] = sources.BoundSource(claims[index].candidate, capture, location, passage)
    if seen != set(range(len(claims))):
        raise ResearchError("binding omitted a discovery claim")
    return tuple(bound)


def packets(
    producers: Sequence[
        tuple[Sequence[DiscoveryClaim], Sequence[sources.BoundSource | None]]
    ],
) -> tuple[Packet, ...]:
    rows: dict[tuple[str, str], Packet] = {}
    per_proposition: dict[str, int] = {}
    for claims, bound in producers:
        if len(claims) != len(bound):
            raise ResearchError("bound result count does not match discovery claims")
        for claim, source in zip(claims, bound, strict=True):
            if source is None:
                continue
            pid = sources.packet_id(claim.proposition, source)
            key = (sources.normalize_text(claim.proposition).casefold(), pid)
            if key in rows:
                continue
            count = per_proposition.get(key[0], 0)
            if count == 2:
                continue
            per_proposition[key[0]] = count + 1
            rows[key] = Packet(pid, claim.kind, sources.normalize_text(claim.proposition), source)
    result = tuple(rows[key] for key in sorted(rows))
    if len(result) > MAX_UNION_PACKETS:
        raise ResearchError(f"packet union exceeds {MAX_UNION_PACKETS} entries")
    rendered = render(result)
    if len(rendered) > MAX_UNION_CHARS:
        raise ResearchError(f"packet union exceeds {MAX_UNION_CHARS} characters")
    return result


def render(items: Sequence[Packet]) -> str:
    rows = []
    for packet in items:
        source = packet.source
        rows.append({
            "packet_id": packet.packet_id,
            "kind": packet.kind,
            "proposition": packet.proposition,
            "governing_eligible": packet.governing,
            "source": {
                "url": source.capture.final_url or source.candidate.url,
                "title": source.candidate.title,
                "publisher": source.candidate.publisher,
                "source_kind": source.candidate.source_kind,
                "authority_basis": source.candidate.authority_basis,
                "relation": source.candidate.relation,
                "location": source.location,
                "passage": source.passage,
                "content_sha256": source.capture.content_sha256,
                "text_sha256": source.capture.text_sha256,
            },
        })
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(items: Sequence[Packet]) -> str:
    # Model-controlled fields can contain lone surrogates. JSON can represent them,
    # and audit logging escapes them; the digest must remain total on the same bytes
    # instead of making the failure serializer fail while reporting their rejection.
    return hashlib.sha256(render(items).encode("utf-8", "surrogatepass")).hexdigest()
