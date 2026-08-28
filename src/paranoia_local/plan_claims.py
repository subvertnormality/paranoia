"""Authoritative external-claim verification for plan reviews.

The claim register is deliberately narrower than the structural review.  It covers
external-world facts, externally imposed design principles, and behavior promised by
external systems.  Repository mechanics remain available to the ordinary code/structure
review, but never enter this persistent evidence lifecycle.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from . import external_sources as sources
from . import inert_git


AUDIT_MARKER = "=== CLAIM AUDIT JSON ==="
MAX_ACTIVE_CLAIMS = 500
MAX_EVIDENCE_PER_CLAIM = 20
DIAGNOSTIC_CHARS = 4000
MAX_ATTESTATION_REASON_CHARS = 1_000
BINDING_FAILURE_PREFIX = "binding failure: "
ATTESTATION_FAILURE_PREFIX = "attestation failure: "

VERDICTS = frozenset({"supported", "refuted", "unverified"})
SCOPES = frozenset({"external"})
CLAIM_KINDS = frozenset({"fact", "design_principle", "behavior"})
SOURCE_KINDS = sources.SOURCE_KINDS
RELATIONS = frozenset(
    {"supports_claim", "refutes_claim", "supports_replacement", "context"}
)
AUTHORITATIVE_KINDS = sources.AUTHORITATIVE_KINDS

# These sources can be useful discovery leads, but cannot become authoritative merely
# because a model labels them "primary".  This is intentionally a narrow deny-list of
# unambiguously user-generated/community platforms, not a pretend universal authority
# classifier.
UGC_HOSTS = sources.UGC_HOSTS


class AuditError(ValueError):
    """The claim audit is absent, malformed, or makes an unsupported transition."""

    def __init__(
        self, reason: str, raw: str = "", *, failure_detail: str = "", stderr: str = "",
        returncode: int | None = None,
    ) -> None:
        self.reason = reason
        self.raw = raw
        self.failure_detail_raw = failure_detail
        self.stderr_raw = stderr
        self.returncode = returncode
        self.raw_sha256 = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()
        self.excerpt = _excerpt(raw)
        self.failure_detail_sha256 = hashlib.sha256(
            failure_detail.encode("utf-8", "replace")
        ).hexdigest()
        self.failure_detail = _excerpt(failure_detail)
        self.stderr_sha256 = hashlib.sha256(stderr.encode("utf-8", "replace")).hexdigest()
        self.stderr = _excerpt(stderr)
        super().__init__(reason)

    def debt(self, round_no: int) -> dict[str, Any]:
        return {
            "round": round_no,
            "reason": self.reason,
            "returncode": self.returncode,
            "raw_sha256": self.raw_sha256,
            "rejected_excerpt": self.excerpt,
            "failure_detail_sha256": self.failure_detail_sha256,
            "failure_detail": self.failure_detail,
            "stderr_sha256": self.stderr_sha256,
            "stderr": self.stderr,
        }


def bounded_diagnostic(text: str) -> str:
    """Bound one model-controlled diagnostic using the canonical head/tail excerpt."""
    return _excerpt(text)


@dataclass(frozen=True)
class Audit:
    claims: tuple[dict[str, Any], ...]
    coverage: dict[str, Any]
    dispositions: tuple[dict[str, str], ...]
    assessments: tuple[dict[str, str], ...] = ()
    issues: tuple[str, ...] = ()
    raw_sha256: str = ""
    rejected_excerpt: str = ""


def empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "rounds": 0,
        "next_seq": 1,
        "plan_digest": None,
        "plan_snapshot": None,
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
    if not raw:
        return state
    if raw.get("version") != 1:
        return _migration_blocked_state(raw)
    claims = deepcopy(raw.get("claims", {})) if isinstance(raw.get("claims"), dict) else {}
    retired = deepcopy(raw.get("retired", [])) if isinstance(raw.get("retired"), list) else []
    # Version-1 lineages may contain repository assertions created by the old broad
    # extractor.  Scope eligibility is server-owned, so retire these mechanically rather
    # than asking another stochastic model round to disposition them.  This is what makes
    # the external/repository boundary an invariant instead of prompt advice.
    retired_ids = {
        item.get("claim_id") for item in retired if isinstance(item, dict)
    }
    for claim_id, record in list(claims.items()):
        if not isinstance(record, dict) or record.get("scope") != "external":
            claims.pop(claim_id, None)
            if claim_id not in retired_ids:
                retired.append({
                    "claim_id": claim_id,
                    "anchor": record.get("anchor") if isinstance(record, dict) else None,
                    "proposition": (
                        record.get("proposition") if isinstance(record, dict) else None
                    ),
                    "disposition": "out_of_scope",
                    "reason": (
                        "Mechanically retired: repository/internal assertions belong to "
                        "structural review and tests, not external evidence verification."
                    ),
                    "retired_round": max(0, int(raw.get("rounds", 0))),
                })
                retired_ids.add(claim_id)
    state.update({
        "rounds": max(0, int(raw.get("rounds", 0))),
        "next_seq": max(1, int(raw.get("next_seq", 1))),
        "plan_digest": raw.get("plan_digest"),
        "plan_snapshot": (
            raw.get("plan_snapshot")
            if isinstance(raw.get("plan_snapshot"), str) else None
        ),
        "claims": claims,
        "retired": retired[-MAX_ACTIVE_CLAIMS:],
        "debt": deepcopy(raw.get("debt")),
    })
    return state


def _migration_blocked_state(raw: dict[str, Any]) -> dict[str, Any]:
    """Fail closed over the pre-replacement claim schema until one exhaustive audit.

    Current main persisted a versionless claim array with different evidence and anchor
    types. Guessing those rows into the external-only schema would either retain internal
    debt or silently lose unresolved claims. Preserve their identity as migration debt;
    absence of a plan snapshot forces the next successful call through exhaustive audit.
    """
    state = empty_state()
    rows = raw.get("claims")
    identifiers: list[str] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("status") in {"NOT_APPLICABLE", "SUPERSEDED"}:
                continue
            claim_id = row.get("claim_id")
            status = row.get("status")
            if isinstance(claim_id, str):
                identifiers.append(f"{claim_id}:{status}")
    prior_debt = raw.get("debt")
    if identifiers or prior_debt is not None or "claims" not in raw:
        digest = hashlib.sha256(
            json.dumps(raw, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        preview = ", ".join(identifiers[:20]) or "unrecognized versioned state"
        state["debt"] = {
            "round": 1,
            "reason": (
                "Legacy claim state requires one exhaustive external-claim audit before "
                f"clearance; {len(identifiers)} active predecessor(s): {preview}; "
                f"legacy-state sha256 {digest}."
            )[:DIAGNOSTIC_CHARS],
            "raw_sha256": digest,
            "rejected_excerpt": "",
        }
    if isinstance(raw.get("next_seq"), int) and raw["next_seq"] > 0:
        state["next_seq"] = raw["next_seq"]
    return state


def has_prior_snapshot(state_raw: Any) -> bool:
    """Whether a later round can be scoped to edits from a successful prior audit."""
    return normalize_state(state_raw).get("plan_snapshot") is not None


def frozen_supported_ids(
    state_raw: Any, plan_text: str, *, repo: Path | None = None,
    plan_repo_path: str | None = None, require_capture_attestation: bool = False,
) -> frozenset[str]:
    """Return exact supported claims that need no new model/web judgement.

    External packets are immutable evidence captured by the exhaustive round. Edited or
    removed anchors and every unresolved claim remain outside this set and therefore enter
    targeted remediation.
    """
    state = normalize_state(state_raw)
    if state.get("plan_snapshot") is None:
        return frozenset()
    previous_plan = state["plan_snapshot"]
    frozen: set[str] = set()
    for claim_id, record in state["claims"].items():
        if not isinstance(record, dict) or record.get("verdict") != "supported":
            continue
        if require_capture_attestation and not _captured_support(record):
            continue
        if not _assertion_binding_unchanged(
            record.get("anchor", ""), previous_plan, plan_text,
        ):
            continue
        evidence = [item for item in record.get("evidence", []) if isinstance(item, dict)]
        supports = [
            item for item in evidence
            if _qualifying(
                item, record.get("scope", ""), repo=repo,
                plan_repo_path=plan_repo_path,
            )
            and item.get("relation") == "supports_claim"
        ]
        if not supports:
            continue
        frozen.add(claim_id)
    return frozenset(frozen)


def _captured_support(record: dict[str, Any]) -> bool:
    evidence = record.get("evidence", [])
    provenance = record.get("capture_provenance", [])
    for row in record.get("capture_attestations", []):
        if not isinstance(row, dict):
            continue
        index = row.get("evidence_index")
        if type(index) is not int or not 0 <= index < len(evidence):
            continue
        item = evidence[index]
        capture_row = next((
            candidate for candidate in provenance
            if isinstance(candidate, dict)
            and candidate.get("evidence_index") == index
        ), None)
        if (
            isinstance(item, dict)
            and isinstance(capture_row, dict)
            and item.get("relation") == "supports_claim"
            and row.get("relation") == "supports_claim"
            and row.get("final_url") == item.get("url")
            and capture_row.get("final_url") == item.get("url")
            and isinstance(capture_row.get("requested_url"), str)
            and capture_row.get("text_sha256") == row.get("text_sha256")
            and capture_row.get("error") is None
            and row.get("publisher_authority") is True
            and row.get("passage_entailment") is True
        ):
            return True
    return False


def changed_plan_text(state_raw: Any, plan_text: str) -> str:
    """Render the exact edit cone used after the exhaustive round."""
    previous = normalize_state(state_raw).get("plan_snapshot")
    if not isinstance(previous, str):
        return plan_text
    if previous == plan_text:
        return "(no textual changes)"
    return "".join(unified_diff(
        previous.splitlines(keepends=True), plan_text.splitlines(keepends=True),
        fromfile="previous-plan", tofile="current-plan", n=4,
    ))


def parse_audit(
    text: str, plan_text: str, *, allow_partial: bool = False,
    repo: Path | None = None, plan_repo_path: str | None = None,
    require_capture_provenance: bool = False,
) -> Audit:
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
    issues: list[str] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(claims):
        try:
            claim = _validate_claim(
                item, plan_text, repo=repo, plan_repo_path=plan_repo_path,
                require_capture_provenance=require_capture_provenance,
            )
        except ValueError as exc:
            reason = f"claim {index}: {exc}"
            if not allow_partial:
                raise AuditError(reason, text) from exc
            issues.append(f"{reason}; item={_excerpt(json.dumps(item, ensure_ascii=False))}")
            continue
        identity = (claim["anchor"], claim["proposition"])
        if identity in seen:
            reason = f"claim {index}: duplicate anchor and proposition"
            if not allow_partial:
                raise AuditError(reason, text)
            issues.append(f"{reason}; item={_excerpt(json.dumps(item, ensure_ascii=False))}")
            continue
        seen.add(identity)
        validated.append(claim)
    for field in ("prior_dispositions", "prior_assessments"):
        if field not in coverage:
            raise AuditError(f"coverage.{field} is required", text)
    dispositions = _validate_dispositions(coverage["prior_dispositions"], text)
    assessments = _validate_assessments(coverage["prior_assessments"], text)
    return Audit(
        tuple(validated), deepcopy(coverage), dispositions, assessments, tuple(issues),
        hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
        _excerpt("\n".join(issues)),
    )


def _validate_dispositions(raw: Any, text: str) -> tuple[dict[str, str], ...]:
    if not isinstance(raw, list):
        raise AuditError("coverage.prior_dispositions must be an array", text)
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        fields = set(item) if isinstance(item, dict) else set()
        id_fields = fields & {"claim_id", "prior_claim_id"}
        reason_fields = fields & {"reason", "rationale"}
        if (
            len(id_fields) != 1
            or len(reason_fields) != 1
            or "disposition" not in fields
        ):
            raise AuditError(
                f"prior disposition {index} must contain one claim ID, disposition, "
                "and one reason (prior_claim_id and rationale are accepted as wire aliases)",
                text,
            )
        try:
            claim_id = _one_line(item[next(iter(id_fields))], "disposition.claim_id")
            disposition = _one_line(item["disposition"], "disposition.disposition")
            reason = _one_line(
                item.get("reason", item.get("rationale")), "disposition.reason",
            )
        except ValueError as exc:
            raise AuditError(f"prior disposition {index}: {exc}", text) from exc
        if disposition != "removed":
            raise AuditError(f"prior disposition {index} must be removed", text)
        if claim_id in seen:
            raise AuditError(f"duplicate disposition for prior claim {claim_id}", text)
        seen.add(claim_id)
        result.append({"claim_id": claim_id, "disposition": disposition, "reason": reason})
    return tuple(result)


def _validate_assessments(raw: Any, text: str) -> tuple[dict[str, str], ...]:
    """Keep the legacy wire field explicit but mechanically empty."""
    if not isinstance(raw, list):
        raise AuditError("coverage.prior_assessments must be an array", text)
    if raw:
        raise AuditError(
            "coverage.prior_assessments must be empty; compact assessments cannot cross "
            "the server-capture boundary",
            text,
        )
    return ()


def _validate_claim(
    item: Any, plan_text: str, *, repo: Path | None = None,
    plan_repo_path: str | None = None, require_capture_provenance: bool = False,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("must be an object")
    required = {"kind", "scope", "anchor", "proposition", "verdict", "evidence", "replacement"}
    optional = {
        "prior_claim_id", "rationale", "capture_attestations", "capture_provenance",
    }
    unknown = set(item) - required - optional
    missing = required - set(item)
    if missing or unknown:
        raise ValueError(f"fields mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}")
    # Concrete literals make eligibility mechanically enforceable.  An externally
    # published normative principle or promised behavior can be load-bearing even though
    # it is not naturally described as a historical "fact".
    if item["kind"] not in CLAIM_KINDS:
        raise ValueError(f"kind must be one of {sorted(CLAIM_KINDS)}")
    kind = item["kind"]
    scope = item["scope"]
    if scope not in SCOPES:
        raise ValueError(
            "scope must be the literal \"external\"; repository/internal assertions "
            "belong to structural review and tests"
        )
    anchor = _one_line(item["anchor"], "anchor")
    proposition = _one_line(item["proposition"], "proposition")
    # Markdown frequently wraps one sentence across physical lines. Verbatim means the
    # same characters/tokens modulo whitespace, not identical line wrapping. Punctuation
    # and case remain exact, so this cannot recreate normalized identity collisions.
    if not _anchor_in_plan(anchor, plan_text):
        raise ValueError(
            "anchor is not a verbatim substring of the current plan modulo whitespace"
        )
    introduced = _introduced_universal_quantifiers(anchor, proposition)
    if introduced:
        raise ValueError(
            "proposition introduces universal quantifier(s) absent from the verbatim "
            f"plan wording: {', '.join(introduced)}"
        )
    verdict = item["verdict"]
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")
    evidence = item["evidence"]
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE_PER_CLAIM:
        raise ValueError(f"evidence must be an array of at most {MAX_EVIDENCE_PER_CLAIM}")
    checked = [
        _validate_evidence(
            e, scope, repo=repo, plan_repo_path=plan_repo_path,
        )
        for e in evidence
    ]
    replacement = item["replacement"]
    if replacement is not None:
        replacement = _one_line(replacement, "replacement")
    prior = item.get("prior_claim_id")
    if prior is not None:
        prior = _one_line(prior, "prior_claim_id")
    rationale = str(item.get("rationale", "")).strip()
    capture_attestations = _validate_capture_attestations(
        item.get("capture_attestations", []), checked,
    )
    capture_provenance = _validate_capture_provenance(
        item.get("capture_provenance", []), checked,
    )
    if require_capture_provenance and len(capture_provenance) != len(checked):
        raise ValueError(
            "capture_provenance must contain exactly one row per evidence item"
        )

    qualifying = [
        e for e in checked
        if _qualifying(e, scope, repo=repo, plan_repo_path=plan_repo_path)
    ]
    failure_phases = _source_failure_phases(capture_provenance, checked)
    demotion = None
    if verdict == "supported" and not any(e["relation"] == "supports_claim" for e in qualifying):
        demotion = "claimed support lacked claim-entailing authoritative evidence"
    if verdict == "refuted" and not any(e["relation"] == "refutes_claim" for e in qualifying):
        demotion = "claimed refutation lacked claim-refuting authoritative evidence"
    if demotion:
        # Model mistakes about authority or relation are local to one claim. Preserve
        # its proposition and candidate sources, but make the server-owned verdict
        # conservatively blocking instead of discarding every other valid packet.
        verdict = "unverified"
        replacement = None
        if not failure_phases:
            rationale = f"{rationale} Server demotion: {demotion}.".strip()
    if failure_phases:
        verdict = "unverified"
        replacement = None
        if failure_phases == ("capture",):
            rationale = (
                "Server capture failed before authority or entailment could be adjudicated; "
                "provider-authored assessment is not evidence, and the proposition remains "
                "unverified."
            )
        else:
            named_phases = ", ".join(failure_phases)
            rationale = (
                f"Server evidence processing failed in the {named_phases} phase(s) before "
                "authority and entailment could be fully adjudicated; the proposition "
                "remains unverified."
            )
    if replacement is not None:
        if verdict != "refuted" or not any(
            e["relation"] == "supports_replacement" for e in qualifying
        ):
            # A replacement is optional assistance, not part of the audited verdict.
            # Keep the valid refutation packet while refusing to expose wording that
            # its evidence does not entail.  One over-eager correction must not discard
            # every independently valid claim in the same model response.
            replacement = None

    return {
        "kind": kind, "scope": scope, "anchor": anchor,
        "proposition": proposition, "verdict": verdict, "evidence": checked,
        "replacement": replacement, "prior_claim_id": prior, "rationale": rationale,
        "capture_attestations": capture_attestations,
        "capture_provenance": capture_provenance,
    }


def _validate_capture_provenance(
    value: Any, evidence: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > len(evidence):
        raise ValueError("capture_provenance must contain at most one row per evidence item")
    fields = {
        "evidence_index", "requested_url", "final_url", "status", "content_type",
        "fallback_attempted", "content_sha256", "text_sha256", "error",
    }
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in value:
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("capture_provenance fields are invalid")
        index = row["evidence_index"]
        if type(index) is not int or not 0 <= index < len(evidence) or index in seen:
            raise ValueError("capture_provenance evidence_index is invalid or duplicated")
        seen.add(index)
        requested_url = _one_line(
            row["requested_url"], "capture_provenance.requested_url",
        )
        final_url = row["final_url"]
        if final_url is not None:
            final_url = _one_line(final_url, "capture_provenance.final_url")
            parsed = urlparse(final_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(
                    "capture_provenance final_url must be null or absolute HTTP(S)"
                )
            if final_url != evidence[index]["url"]:
                raise ValueError("capture_provenance final_url differs from its evidence URL")
        elif requested_url != evidence[index]["url"]:
            raise ValueError(
                "capture_provenance requested_url differs from uncaptured evidence URL"
            )
        status = row["status"]
        if status is not None and (type(status) is not int or not 100 <= status <= 599):
            raise ValueError("capture_provenance status must be null or an HTTP status integer")
        if type(row["fallback_attempted"]) is not bool:
            raise ValueError("capture_provenance fallback_attempted must be boolean")

        def optional_line(field: str, maximum: int) -> str | None:
            raw = row[field]
            if raw is None:
                return None
            checked = _one_line(raw, f"capture_provenance.{field}")
            if len(checked) > maximum:
                raise ValueError(
                    f"capture_provenance {field} exceeds {maximum} characters"
                )
            return checked

        content_sha = optional_line("content_sha256", 64)
        text_sha = optional_line("text_sha256", 64)
        for field, digest in (("content_sha256", content_sha), ("text_sha256", text_sha)):
            if digest is not None and not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"capture_provenance {field} must be null or lowercase SHA-256")
        rows.append({
            "evidence_index": index,
            "requested_url": requested_url,
            "final_url": final_url,
            "status": status,
            "content_type": optional_line("content_type", 500),
            "fallback_attempted": row["fallback_attempted"],
            "content_sha256": content_sha,
            "text_sha256": text_sha,
            "error": optional_line("error", sources.MAX_CAPTURE_ERROR_CHARS),
        })
    return rows


def _source_failure_phases(
    provenance: list[dict[str, Any]], evidence: list[dict[str, str]],
) -> tuple[str, ...]:
    """Return every server-owned failed phase, including mixed/partial failures."""
    if not evidence or len(provenance) != len(evidence):
        return ()
    phases: list[str] = []
    for row in provenance:
        raw_error = row.get("error")
        if not raw_error:
            continue
        error = str(raw_error)
        if error.startswith(BINDING_FAILURE_PREFIX):
            phase = "binding"
        elif error.startswith(ATTESTATION_FAILURE_PREFIX):
            phase = "attestation"
        elif row.get("content_sha256") is None and row.get("text_sha256") is None:
            phase = "capture"
        else:
            # A digest-bearing, unlabelled error has no trustworthy server phase.
            return ()
        if phase not in phases:
            phases.append(phase)
    return tuple(phases)


def _validate_capture_attestations(
    value: Any, evidence: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > len(evidence):
        raise ValueError("capture_attestations must contain at most one row per evidence item")
    required = {
        "evidence_index", "final_url", "text_sha256", "relation",
        "publisher_authority", "authority_reason", "passage_entailment",
        "entailment_reason",
    }
    optional = {
        "content_sha256", "status", "content_type", "fallback_attempted",
        "capture_error",
    }
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in value:
        if not isinstance(row, dict) or not required <= set(row) or set(row) - required - optional:
            raise ValueError("capture_attestation fields are invalid")
        index = row["evidence_index"]
        if type(index) is not int or not 0 <= index < len(evidence) or index in seen:
            raise ValueError("capture_attestation evidence_index is invalid or duplicated")
        seen.add(index)
        final_url = _one_line(row["final_url"], "capture_attestation.final_url")
        parsed = urlparse(final_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("capture_attestation final_url must be absolute HTTP(S)")
        text_sha256 = _one_line(
            row["text_sha256"], "capture_attestation.text_sha256",
        )
        if not re.fullmatch(r"[0-9a-f]{64}", text_sha256):
            raise ValueError("capture_attestation text_sha256 must be lowercase SHA-256")
        relation = _one_line(row["relation"], "capture_attestation.relation")
        if relation != evidence[index]["relation"]:
            raise ValueError("capture_attestation relation differs from its evidence item")
        if final_url != evidence[index]["url"]:
            raise ValueError("capture_attestation final_url differs from its evidence URL")
        for field in ("publisher_authority", "passage_entailment"):
            if type(row[field]) is not bool:
                raise ValueError(f"capture_attestation {field} must be boolean")
        checked = {
            "evidence_index": index,
            "final_url": final_url,
            "text_sha256": text_sha256,
            "relation": relation,
            "publisher_authority": row["publisher_authority"],
            "authority_reason": _one_line(
                row["authority_reason"], "capture_attestation.authority_reason",
            ),
            "passage_entailment": row["passage_entailment"],
            "entailment_reason": _one_line(
                row["entailment_reason"], "capture_attestation.entailment_reason",
            ),
        }
        if len(checked["authority_reason"]) > MAX_ATTESTATION_REASON_CHARS or len(
            checked["entailment_reason"]
        ) > MAX_ATTESTATION_REASON_CHARS:
            raise ValueError(
                "capture_attestation reason exceeds "
                f"{MAX_ATTESTATION_REASON_CHARS} characters"
            )
        if "content_sha256" in row:
            content_sha256 = _one_line(
                row["content_sha256"], "capture_attestation.content_sha256",
            )
            if not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
                raise ValueError("capture_attestation content_sha256 must be lowercase SHA-256")
            checked["content_sha256"] = content_sha256
        if "status" in row:
            if type(row["status"]) is not int or not 100 <= row["status"] <= 599:
                raise ValueError("capture_attestation status must be an HTTP status integer")
            checked["status"] = row["status"]
        if "content_type" in row:
            checked["content_type"] = _one_line(
                row["content_type"], "capture_attestation.content_type",
            )
        if "fallback_attempted" in row:
            if type(row["fallback_attempted"]) is not bool:
                raise ValueError("capture_attestation fallback_attempted must be boolean")
            checked["fallback_attempted"] = row["fallback_attempted"]
        if "capture_error" in row:
            checked["capture_error"] = _one_line(
                row["capture_error"], "capture_attestation.capture_error",
            )
        rows.append(checked)
    return rows


def _validate_evidence(
    item: Any, scope: str, *, repo: Path | None = None,
    plan_repo_path: str | None = None,
) -> dict[str, str]:
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
    parsed = urlparse(result["url"])
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"https", "http"} or not host:
        result["relation"] = "context"
    if repo is not None and plan_repo_path and _is_plan_self_url(
        result["url"], repo, plan_repo_path,
    ):
        result["relation"] = "context"
    if _is_ugc_host(host):
        # Normalize, rather than reject: the packet remains useful as a lead or conflict,
        # while verdict validation below refuses to let it close a claim.
        result["source_kind"] = "ugc"
    return result


def _qualifying(
    evidence: dict[str, str], scope: str, *, repo: Path | None = None,
    plan_repo_path: str | None = None,
) -> bool:
    parsed = urlparse(evidence["url"])
    return (
        scope == "external"
        and parsed.scheme in {"https", "http"}
        and bool(parsed.hostname)
        and evidence["source_kind"] in AUTHORITATIVE_KINDS
        and not (
            repo is not None
            and plan_repo_path
            and _is_plan_self_url(evidence["url"], repo, plan_repo_path)
        )
    )


def _is_plan_self_url(url: str, repo: Path, plan_repo_path: str) -> bool:
    """Whether an HTTP(S) URL resolves to the reviewed plan in this repository."""
    remote = _canonical_remote_repo(str(repo.resolve()))
    if remote is None:
        return False
    remote_host, remote_path = remote
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = unquote(parsed.path).strip("/")
    plan_path = unquote(plan_repo_path).strip("/")
    if not plan_path or not path.endswith("/" + plan_path):
        return False
    if host == remote_host and path.startswith(remote_path + "/"):
        middle = path[len(remote_path) + 1: -len(plan_path)].strip("/")
        return middle.startswith("blob/") or middle.startswith("raw/") or "/blob/" in middle
    if remote_host == "github.com" and host == "raw.githubusercontent.com":
        return path.startswith(remote_path + "/")
    return False


def _canonical_remote_repo(repo_path: str) -> tuple[str, str] | None:
    try:
        completed = inert_git.invoke(
            Path(repo_path), ["config", "--get", "remote.origin.url"],
        )
    except OSError:
        return None
    remote = (
        completed.stdout.decode("utf-8", errors="replace").strip()
        if completed.returncode == 0 else ""
    )
    if not remote:
        return None
    if "://" not in remote:
        scp = re.match(r"^(?:[^@]+@)?([^:]+):(.+)$", remote)
        if not scp:
            return None
        host, path = scp.group(1).lower(), scp.group(2)
    else:
        parsed = urlparse(remote)
        host, path = (parsed.hostname or "").lower(), parsed.path
    normalized = path.strip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if not host or not normalized:
        return None
    return host, normalized


def reconcile(
    prior_raw: Any, audit: Audit, *, lineage_id: str, round_no: int, plan_text: str,
    frozen_ids: Iterable[str] = (), repo: Path | None = None,
    plan_repo_path: str | None = None,
    allow_missing: bool = False,
) -> dict[str, Any]:
    """Replace the active inventory with the current audit, retaining identity/evidence.

    Every verdict in ``audit`` has just been assessed against the current proposition.
    ``frozen_ids`` are the narrow exception: exact unchanged supported propositions retain
    their exhaustive-round packet without another model/web judgement.
    """
    frozen = frozenset(frozen_ids)
    validate_prior_coverage(
        prior_raw, audit, plan_text=plan_text, frozen_ids=frozen, repo=repo,
        plan_repo_path=plan_repo_path, allow_missing=allow_missing,
    )
    prior = normalize_state(prior_raw)
    old = prior["claims"]
    by_prop: dict[str, str] = {}
    for claim_id, record in old.items():
        if isinstance(record, dict) and isinstance(record.get("proposition"), str):
            by_prop.setdefault(record["proposition"], claim_id)

    next_seq = prior["next_seq"]
    used: set[str] = set()
    current: dict[str, Any] = {}
    for claim_id in frozen:
        previous = old.get(claim_id)
        if not isinstance(previous, dict):
            raise AuditError(f"frozen assessment references unknown prior claim {claim_id}")
        if previous.get("verdict") != "supported":
            raise AuditError(f"only supported prior claims may be frozen: {claim_id}")
        if not _anchor_in_plan(previous.get("anchor", ""), plan_text):
            raise AuditError(f"frozen prior anchor is absent from the current plan: {claim_id}")
        record = deepcopy(previous)
        record["retained_round"] = round_no
        record["retention_basis"] = (
            "Exact proposition and anchor are unchanged; the authoritative evidence packet "
            "was frozen by the first exhaustive round."
        )
        current[claim_id] = record
        used.add(claim_id)
    for claim in audit.claims:
        exact = by_prop.get(claim["proposition"])
        # Identity is server-owned and semantic only at the exact proposition seam.
        # A model-provided prior ID is useful context but cannot bind edited wording to
        # unrelated history.  Corrected propositions mint a new ID; the predecessor must
        # separately satisfy the mechanically checked removal rule below.
        claim_id = exact
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
    dispositions = {item["claim_id"]: item for item in audit.dispositions}
    for claim_id, record in old.items():
        if claim_id not in used:
            disposition = dispositions.get(claim_id)
            old_anchor = record.get("anchor", "") if isinstance(record, dict) else ""
            removable = bool(
                disposition
                and disposition["disposition"] == "removed"
                and not _anchor_in_plan(old_anchor, plan_text)
            )
            if removable:
                retired.append({
                    "claim_id": claim_id,
                    "anchor": old_anchor,
                    "proposition": record.get("proposition") if isinstance(record, dict) else None,
                    "disposition": disposition["disposition"],
                    "reason": disposition["reason"],
                    "retired_round": round_no,
                })
            else:
                # Model omission is not deletion.  Preserve the exact prior packet as
                # active but invalidate its verdict until the current audit either retains
                # it or gives an independently reviewable disposition.
                carried = deepcopy(record) if isinstance(record, dict) else {}
                carried.update({
                    "claim_id": claim_id,
                    "verdict": "unverified",
                    "replacement": None,
                    "verified_round": round_no,
                    "rationale": (
                        "The current audit omitted this prior claim without a valid "
                        "disposition; omission cannot clear governing inventory."
                    ),
                })
                current[claim_id] = carried
    # History is diagnostic only and must not grow without bound or consume active prompt
    # inventory.  The active claims retain all evidence needed for the next round.
    retired = retired[-MAX_ACTIVE_CLAIMS:]
    debt = None
    if audit.issues:
        debt = {
            "round": round_no,
            "reason": (
                f"{len(audit.issues)} localized invalid claim(s); valid claims and "
                "dispositions were retained: " + "; ".join(audit.issues)
            )[:DIAGNOSTIC_CHARS],
            "raw_sha256": audit.raw_sha256,
            "rejected_excerpt": audit.rejected_excerpt,
        }
    return {
        "version": 1,
        "rounds": prior["rounds"] + 1,
        "next_seq": next_seq,
        "plan_digest": hashlib.sha256(plan_text.encode("utf-8", "surrogateescape")).hexdigest()[:16],
        "plan_snapshot": plan_text,
        "claims": current,
        "retired": retired,
        "coverage": audit.coverage,
        "debt": debt,
    }


def validate_prior_coverage(
    prior_raw: Any, audit: Audit, *, plan_text: str, raw: str = "",
    frozen_ids: Iterable[str] = (), repo: Path | None = None,
    plan_repo_path: str | None = None,
    allow_missing: bool = False,
) -> None:
    """Require a current judgement for every retained exact claim still in the plan.

    The governing inventory is server-owned. A stochastic extractor may discover new
    facts, but it cannot decide which old facts deserve another assessment merely by
    omitting them.
    """
    prior = normalize_state(prior_raw)
    frozen = frozenset(frozen_ids)
    if len(audit.claims) + len(audit.assessments) + len(frozen) > MAX_ACTIVE_CLAIMS:
        raise AuditError(
            f"audit returned {len(audit.claims)} full claims plus "
            f"{len(audit.assessments)} retained assessments plus {len(frozen)} frozen; "
            "active safety ceiling is "
            f"{MAX_ACTIVE_CLAIMS}", raw,
        )
    old = prior["claims"]
    if audit.assessments:
        raise AuditError(
            "non-frozen retained claims require full current evidence packets; compact "
            "assessments cannot cross the server-capture boundary",
            raw,
        )
    by_prop = {
        record.get("proposition"): claim_id
        for claim_id, record in old.items()
        if isinstance(record, dict) and isinstance(record.get("proposition"), str)
    }
    emitted = {
        by_prop[claim["proposition"]]
        for claim in audit.claims
        if claim["proposition"] in by_prop
    }
    frozen_overlap = emitted & frozen
    if frozen_overlap:
        raise AuditError(
            "frozen claims were re-emitted by the targeted audit: "
            + ", ".join(sorted(frozen_overlap)), raw,
        )
    expected = {
        claim_id for claim_id, record in old.items()
        if isinstance(record, dict)
        and _anchor_in_plan(record.get("anchor", ""), plan_text)
    }
    unknown_frozen = frozen - expected
    if unknown_frozen:
        raise AuditError(
            "frozen IDs are not exact current claims: " + ", ".join(sorted(unknown_frozen)), raw,
        )
    missing = expected - emitted - frozen
    if missing and not allow_missing:
        raise AuditError(
            "missing full current evidence packets for retained claims: "
            + ", ".join(sorted(missing)),
            raw,
        )


def with_debt(
    prior_raw: Any, error: AuditError, *, round_no: int, plan_text: str,
    frozen_ids: Iterable[str] = (),
) -> dict[str, Any]:
    state = normalize_state(prior_raw)
    state["rounds"] += 1
    state["plan_digest"] = hashlib.sha256(
        plan_text.encode("utf-8", "surrogateescape")
    ).hexdigest()[:16]
    state["debt"] = error.debt(round_no)
    # Old verdicts are retained as evidence candidates, but cannot govern the changed
    # plan after a failed audit.
    frozen = frozenset(frozen_ids)
    for claim_id, record in state["claims"].items():
        if isinstance(record, dict):
            if claim_id in frozen and record.get("verdict") == "supported":
                record["retained_round"] = round_no
                continue
            record["verdict"] = "unverified"
            record["verified_round"] = round_no
            record["replacement"] = None
            record["rationale"] = (
                "The current-plan audit failed; retained sources are candidates only and "
                "must have entailment rechecked before correction."
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


def evidence_context(state_raw: Any, include_ids: Iterable[str] | None = None) -> str:
    """Compact prior evidence supplied for re-entailment, excluding retired inventory."""
    state = normalize_state(state_raw)
    allowed = frozenset(include_ids) if include_ids is not None else None
    records = []
    for claim_id, claim in state["claims"].items():
        if not isinstance(claim, dict):
            continue
        if allowed is not None and claim_id not in allowed:
            continue
        records.append({
            "claim_id": claim_id,
            "anchor": claim.get("anchor"),
            "proposition": claim.get("proposition"),
            "evidence": claim.get("evidence", []),
        })
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"))


def review_context(state_raw: Any) -> str:
    """Give the structural reviewer external evidence without expanding its scope."""
    state = normalize_state(state_raw)
    lines = [
        "=== AUTHORITATIVE EXTERNAL CLAIM REGISTER ===",
        (
            "This register is limited to external-world facts, externally imposed design "
            "principles, and behavior promised by external systems. Do not demand claim "
            "packets for repository state, code paths, implementation conformance, internal "
            "history, or function-to-function bridges; assess those normally in the structural "
            "review and tests. An omission is claim-blocking only when the plan relies on an "
            "eligible external proposition that authoritative web evidence can adjudicate."
        ),
    ]
    for claim_id, claim in state["claims"].items():
        lines.extend([
            f"- CLAIM {claim_id} [{claim.get('kind')}/{claim.get('verdict')}]",
            f"  Plan wording: {claim.get('anchor')}",
            f"  Atomic proposition: {claim.get('proposition')}",
            f"  Proposed replacement: {claim.get('replacement') or 'none'}",
        ])
        for index, evidence in enumerate(claim.get("evidence", []), 1):
            lines.extend([
                f"  Evidence {index}: [{evidence.get('source_kind')}/{evidence.get('relation')}] "
                f"{evidence.get('title')} — {evidence.get('publisher')}",
                f"    Authority basis: {evidence.get('authority_basis')}",
                f"    Location: {evidence.get('url')} ({evidence.get('location')})",
                f"    Exact passage: {evidence.get('quote')}",
            ])
    recent_retired = [
        item for item in state.get("retired", [])
        if item.get("retired_round") == state.get("rounds")
        and item.get("disposition") == "removed"
    ]
    if recent_retired:
        lines.append("Claims retired by this audit — independently verify each disposition:")
        for item in recent_retired:
            lines.append(
                f"- {item.get('claim_id')} [{item.get('disposition')}]: "
                f"{item.get('anchor')} — {item.get('reason')}"
            )
    if state.get("debt"):
        lines.append(f"- AUDIT DEBT: {state['debt'].get('reason')}")
    return "\n".join(lines)


def render_trailer(state_raw: Any) -> str:
    state = normalize_state(state_raw)
    claims = list(state["claims"].values())
    counts = {verdict: sum(1 for c in claims if c.get("verdict") == verdict) for verdict in VERDICTS}
    lines = [
        f"CLAIM-REGISTER: {len(claims)} active external claims; "
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
    failure_phases = _source_failure_phases(
        claim.get("capture_provenance", []), claim.get("evidence", []),
    )
    if failure_phases and claim.get("verdict") == "unverified":
        for failure_phase in failure_phases:
            if failure_phase == "capture":
                lines.extend([
                    "  Evidence status: RETRIEVAL-FAILED (blocking; proposition not adjudicated)",
                    "  Next action: retry capture or supply another authoritative public URL; "
                    "do not remove or weaken the assertion solely because retrieval failed",
                ])
            elif failure_phase == "binding":
                lines.extend([
                    "  Evidence status: BINDING-FAILED (blocking; captured source not adjudicated)",
                    "  Next action: retry captured-text binding; do not remove or weaken the "
                    "assertion solely because binding failed",
                ])
            else:
                lines.extend([
                    "  Evidence status: ATTESTATION-FAILED (blocking; bound passage not adjudicated)",
                    "  Next action: retry cold authority-and-entailment attestation; do not remove "
                    "or weaken the assertion solely because attestation failed",
                ])
    elif claim.get("replacement"):
        lines.append(f"  Evidence-entailed replacement: {claim['replacement']}")
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
    removals = _removal_candidates(prior_state, plan_text)
    retained_full = evidence_context(
        prior_state, normalize_state(prior_state)["claims"].keys(),
    )
    stakes_text = stakes or "modest single-team internal tool; trusted operators; ordinary scale"
    return f"""You are the authoritative external-claim phase of an autonomous plan review.

You ARE the verifier. Never invoke MCP review tools (including any registered paranoia
server), plugins, other agents, or nested reviewers. Use only your own built-in web search.
Delegation would recurse and invalidate this phase.

STAKES: {stakes_text}

Read the entire plan. Inventory only load-bearing propositions about the external world whose
truth or authority could change feasibility, architecture, ordering, dependencies, rationale,
or acceptance. Eligible kinds are mechanically limited to:

- `fact`: an objective external-world state, event, quantity, identity, or history;
- `design_principle`: a requirement, constraint, or recommended principle issued by the
  authoritative external standard, regulator, protocol, platform, or vendor that governs the
  plan. A project team's chosen preference is not eligible merely because it is called a
  principle;
- `behavior`: documented or observable behavior promised by an external API, dependency,
  platform, protocol, service, or runtime on which the plan relies.

Every claim has scope `external`. Mechanically OMIT repository state, code paths, functions,
internal implementation behavior, internal history, whether this repository conforms, and
"missing atomic bridges" between internal steps. Those belong to the separate structural/code
review and tests. Also omit proposed decisions, local policies, authorizations, definitions,
intentions, instructions, subjective preferences, forecasts, and incidental observations.
Split eligible conjunctions into atomic propositions, but do not decompose an internal design
into a chain of repository-mechanical claims. Scan every heading, paragraph, list item, and
table row for the three eligible external kinds.

Use BUILT-IN web search for every retained claim. Search official/primary sources first:
first-party documentation, standards, statutes/regulators, government data, original
papers/datasets, and the entity's own records. Secondary reporting may corroborate or locate a
source. Reddit, forums, Stack Overflow, social media, wikis, blogs, and other UGC are leads or
conflict signals only; they can NEVER support or refute a governing verdict.

For every retained claim, decide supported, refuted, or unverified. A source verifies a
claim only when the exact quoted passage entails that exact atomic proposition. Every
source must have a canonical absolute web URL, title, publisher, precise
section/table/page location, exact passage, and an explanation of why that publisher governs
this proposition. Label source_kind honestly as primary, authoritative, secondary, or ugc.
A proposed replacement is allowed only when an authoritative passage entails
the replacement itself; evidence that merely refutes the old wording is not enough.
Preserve the original event, actor, date, modality, scope, and chronology when forming the
atomic proposition. An anchor saying that a dated audit/report occurred is not verified by
evidence that contains only the underlying condition. The current plan/dossier is the
assertion under review, not evidence for itself.
{_universal_scope_instruction()}

Prior packets below are candidate leads, never inherited verdicts. Re-open or search each
retained URL and return every still-present retained proposition as a full current claim/evidence
packet. `coverage.prior_assessments` must be empty: compact verdicts cannot cross the server
capture and cold-attestation boundary. The server rejects a missing retained ID in this round.

Use claims only for newly discovered or edited propositions. Set prior_claim_id only for the
exact same atomic proposition; use null for edited wording. Every absent prior claim needs one
entry in coverage.prior_dispositions. The only disposition is "removed", and it is valid only
when the old verbatim external anchor is absent from the current plan. If an eligible claim
became a local decision, edit away the old externally asserted wording; do not merely relabel it.
prior_claim_id is contextual only and cannot transfer identity to edited wording.

RETAINED CLAIMS REQUIRING FULL CURRENT PACKETS (JSON):
{retained_full}

ABSENT PRIOR ANCHOR CANDIDATES (JSON):
{removals}

The server mechanically confirmed that each candidate's old verbatim anchor is absent
from the current plan modulo whitespace. Do NOT re-emit an absent anchor as a claim. For
each candidate, either add a removed disposition after confirming the old proposition is
absent/superseded, or inventory the current edited assertion as a new claim AND disposition
the old packet. These are candidates, not automatic retirement: you remain responsible for
checking that removal does not hide a still-load-bearing current assertion.

PRIOR EVIDENCE PACKETS (JSON):
{prior}

Reply with only the marker and one JSON object. Do not use markdown fences. These are
CONCRETE literals, not pipe-delimited pseudo-enums. The shape is:

{AUDIT_MARKER}
{{"claims":[{{"kind":"design_principle","scope":"external","anchor":"verbatim plan text","proposition":"one atomic externally issued design principle","prior_claim_id":null,"verdict":"supported","evidence":[{{"url":"https://official.example/standard","title":"Official standard","publisher":"Issuing authority","source_kind":"primary","authority_basis":"The publisher issues the governing standard","location":"Section 2, table 1","quote":"Exact source passage","relation":"supports_claim"}}],"replacement":null,"rationale":"brief claim-specific assessment"}}],"coverage":{{"sections_scanned":3,"omitted_nonfacts":12,"prior_assessments":[],"prior_dispositions":[],"notes":"brief coverage note"}}}}

Allowed verdict literals: "supported", "refuted", "unverified".
Allowed kind literals: "fact", "design_principle", "behavior".
Allowed scope literal: "external".
Allowed relation literals: "supports_claim", "refutes_claim",
"supports_replacement", "context".

=== PLAN ===
{plan_text}"""


def targeted_audit_instructions(
    plan_text: str, prior_state: Any, stakes: str | None, frozen_ids: Iterable[str],
) -> str:
    """Build the post-round-1 verifier prompt over only the external edit cone."""
    frozen = frozenset(frozen_ids)
    state = normalize_state(prior_state)
    targeted_ids = set(state["claims"]) - frozen
    full_packet_ids = _full_packet_candidate_ids(prior_state, plan_text, frozen)
    prior = evidence_context(prior_state, targeted_ids)
    removals = _removal_candidates(prior_state, plan_text)
    full_packets = evidence_context(prior_state, full_packet_ids)
    changes = changed_plan_text(prior_state, plan_text)
    stakes_text = stakes or "modest single-team internal tool; trusted operators; ordinary scale"
    return f"""You are the targeted external-claim remediation phase of an autonomous plan review.

You ARE the verifier. Never invoke MCP review tools (including any registered paranoia
server), plugins, other agents, or nested reviewers. Use only your own built-in web search.
Delegation would recurse and invalidate this phase.

STAKES: {stakes_text}

Round 1 already exhaustively scanned the complete plan. The server has frozen exact,
unchanged SUPPORTED claims with authoritative packets. Do NOT reassess, search for, or emit
those frozen claims. Audit only (a) added/edited eligible external wording in the diff below, (b) each
retained refuted or unverified claim listed below, and (c) removed-anchor dispositions.
Follow dependencies from an edited claim when necessary, but do not inventory unchanged
settled prose again. This is a cost-control boundary, not a weaker authority rule.

Eligible external claims have exactly one of three kinds: `fact` for external-world states or
history, `design_principle` for a requirement/constraint/principle issued by the governing
external authority, and `behavior` for behavior promised by an external dependency, API,
platform, protocol, service, or runtime. Every claim has scope `external`.

Mechanically OMIT repository state, code paths, internal implementation behavior, internal
history, conformance of this repository, and internal function-to-function or
"missing atomic bridge" assertions. The separate structural/code review and tests own those.
Also omit local decisions, preferences, and project-authored principles that do not assert an
external authority.

For every eligible claim, use built-in web search and prefer official/primary
sources. Reddit, forums, Stack Overflow, social media, wikis, blogs and other UGC are leads
only and can NEVER govern support or refutation. Require an exact passage, canonical
location, publisher/authority basis, and a direct entailment relation. Split conjunctions
and ranges into atomic propositions. A replacement is allowed only when authoritative
evidence entails the replacement itself.

Every item in RETAINED CLAIMS REQUIRING FULL EVIDENCE PACKETS must be re-researched and
returned in `claims` with its exact unchanged proposition and a current, complete evidence
packet. Do not put these IDs in `prior_assessments`: only a fresh server capture plus cold
attestation can change or retain an unresolved verdict. The server preserves identity by exact
proposition. `coverage.prior_assessments` must be empty in the captured-evidence path.

Preserve event, actor, date, modality, scope, and chronology: evidence of an underlying
condition does not prove that a dated external audit/report event occurred. Use claims only
for new or edited eligible external propositions. Every absent prior claim
needs a `removed` disposition; edited wording mints a new claim and does not inherit the old
identity or verdict.
{_universal_scope_instruction()}

RETAINED CLAIMS REQUIRING FULL EVIDENCE PACKETS (JSON):
{full_packets}

ABSENT PRIOR ANCHOR CANDIDATES (JSON):
{removals}

PRIOR EVIDENCE PACKETS FOR THE TARGETED SET (JSON):
{prior}

CURRENT PLAN EDIT CONE (unified diff with context):
{changes}

Reply with only the marker and one JSON object; no markdown fence:

{AUDIT_MARKER}
{{"claims":[{{"kind":"behavior","scope":"external","anchor":"verbatim current-plan text","proposition":"one atomic externally promised behavior","prior_claim_id":null,"verdict":"supported","evidence":[{{"url":"https://official.example/reference","title":"Official reference","publisher":"Issuing authority","source_kind":"primary","authority_basis":"The publisher defines the external system behavior","location":"Section 2, table 1","quote":"Exact source passage","relation":"supports_claim"}}],"replacement":null,"rationale":"brief claim-specific assessment"}}],"coverage":{{"sections_scanned":1,"omitted_nonfacts":1,"prior_assessments":[],"prior_dispositions":[],"notes":"targeted edit-cone audit"}}}}

Allowed kinds: "fact", "design_principle", "behavior". Allowed verdicts: "supported",
"refuted", "unverified". Allowed scope: "external". Allowed relations: "supports_claim", "refutes_claim",
"supports_replacement", "context". The server validates anchors against the full current
plan and rejects omission of any listed unresolved retained ID."""


def retry_instructions(
    error: AuditError, plan_text: str, prior_state: Any,
    frozen_ids: Iterable[str] = (),
) -> str:
    frozen = frozenset(frozen_ids)
    state = normalize_state(prior_state)
    targeted_ids = set(state["claims"]) - frozen
    full_packet_ids = _full_packet_candidate_ids(prior_state, plan_text, frozen)
    removals = _removal_candidates(prior_state, plan_text)
    prior = evidence_context(prior_state, targeted_ids)
    full_packets = evidence_context(prior_state, full_packet_ids)
    scope_label = "CURRENT PLAN EDIT CONE" if frozen else "PLAN"
    scope_text = changed_plan_text(prior_state, plan_text) if frozen else plan_text
    frozen_note = (
        "This is a targeted later-round correction. Do not search for or emit the frozen "
        "supported IDs below; correct only the edit cone and unresolved checklist.\n\n"
        "FROZEN SUPPORTED IDS (JSON):\n"
        + json.dumps(sorted(frozen), ensure_ascii=False, separators=(",", ":"))
    ) if frozen else ""
    return f"""Your claim audit was rejected and no new verdict was applied.

Reason: {error.reason}
Rejected payload sha256: {error.raw_sha256}

Return the COMPLETE corrected audit for the plan, not a patch. Use exactly one
{AUDIT_MARKER} marker followed by one JSON object and nothing else. Every claim uses the
literal kind `fact`, `design_principle`, or `behavior` and the literal scope `external`.
Never write a pseudo-enum. Preserve valid source packets, fix the structural error, and do
not weaken evidence requirements.
Do not invoke MCP tools, paranoia-local, plugins, other agents, or nested reviewers.
Repository state, code paths, internal history, implementation conformance, and internal
function bridges are mechanically out of scope for this register; omit them because the
structural/code review and tests own them. Do retain externally issued requirements/design
principles and behavior promised by external systems, not only historical facts. Require
authoritative web evidence and preserve any claimed event, date, actor, modality, scope, and
chronology instead of weakening the proposition to an underlying condition.

{frozen_note}

RETAINED CLAIMS REQUIRING COMPLETE REPLACEMENT EVIDENCE PACKETS (JSON):
{full_packets}

Return each of these exact propositions as a full item in `claims`. Do not compactly
assess them: their retained packets are unresolved or non-freezable and cannot govern.

`coverage.prior_assessments` must be an empty array. Compact retained verdicts cannot cross
the server-capture and cold-attestation boundary.

ABSENT PRIOR ANCHOR CANDIDATES (JSON):
{removals}

Do not re-emit these absent old anchors. Confirm and disposition each genuinely removed
packet, and separately inventory any edited current assertion under its verbatim anchor.

PRIOR EVIDENCE PACKETS (JSON):
{prior}

=== {scope_label} ===
{scope_text}"""


def _one_line(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return " ".join(value.split())


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _anchor_in_plan(anchor: str, plan_text: str) -> bool:
    return _collapse_whitespace(anchor) in _collapse_whitespace(plan_text)


UNIVERSAL_FORMS = (
    "all", "always", "any", "anybody", "anyone", "anything", "anywhere", "each",
    "entire", "every", "everybody", "everyone", "everything", "everywhere",
    "in all cases", "invariably", "never", "no", "none", "throughout",
    "under all circumstances", "universally", "whole", "wholly", "without exception",
)
_UNIVERSAL_QUANTIFIER = re.compile(
    rf"\b(?:{'|'.join(map(re.escape, UNIVERSAL_FORMS))})\b", re.IGNORECASE,
)


def _universal_scope_instruction() -> str:
    examples = ", ".join(f"`{term}`" for term in UNIVERSAL_FORMS)
    return (
        f"Do not introduce {examples} into a proposition unless that exact universal "
        "form occurs in the verbatim anchor. The server rejects that scope expansion."
    )


def _introduced_universal_quantifiers(anchor: str, proposition: str) -> tuple[str, ...]:
    """Reject an extractor widening bounded wording into a universal proposition."""
    anchor_terms = {
        match.group(0).casefold()
        for match in _UNIVERSAL_QUANTIFIER.finditer(anchor)
    }
    proposition_terms = {
        match.group(0).casefold()
        for match in _UNIVERSAL_QUANTIFIER.finditer(proposition)
    }
    return tuple(sorted(proposition_terms - anchor_terms))


def _assertion_binding_unchanged(anchor: str, previous: str, current: str) -> bool:
    """Whether an anchor still occurs in the same assertion-bearing document context.

    Substring presence alone freezes quoted, negated, or relocated wording.  Markdown
    blocks plus their heading path are a conservative occurrence identity: wrapping can
    change without invalidation, while an edited assertion or section move is re-audited.
    """
    if not isinstance(anchor, str) or not anchor.strip():
        return False
    previous_contexts = _assertion_contexts(previous, anchor)
    current_contexts = _assertion_contexts(current, anchor)
    return (
        len(previous_contexts) == 1
        and len(current_contexts) == 1
        and previous_contexts == current_contexts
    )


def _assertion_contexts(
    plan_text: str, anchor: str,
) -> list[
    tuple[tuple[tuple[int, str], ...], tuple[tuple[int, str], ...], str]
]:
    needle = _collapse_whitespace(anchor)
    contexts: list[
        tuple[tuple[tuple[int, str], ...], tuple[tuple[int, str], ...], str]
    ] = []
    heading_path: list[tuple[int, str]] = []
    list_ancestors: list[tuple[int, str]] = []
    block: list[str] = []
    block_kind: str | None = None
    block_list_path: tuple[tuple[int, str], ...] = ()

    def flush() -> None:
        nonlocal block_kind, block_list_path
        if not block:
            return
        body = _collapse_whitespace(" ".join(block))
        contexts.extend(
            [(tuple(heading_path), block_list_path, body)] * body.count(needle)
        )
        block.clear()
        block_kind = None
        block_list_path = ()

    def set_heading(level: int, text: str) -> None:
        heading_path[:] = [item for item in heading_path if item[0] < level]
        heading_path.append((level, _collapse_whitespace(text)))
        list_ancestors.clear()

    lines = plan_text.splitlines()
    in_fence: tuple[str, int] | None = None
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})", raw_line)
        if in_fence:
            closing = re.match(
                rf"^ {{0,3}}{re.escape(in_fence[0])}{{{in_fence[1]},}}\s*$",
                raw_line,
            )
            if closing:
                in_fence = None
            index += 1
            continue
        if fence:
            flush()
            in_fence = (fence.group(1)[0], len(fence.group(1)))
            index += 1
            continue
        leading = len(raw_line) - len(raw_line.lstrip(" "))
        if raw_line.startswith("\t") or (leading and block_kind != "list"):
            flush()
            index += 1
            continue
        if (
            stripped
            and index + 1 < len(lines)
            and re.match(r"^ {0,3}(=+|-+)\s*$", lines[index + 1])
        ):
            flush()
            underline = lines[index + 1].lstrip()
            level = 1 if underline.startswith("=") else 2
            set_heading(level, stripped)
            index += 2
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush()
            level = len(heading.group(1))
            set_heading(level, heading.group(2))
            index += 1
            continue
        if not stripped:
            flush()
            index += 1
            continue
        if re.match(r"^(?:[-*+] |\d+[.)] )", stripped):
            flush()
            list_ancestors[:] = [
                item for item in list_ancestors if item[0] < leading
            ]
            # The current item's own physical first line belongs to its semantic
            # body, not its ancestry. Keeping it in both made a harmless Markdown
            # reflow change identity because continuation-line marker text split an
            # otherwise exact anchor. Parent list items still identify relocation.
            block_list_path = tuple(list_ancestors)
            list_ancestors.append((leading, stripped))
            block_kind = "list"
            block.append(stripped)
            index += 1
            continue
        if block_kind == "list":
            block.append(stripped)
            index += 1
            continue
        if stripped.startswith("|"):
            if block_kind != "table":
                flush()
                block_kind = "table"
            block.append(stripped)
            index += 1
            continue
        if block_kind == "table":
            flush()
        list_ancestors.clear()
        block_kind = "plain"
        block.append(stripped)
        index += 1
    flush()
    return contexts


def _removal_candidates(prior_state: Any, plan_text: str) -> str:
    state = normalize_state(prior_state)
    candidates = [
        {"claim_id": claim_id, "anchor": claim.get("anchor")}
        for claim_id, claim in state["claims"].items()
        if isinstance(claim, dict)
        and isinstance(claim.get("anchor"), str)
        and claim["anchor"].strip()
        and not _anchor_in_plan(claim["anchor"], plan_text)
    ]
    return json.dumps(candidates, ensure_ascii=False, separators=(",", ":"))


def _full_packet_candidate_ids(
    prior_state: Any, plan_text: str, exclude_ids: Iterable[str] = (),
) -> set[str]:
    """Every non-frozen retained claim requires a current captured packet."""
    state = normalize_state(prior_state)
    excluded = frozenset(exclude_ids)
    return {
        claim_id for claim_id, claim in state["claims"].items()
        if claim_id not in excluded
        and isinstance(claim, dict)
        and _anchor_in_plan(claim.get("anchor", ""), plan_text)
    }


def _mint(lineage_id: str, seq: int, proposition: str) -> str:
    digest = hashlib.sha256(
        f"{lineage_id}\0claim\0{seq}\0{proposition}".encode("utf-8")
    ).hexdigest()[:10]
    return f"C-{digest}"


def _is_ugc_host(host: str) -> bool:
    return sources.is_ugc_host(host)


def _excerpt(raw: str) -> str:
    if len(raw) <= DIAGNOSTIC_CHARS:
        return raw
    half = DIAGNOSTIC_CHARS // 2
    return raw[:half] + "\n… [bounded rejected output] …\n" + raw[-half:]
