"""Atomic factual-claim verification for plan reviews.

This module deliberately has a small job: parse one model-produced claim audit,
validate that its verdicts are backed by suitable evidence, reconcile it with the
previous round, and render actionable packets.  The reviewer CLI supplies repository
access and its built-in web search; there is no search-provider abstraction here.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse


AUDIT_MARKER = "=== CLAIM AUDIT JSON ==="
MAX_ACTIVE_CLAIMS = 500
MAX_EVIDENCE_PER_CLAIM = 20
DIAGNOSTIC_CHARS = 4000

VERDICTS = frozenset({"supported", "refuted", "unverified"})
SCOPES = frozenset({"external", "repository"})
SOURCE_KINDS = frozenset(
    {"primary", "authoritative", "secondary", "ugc", "repository"}
)
RELATIONS = frozenset(
    {"supports_claim", "refutes_claim", "supports_replacement", "context"}
)
AUTHORITATIVE_KINDS = frozenset({"primary", "authoritative"})

# These sources can be useful discovery leads, but cannot become authoritative merely
# because a model labels them "primary".  This is intentionally a narrow deny-list of
# unambiguously user-generated/community platforms, not a pretend universal authority
# classifier.
UGC_HOSTS = (
    "reddit.com", "quora.com", "stackoverflow.com", "stackexchange.com",
    "medium.com", "substack.com", "x.com", "twitter.com", "facebook.com",
    "instagram.com", "tiktok.com", "youtube.com", "wikipedia.org",
)


class AuditError(ValueError):
    """The claim audit is absent, malformed, or makes an unsupported transition."""

    def __init__(self, reason: str, raw: str = "") -> None:
        self.reason = reason
        self.raw_sha256 = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()
        self.excerpt = _excerpt(raw)
        super().__init__(reason)

    def debt(self, round_no: int) -> dict[str, Any]:
        return {
            "round": round_no,
            "reason": self.reason,
            "raw_sha256": self.raw_sha256,
            "rejected_excerpt": self.excerpt,
        }


@dataclass(frozen=True)
class Audit:
    claims: tuple[dict[str, Any], ...]
    coverage: dict[str, Any]


def empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "rounds": 0,
        "next_seq": 1,
        "plan_digest": None,
        "claims": {},
        "retired": [],
        "debt": None,
    }


def normalize_state(raw: Any) -> dict[str, Any]:
    """Return a defensive, schema-light copy of persisted state.

    Full record validation happens when records are used.  Keeping migration here small
    prevents plan-claim evolution from becoming a second persistence framework.
    """
    state = empty_state()
    if not isinstance(raw, dict):
        return state
    if raw.get("version") != 1:
        return state
    state.update({
        "rounds": max(0, int(raw.get("rounds", 0))),
        "next_seq": max(1, int(raw.get("next_seq", 1))),
        "plan_digest": raw.get("plan_digest"),
        "claims": deepcopy(raw.get("claims", {})) if isinstance(raw.get("claims"), dict) else {},
        "retired": deepcopy(raw.get("retired", [])) if isinstance(raw.get("retired"), list) else [],
        "debt": deepcopy(raw.get("debt")),
    })
    return state


def parse_audit(text: str, plan_text: str) -> Audit:
    """Parse and validate the single JSON object following ``AUDIT_MARKER``."""
    if text.count(AUDIT_MARKER) != 1:
        raise AuditError(
            f"expected exactly one {AUDIT_MARKER!r} marker, found {text.count(AUDIT_MARKER)}",
            text,
        )
    tail = text.split(AUDIT_MARKER, 1)[1].strip()
    if tail.startswith("```json"):
        tail = tail[7:].lstrip()
    elif tail.startswith("```"):
        tail = tail[3:].lstrip()
    try:
        value, end = json.JSONDecoder().raw_decode(tail)
    except json.JSONDecodeError as exc:
        raise AuditError(f"claim audit JSON did not parse: {exc}", text) from exc
    remainder = tail[end:].strip()
    if remainder == "```":
        remainder = ""
    if remainder:
        raise AuditError("unexpected text after claim audit JSON", text)
    if not isinstance(value, dict) or set(value) != {"claims", "coverage"}:
        raise AuditError("audit must be an object with exactly claims and coverage", text)
    claims, coverage = value["claims"], value["coverage"]
    if not isinstance(claims, list):
        raise AuditError("claims must be an array", text)
    if len(claims) > MAX_ACTIVE_CLAIMS:
        raise AuditError(
            f"audit returned {len(claims)} active claims; safety ceiling is {MAX_ACTIVE_CLAIMS}",
            text,
        )
    if not isinstance(coverage, dict):
        raise AuditError("coverage must be an object", text)

    validated: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(claims):
        try:
            claim = _validate_claim(item, plan_text)
        except ValueError as exc:
            raise AuditError(f"claim {index}: {exc}", text) from exc
        identity = (_norm(claim["anchor"]), _norm(claim["proposition"]))
        if identity in seen:
            raise AuditError(f"claim {index}: duplicate anchor and proposition", text)
        seen.add(identity)
        validated.append(claim)
    return Audit(tuple(validated), deepcopy(coverage))


def _validate_claim(item: Any, plan_text: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("must be an object")
    required = {"kind", "scope", "anchor", "proposition", "verdict", "evidence", "replacement"}
    optional = {"prior_claim_id", "rationale"}
    unknown = set(item) - required - optional
    missing = required - set(item)
    if missing or unknown:
        raise ValueError(f"fields mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}")
    # A concrete literal, not a pseudo-enum such as "fact|decision".  Decisions,
    # intentions and non-load-bearing observations never enter active inventory.
    if item["kind"] != "fact":
        raise ValueError("kind must be the literal \"fact\"")
    scope = item["scope"]
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {sorted(SCOPES)}")
    anchor = _one_line(item["anchor"], "anchor")
    proposition = _one_line(item["proposition"], "proposition")
    if anchor not in plan_text:
        raise ValueError("anchor is not a verbatim substring of the current plan")
    verdict = item["verdict"]
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")
    evidence = item["evidence"]
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE_PER_CLAIM:
        raise ValueError(f"evidence must be an array of at most {MAX_EVIDENCE_PER_CLAIM}")
    checked = [_validate_evidence(e, scope) for e in evidence]
    replacement = item["replacement"]
    if replacement is not None:
        replacement = _one_line(replacement, "replacement")
    prior = item.get("prior_claim_id")
    if prior is not None:
        prior = _one_line(prior, "prior_claim_id")
    rationale = str(item.get("rationale", "")).strip()

    qualifying = [e for e in checked if _qualifying(e, scope)]
    if verdict == "supported" and not any(e["relation"] == "supports_claim" for e in qualifying):
        raise ValueError("supported verdict lacks claim-entailing authoritative evidence")
    if verdict == "refuted" and not any(e["relation"] == "refutes_claim" for e in qualifying):
        raise ValueError("refuted verdict lacks claim-refuting authoritative evidence")
    if replacement is not None:
        if verdict != "refuted":
            raise ValueError("replacement is permitted only for a refuted claim")
        if not any(e["relation"] == "supports_replacement" for e in qualifying):
            raise ValueError("replacement lacks authoritative evidence that entails its wording")

    return {
        "kind": "fact", "scope": scope, "anchor": anchor,
        "proposition": proposition, "verdict": verdict, "evidence": checked,
        "replacement": replacement, "prior_claim_id": prior, "rationale": rationale,
    }


def _validate_evidence(item: Any, scope: str) -> dict[str, str]:
    if not isinstance(item, dict):
        raise ValueError("each evidence item must be an object")
    required = {
        "url", "title", "publisher", "source_kind", "authority_basis",
        "location", "quote", "relation",
    }
    if set(item) != required:
        raise ValueError(f"evidence fields must be exactly {sorted(required)}")
    result = {key: _one_line(value, f"evidence.{key}") for key, value in item.items()}
    if result["source_kind"] not in SOURCE_KINDS:
        raise ValueError(f"source_kind must be one of {sorted(SOURCE_KINDS)}")
    if result["relation"] not in RELATIONS:
        raise ValueError(f"relation must be one of {sorted(RELATIONS)}")
    if scope == "repository":
        if result["source_kind"] != "repository" or not result["url"].startswith("repo://"):
            raise ValueError("repository claims require source_kind repository and a repo:// URL")
    elif result["source_kind"] == "repository":
        raise ValueError("external claims cannot use repository evidence")
    host = (urlparse(result["url"]).hostname or "").lower()
    if scope == "external" and not host:
        raise ValueError("external evidence needs an absolute web URL")
    if _is_ugc_host(host):
        # Normalize, rather than reject: the packet remains useful as a lead or conflict,
        # while verdict validation below refuses to let it close a claim.
        result["source_kind"] = "ugc"
    return result


def _qualifying(evidence: dict[str, str], scope: str) -> bool:
    if scope == "repository":
        return evidence["source_kind"] == "repository"
    return evidence["source_kind"] in AUTHORITATIVE_KINDS


def reconcile(
    prior_raw: Any, audit: Audit, *, lineage_id: str, round_no: int, plan_text: str,
) -> dict[str, Any]:
    """Replace the active inventory with the current audit, retaining identity/evidence.

    Every verdict in ``audit`` has just been re-entailled against the current proposition.
    Prior evidence is retained only because it was supplied back to the reviewer as a
    candidate; no prior verdict is copied forward.
    """
    prior = normalize_state(prior_raw)
    old = prior["claims"]
    by_prop: dict[str, str] = {}
    for claim_id, record in old.items():
        if isinstance(record, dict) and isinstance(record.get("proposition"), str):
            by_prop.setdefault(_norm(record["proposition"]), claim_id)

    next_seq = prior["next_seq"]
    used: set[str] = set()
    current: dict[str, Any] = {}
    for claim in audit.claims:
        requested = claim.get("prior_claim_id")
        exact = by_prop.get(_norm(claim["proposition"]))
        claim_id = requested if requested in old and requested not in used else exact
        if not claim_id or claim_id in used:
            claim_id = _mint(lineage_id, next_seq, claim["proposition"])
            next_seq += 1
        used.add(claim_id)
        previous = old.get(claim_id)
        record = deepcopy(claim)
        record.pop("prior_claim_id", None)
        record["claim_id"] = claim_id
        record["verified_round"] = round_no
        if isinstance(previous, dict) and previous.get("proposition") != record["proposition"]:
            record["previous_proposition"] = previous.get("proposition")
        current[claim_id] = record

    retired = list(prior["retired"])
    for claim_id, record in old.items():
        if claim_id not in used:
            retired.append({
                "claim_id": claim_id,
                "proposition": record.get("proposition") if isinstance(record, dict) else None,
                "retired_round": round_no,
            })
    # History is diagnostic only and must not grow without bound or consume active prompt
    # inventory.  The active claims retain all evidence needed for the next round.
    retired = retired[-MAX_ACTIVE_CLAIMS:]
    return {
        "version": 1,
        "rounds": prior["rounds"] + 1,
        "next_seq": next_seq,
        "plan_digest": hashlib.sha256(plan_text.encode("utf-8", "surrogateescape")).hexdigest()[:16],
        "claims": current,
        "retired": retired,
        "coverage": audit.coverage,
        "debt": None,
    }


def with_debt(prior_raw: Any, error: AuditError, *, round_no: int, plan_text: str) -> dict[str, Any]:
    state = normalize_state(prior_raw)
    state["rounds"] += 1
    state["plan_digest"] = hashlib.sha256(
        plan_text.encode("utf-8", "surrogateescape")
    ).hexdigest()[:16]
    state["debt"] = error.debt(round_no)
    # Old verdicts are retained as evidence candidates, but cannot govern the changed
    # plan after a failed audit.
    for record in state["claims"].values():
        if isinstance(record, dict):
            record["verdict"] = "unverified"
            record["verified_round"] = round_no
            record["replacement"] = None
            record["rationale"] = (
                "The current-plan audit failed; retained sources are candidates only and "
                "must be re-entailled before correction."
            )
    return state


def is_blocked(state_raw: Any) -> bool:
    state = normalize_state(state_raw)
    if state.get("debt"):
        return True
    return any(
        isinstance(c, dict) and c.get("verdict") != "supported"
        for c in state["claims"].values()
    )


def evidence_context(state_raw: Any) -> str:
    """Compact prior evidence supplied for re-entailment, excluding retired inventory."""
    state = normalize_state(state_raw)
    records = []
    for claim_id, claim in state["claims"].items():
        if not isinstance(claim, dict):
            continue
        records.append({
            "claim_id": claim_id,
            "anchor": claim.get("anchor"),
            "proposition": claim.get("proposition"),
            "evidence": claim.get("evidence", []),
        })
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"))


def review_context(state_raw: Any) -> str:
    """Give the structural reviewer enough to detect omissions and use verified facts."""
    state = normalize_state(state_raw)
    lines = [
        "=== FACTUAL CLAIM REGISTER ===",
        "This inventory was independently researched before your structural review. Check the plan for any omitted load-bearing factual assertion; an omission is a blocking finding.",
    ]
    for claim_id, claim in state["claims"].items():
        lines.append(
            f"- {claim_id} [{claim.get('scope')}/{claim.get('verdict')}]: "
            f"{claim.get('proposition')}"
        )
    if state.get("debt"):
        lines.append(f"- AUDIT DEBT: {state['debt'].get('reason')}")
    return "\n".join(lines)


def render_trailer(state_raw: Any) -> str:
    state = normalize_state(state_raw)
    claims = list(state["claims"].values())
    counts = {verdict: sum(1 for c in claims if c.get("verdict") == verdict) for verdict in VERDICTS}
    lines = [
        f"CLAIM-REGISTER: {len(claims)} active factual claims; "
        f"{len(state.get('retired', []))} retired and excluded from active inventory",
        f"CLAIM-CLOSURE: {counts['supported']} supported, {counts['refuted']} refuted, "
        f"{counts['unverified']} unverified",
    ]
    if state.get("debt"):
        debt = state["debt"]
        lines.append(
            f"CLAIM-AUDIT-DEBT: round {debt.get('round')}: {debt.get('reason')} "
            f"(rejected sha256 {debt.get('raw_sha256')})"
        )
        if debt.get("rejected_excerpt"):
            lines.append("REJECTED-AUDIT-EXCERPT:\n" + debt["rejected_excerpt"])

    unresolved = [c for c in claims if c.get("verdict") != "supported"]
    if unresolved:
        lines.append("ACTIONABLE SOURCE PACKETS:")
    for claim in unresolved:
        lines.extend(_packet_lines(claim))
    return "\n".join(lines)


def _packet_lines(claim: dict[str, Any]) -> list[str]:
    lines = [
        f"- CLAIM {claim.get('claim_id')} — {str(claim.get('verdict', '')).upper()}",
        f"  Plan wording: {claim.get('anchor')}",
        f"  Atomic proposition: {claim.get('proposition')}",
    ]
    if claim.get("replacement"):
        lines.append(f"  Evidence-entailled replacement: {claim['replacement']}")
    else:
        lines.append("  Replacement: none proven; remove, weaken, or research the assertion")
    if claim.get("rationale"):
        lines.append(f"  Assessment: {claim['rationale']}")
    for index, evidence in enumerate(claim.get("evidence", []), 1):
        lines.extend([
            f"  Source {index}: [{evidence.get('source_kind')}/{evidence.get('relation')}] "
            f"{evidence.get('title')} — {evidence.get('publisher')}",
            f"    Authority: {evidence.get('authority_basis')}",
            f"    Location: {evidence.get('url')} ({evidence.get('location')})",
            f"    Exact passage: {evidence.get('quote')}",
        ])
    return lines


def audit_instructions(plan_text: str, prior_state: Any, stakes: str | None) -> str:
    """Build the research prompt.  Concrete JSON literals avoid pseudo-enum failures."""
    prior = evidence_context(prior_state)
    stakes_text = stakes or "modest single-team internal tool; trusted operators; ordinary scale"
    return f"""You are the factual-verification phase of an autonomous plan review.

STAKES: {stakes_text}

Read the entire plan and repository. Use your BUILT-IN web search for every external
claim. Prioritize external assertions; include repository-current-state facts only when
they are genuinely load-bearing. Search official/primary sources first: first-party documentation, standards,
statutes/regulators, government data, original papers/datasets, and the entity's own
records. Secondary reporting may corroborate or locate a source. Reddit, forums,
Stack Overflow, social media, wikis, blogs and other UGC are leads/conflict signals only;
they can NEVER support or refute a governing verdict.

Inventory ONLY load-bearing factual assertions: propositions whose truth could change
whether a step, dependency, rationale, feasibility judgement, mapping or acceptance test
is correct. Include explicit and necessary implied premises. Include current-repository
claims and externally verifiable claims. Split conjunctions and ranges into atomic
propositions. Scan every heading, paragraph, list item and table row.

OMIT decisions, chosen policies, authorizations, requirements, definitions, intentions,
instructions, subjective preferences, pure forecasts, and incidental facts that cannot
change execution. They must not consume active inventory after classification.

For every retained claim, decide supported, refuted, or unverified. A source verifies a
claim only when the exact quoted passage entails that exact atomic proposition. For
repository facts cite repo://path#Lx-Ly and quote the code. For external facts, record the
canonical absolute URL, title, publisher, precise section/table/page location, exact
passage, and why that publisher is authoritative for this proposition. Label source_kind honestly as primary, authoritative, secondary, ugc, or
repository. A proposed replacement is allowed only when an authoritative passage entails
the replacement itself; evidence that merely refutes the old wording is not enough.

Prior packets below are CANDIDATE evidence, never inherited verdicts. Re-open or search
each retained URL as needed and re-assess entailment against the CURRENT proposition.
If corrected wording corresponds to an old claim, set prior_claim_id to its claim_id.
Unchanged verified claims should normally be quicker because their exact sources are here.

PRIOR EVIDENCE PACKETS (JSON):
{prior}

Reply with only the marker and one JSON object. Do not use markdown fences. These are
CONCRETE literals, not pipe-delimited pseudo-enums. The shape is:

{AUDIT_MARKER}
{{"claims":[{{"kind":"fact","scope":"external","anchor":"verbatim plan text","proposition":"one atomic factual proposition","prior_claim_id":null,"verdict":"supported","evidence":[{{"url":"https://official.example/page","title":"Official title","publisher":"Issuing authority","source_kind":"primary","authority_basis":"The publisher issued the standard being described","location":"Section 2, table 1","quote":"Exact source passage","relation":"supports_claim"}}],"replacement":null,"rationale":"brief claim-specific assessment"}}],"coverage":{{"sections_scanned":3,"omitted_nonfacts":12,"notes":"brief coverage note"}}}}

Allowed verdict literals: "supported", "refuted", "unverified".
Allowed scope literals: "external", "repository".
Allowed relation literals: "supports_claim", "refutes_claim",
"supports_replacement", "context".

=== PLAN ===
{plan_text}"""


def retry_instructions(error: AuditError, plan_text: str) -> str:
    return f"""Your claim audit was rejected and no new verdict was applied.

Reason: {error.reason}
Rejected payload sha256: {error.raw_sha256}

Return the COMPLETE corrected audit for the plan, not a patch. Use exactly one
{AUDIT_MARKER} marker followed by one JSON object and nothing else. Every claim uses the
literal "kind":"fact"; never write "fact|decision" or another pseudo-enum. Preserve
valid source packets, fix the structural error, and do not weaken evidence requirements.

=== PLAN ===
{plan_text}"""


def _one_line(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return " ".join(value.split())


def _norm(value: str) -> str:
    return re.sub(r"\W+", " ", value.casefold()).strip()


def _mint(lineage_id: str, seq: int, proposition: str) -> str:
    digest = hashlib.sha256(
        f"{lineage_id}\0claim\0{seq}\0{proposition}".encode("utf-8")
    ).hexdigest()[:10]
    return f"C-{digest}"


def _is_ugc_host(host: str) -> bool:
    return any(host == suffix or host.endswith("." + suffix) for suffix in UGC_HOSTS)


def _excerpt(raw: str) -> str:
    if len(raw) <= DIAGNOSTIC_CHARS:
        return raw
    half = DIAGNOSTIC_CHARS // 2
    return raw[:half] + "\n… [bounded rejected output] …\n" + raw[-half:]
