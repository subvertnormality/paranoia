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
import subprocess
from copy import deepcopy
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
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
    if raw.get("version") != 1:
        return state
    state.update({
        "rounds": max(0, int(raw.get("rounds", 0))),
        "next_seq": max(1, int(raw.get("next_seq", 1))),
        "plan_digest": raw.get("plan_digest"),
        "plan_snapshot": (
            raw.get("plan_snapshot")
            if isinstance(raw.get("plan_snapshot"), str) else None
        ),
        "claims": deepcopy(raw.get("claims", {})) if isinstance(raw.get("claims"), dict) else {},
        "retired": deepcopy(raw.get("retired", [])) if isinstance(raw.get("retired"), list) else [],
        "debt": deepcopy(raw.get("debt")),
    })
    return state


def has_prior_snapshot(state_raw: Any) -> bool:
    """Whether a later round can be scoped to edits from a successful prior audit."""
    return normalize_state(state_raw).get("plan_snapshot") is not None


def frozen_supported_ids(
    state_raw: Any, plan_text: str, *, repo: Path | None = None,
) -> frozenset[str]:
    """Return exact supported claims that need no new model/web judgement.

    External packets are immutable evidence captured by the exhaustive round. Repository
    packets additionally have their quoted bytes checked against the current worktree, so a
    local edit cannot silently inherit support. Edited/removed anchors and every unresolved
    claim remain outside this set and therefore enter targeted remediation.
    """
    state = normalize_state(state_raw)
    if state.get("plan_snapshot") is None:
        return frozenset()
    frozen: set[str] = set()
    for claim_id, record in state["claims"].items():
        if not isinstance(record, dict) or record.get("verdict") != "supported":
            continue
        if not _anchor_in_plan(record.get("anchor", ""), plan_text):
            continue
        evidence = [item for item in record.get("evidence", []) if isinstance(item, dict)]
        supports = [
            item for item in evidence
            if _qualifying(item, record.get("scope", ""))
            and item.get("relation") == "supports_claim"
        ]
        if not supports:
            continue
        if record.get("scope") == "repository":
            if repo is None or not any(_repository_packet_current(item, repo) for item in supports):
                continue
        frozen.add(claim_id)
    return frozenset(frozen)


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


_GIT_REV = re.compile(r"[0-9a-fA-F]{7,64}(?:(?:\^+)|(?:~[0-9]+))?")


def _repository_source_bytes(evidence: dict[str, str], repo: Path) -> bytes | None:
    raw = evidence.get("url", "")
    if not raw.startswith("repo://"):
        return None
    relative = raw[len("repo://"):].split("#", 1)[0]
    if relative.startswith("git/"):
        spec = relative[len("git/"):]
        if ":" in spec:
            revision, relative = spec.split(":", 1)
            candidate = Path(relative)
            if (
                not _GIT_REV.fullmatch(revision) or not relative
                or candidate.is_absolute() or ".." in candidate.parts
            ):
                return None
            command = ["git", "show", f"{revision}:{relative}"]
        else:
            if not _GIT_REV.fullmatch(spec):
                return None
            command = ["git", "show", "--stat", "--format=fuller", spec]
        try:
            completed = subprocess.run(
                command, cwd=repo, capture_output=True, timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return completed.stdout if completed.returncode == 0 else None
    candidate = Path(relative)
    if not relative or candidate.is_absolute() or ".." in candidate.parts:
        return None
    try:
        return (repo / candidate).read_bytes()
    except OSError:
        return None


def _repository_evidence_resolution(
    evidence: dict[str, str], repo: Path,
) -> tuple[bool, str]:
    """Resolve exact bytes and return an accurate canonical repository URL."""
    raw = evidence.get("url", "")
    source = _repository_source_bytes(evidence, repo)
    if source is None:
        return False, raw
    quote = evidence.get("quote", "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{64}", quote):
        if hashlib.sha256(source).hexdigest() != quote.lower():
            return False, raw
        return True, raw.split("#", 1)[0]
    text = source.decode("utf-8", "replace")
    if _collapse_whitespace(quote) not in _collapse_whitespace(text):
        return False, raw
    # Commit-level packets cite rendered Git metadata rather than a path; keep their
    # URL stable. File packets get a mechanically accurate line hint when the exact
    # passage can be located without interpretation.
    base = raw.split("#", 1)[0]
    relative = base[len("repo://"):] if base.startswith("repo://") else ""
    if relative.startswith("git/") and ":" not in relative[len("git/"):]:
        return True, base
    position = text.find(quote)
    if position < 0:
        return True, base
    start = text.count("\n", 0, position) + 1
    end = start + quote.count("\n")
    suffix = f"#L{start}" if end == start else f"#L{start}-L{end}"
    return True, base + suffix


def _repository_quote_present(evidence: dict[str, str], repo: Path) -> bool:
    return _repository_evidence_resolution(evidence, repo)[0]


def _repository_packet_current(evidence: dict[str, str], repo: Path) -> bool:
    valid, canonical = _repository_evidence_resolution(evidence, repo)
    return valid and canonical == evidence.get("url")


def _canonicalize_repository_evidence(
    evidence: dict[str, Any], repo: Path,
) -> dict[str, Any]:
    result = deepcopy(evidence)
    valid, canonical = _repository_evidence_resolution(result, repo)
    if valid:
        result["url"] = canonical
    return result


def parse_audit(
    text: str, plan_text: str, *, allow_partial: bool = False,
    repo: Path | None = None,
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
            claim = _validate_claim(item, plan_text, repo=repo)
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
    dispositions = _validate_dispositions(coverage.get("prior_dispositions", []), text)
    assessments = _validate_assessments(coverage.get("prior_assessments", []), text)
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
            or fields != id_fields | reason_fields | {"disposition"}
        ):
            raise AuditError(
                f"prior disposition {index} must contain exactly claim_id, disposition, "
                "and reason (prior_claim_id and rationale are accepted as wire aliases)",
                text,
            )
        claim_id = _one_line(item[next(iter(id_fields))], "disposition.claim_id")
        disposition = _one_line(item["disposition"], "disposition.disposition")
        reason = _one_line(item.get("reason", item.get("rationale")), "disposition.reason")
        if disposition != "removed":
            raise AuditError(f"prior disposition {index} must be removed", text)
        if claim_id in seen:
            raise AuditError(f"duplicate disposition for prior claim {claim_id}", text)
        seen.add(claim_id)
        result.append({"claim_id": claim_id, "disposition": disposition, "reason": reason})
    return tuple(result)


def _validate_assessments(raw: Any, text: str) -> tuple[dict[str, str], ...]:
    """Validate compact current-round judgements over retained exact claims."""
    if not isinstance(raw, list):
        raise AuditError("coverage.prior_assessments must be an array", text)
    if len(raw) > MAX_ACTIVE_CLAIMS:
        raise AuditError(
            f"audit returned {len(raw)} retained assessments; safety ceiling is "
            f"{MAX_ACTIVE_CLAIMS}", text,
        )
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or set(item) != {"claim_id", "verdict", "rationale"}:
            raise AuditError(
                f"prior assessment {index} must contain exactly claim_id, verdict, and rationale",
                text,
            )
        claim_id = _one_line(item["claim_id"], "assessment.claim_id")
        verdict = _one_line(item["verdict"], "assessment.verdict")
        rationale = _one_line(item["rationale"], "assessment.rationale")
        if verdict not in VERDICTS:
            raise AuditError(
                f"prior assessment {index} verdict must be one of {sorted(VERDICTS)}", text,
            )
        if claim_id in seen:
            raise AuditError(f"duplicate assessment for prior claim {claim_id}", text)
        seen.add(claim_id)
        result.append({"claim_id": claim_id, "verdict": verdict, "rationale": rationale})
    return tuple(result)


def _validate_claim(
    item: Any, plan_text: str, *, repo: Path | None = None,
) -> dict[str, Any]:
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
    # Markdown frequently wraps one sentence across physical lines. Verbatim means the
    # same characters/tokens modulo whitespace, not identical line wrapping. Punctuation
    # and case remain exact, so this cannot recreate normalized identity collisions.
    if not _anchor_in_plan(anchor, plan_text):
        raise ValueError(
            "anchor is not a verbatim substring of the current plan modulo whitespace"
        )
    verdict = item["verdict"]
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")
    evidence = item["evidence"]
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE_PER_CLAIM:
        raise ValueError(f"evidence must be an array of at most {MAX_EVIDENCE_PER_CLAIM}")
    checked = [_validate_evidence(e, scope, repo=repo) for e in evidence]
    replacement = item["replacement"]
    if replacement is not None:
        replacement = _one_line(replacement, "replacement")
    prior = item.get("prior_claim_id")
    if prior is not None:
        prior = _one_line(prior, "prior_claim_id")
    rationale = str(item.get("rationale", "")).strip()

    qualifying = [e for e in checked if _qualifying(e, scope)]
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
        rationale = f"{rationale} Server demotion: {demotion}.".strip()
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
        "kind": "fact", "scope": scope, "anchor": anchor,
        "proposition": proposition, "verdict": verdict, "evidence": checked,
        "replacement": replacement, "prior_claim_id": prior, "rationale": rationale,
    }


def _validate_evidence(
    item: Any, scope: str, *, repo: Path | None = None,
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
    host = (urlparse(result["url"]).hostname or "").lower()
    if scope == "repository":
        if result["source_kind"] != "repository" or not result["url"].startswith("repo://"):
            result["relation"] = "context"
        elif repo is not None:
            valid, canonical = _repository_evidence_resolution(result, repo)
            if not valid:
                raise ValueError(
                    "repository evidence URL does not resolve to bytes containing its exact "
                    f"quote or matching whole-file SHA-256: {result['url']}"
                )
            result["url"] = canonical
    elif result["source_kind"] == "repository" or not host:
        result["relation"] = "context"
    if _is_ugc_host(host):
        # Normalize, rather than reject: the packet remains useful as a lead or conflict,
        # while verdict validation below refuses to let it close a claim.
        result["source_kind"] = "ugc"
    return result


def _qualifying(evidence: dict[str, str], scope: str) -> bool:
    if scope == "repository":
        return (
            evidence["source_kind"] == "repository"
            and evidence["url"].startswith("repo://")
        )
    return bool(urlparse(evidence["url"]).hostname) and (
        evidence["source_kind"] in AUTHORITATIVE_KINDS
    )


def reconcile(
    prior_raw: Any, audit: Audit, *, lineage_id: str, round_no: int, plan_text: str,
    frozen_ids: Iterable[str] = (), repo: Path | None = None,
) -> dict[str, Any]:
    """Replace the active inventory with the current audit, retaining identity/evidence.

    Every verdict in ``audit`` has just been assessed against the current proposition.
    ``frozen_ids`` are the narrow exception: exact unchanged supported propositions retain
    their exhaustive-round packet without another model/web judgement.
    """
    frozen = frozenset(frozen_ids)
    validate_prior_coverage(
        prior_raw, audit, plan_text=plan_text, frozen_ids=frozen, repo=repo,
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

    # Unresolved exact retained claims use a compact current-round assessment. The reviewer
    # has re-opened/re-entailled the retained packet, while the server owns the anchor,
    # proposition, and evidence bytes. This avoids asking the model to reproduce large
    # packets merely to prove it did not forget them.
    for assessment in audit.assessments:
        claim_id = assessment["claim_id"]
        previous = old[claim_id]
        record = deepcopy(previous)
        verdict = assessment["verdict"]
        rationale = assessment["rationale"]
        if repo is not None and record.get("scope") == "repository":
            record["evidence"] = [
                _canonicalize_repository_evidence(evidence, repo)
                if isinstance(evidence, dict) else evidence
                for evidence in record.get("evidence", [])
            ]
            relation = {
                "supported": "supports_claim", "refuted": "refutes_claim",
            }.get(verdict)
            if relation and not any(
                isinstance(evidence, dict)
                and _qualifying(evidence, "repository")
                and evidence.get("relation") == relation
                and _repository_quote_present(evidence, repo)
                for evidence in record.get("evidence", [])
            ):
                verdict = "unverified"
                rationale = (
                    f"{rationale} Server demotion: the retained repository packet no "
                    "longer resolves to its exact bytes; emit a corrected full packet."
                ).strip()
        record.update({
            "claim_id": claim_id,
            "verdict": verdict,
            "verified_round": round_no,
            "rationale": rationale,
        })
        if verdict != "refuted":
            record["replacement"] = None
        elif not any(
            _qualifying(evidence, record.get("scope", ""))
            and evidence.get("relation") == "supports_replacement"
            for evidence in record.get("evidence", [])
            if isinstance(evidence, dict)
        ):
            record["replacement"] = None
        current[claim_id] = record
        used.add(claim_id)

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
    assessed = {item["claim_id"] for item in audit.assessments}
    overlap = emitted & assessed
    if overlap:
        raise AuditError(
            "retained claims were both fully emitted and compactly assessed: "
            + ", ".join(sorted(overlap)), raw,
        )
    frozen_overlap = emitted & frozen
    if frozen_overlap:
        raise AuditError(
            "frozen claims were re-emitted by the targeted audit: "
            + ", ".join(sorted(frozen_overlap)), raw,
        )
    for item in audit.assessments:
        claim_id = item["claim_id"]
        record = old.get(claim_id)
        if not isinstance(record, dict):
            raise AuditError(f"assessment references unknown prior claim {claim_id}", raw)
        if not _anchor_in_plan(record.get("anchor", ""), plan_text):
            raise AuditError(
                f"assessment references absent prior anchor {claim_id}; use a removal disposition",
                raw,
            )
        evidence = [e for e in record.get("evidence", []) if isinstance(e, dict)]
        qualifying = [e for e in evidence if _qualifying(e, record.get("scope", ""))]
        relation = {
            "supported": "supports_claim", "refuted": "refutes_claim",
        }.get(item["verdict"])
        if relation and not any(e.get("relation") == relation for e in qualifying):
            raise AuditError(
                f"assessment {claim_id} says {item['verdict']} but its retained packet "
                f"has no qualifying {relation} evidence; emit a full current claim packet",
                raw,
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
    missing = expected - emitted - assessed - frozen
    if missing:
        raise AuditError(
            "missing current assessments for retained claims: " + ", ".join(sorted(missing)),
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
    """Give the structural reviewer enough to detect omissions and use verified facts."""
    state = normalize_state(state_raw)
    lines = [
        "=== FACTUAL CLAIM REGISTER ===",
        "This inventory was independently researched before your structural review. Check the plan for any omitted load-bearing factual assertion; an omission is a blocking finding.",
    ]
    for claim_id, claim in state["claims"].items():
        lines.extend([
            f"- CLAIM {claim_id} [{claim.get('scope')}/{claim.get('verdict')}]",
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
    removals = _removal_candidates(prior_state, plan_text)
    assessments = _assessment_candidates(prior_state, plan_text)
    stakes_text = stakes or "modest single-team internal tool; trusted operators; ordinary scale"
    return f"""You are the factual-verification phase of an autonomous plan review.

You ARE the verifier. Never invoke MCP review tools (including any registered paranoia
server), plugins, other agents, or nested reviewers. Inspect the repository and use only
your own built-in web search. Delegation would recurse and invalidate this phase.

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
repository facts cite repo://path#Lx-Ly and quote the exact bytes. Historical bytes use
repo://git/<hex-revision>:<path>; commit-level evidence uses repo://git/<hex-revision>.
Every repository URL must resolve in this repository and contain the exact quote or the server
will reject the packet. For external facts, record the
canonical absolute URL, title, publisher, precise section/table/page location, exact
passage, and why that publisher is authoritative for this proposition. Label source_kind honestly as primary, authoritative, secondary, ugc, or
repository. A proposed replacement is allowed only when an authoritative passage entails
the replacement itself; evidence that merely refutes the old wording is not enough.

Prior packets below are CANDIDATE evidence, never inherited verdicts. Re-open or search
each retained URL as needed and re-assess entailment against the CURRENT proposition.
For every item in RETAINED EXACT CLAIMS, return exactly one compact entry in
coverage.prior_assessments. Do not repeat that unchanged claim or its evidence in claims.
The server owns its exact anchor, proposition, and retained packet; your compact verdict is
the current-round re-entailment judgement. If retained evidence cannot support/refute the
current verdict, return unverified, or emit a full claim packet with new current evidence
instead of a compact assessment. The server rejects a missing retained ID in this same round.

Use claims only for newly discovered or edited propositions. Set prior_claim_id only for the
exact same atomic proposition; use null for edited wording. Every absent prior claim needs one
entry in coverage.prior_dispositions. The only disposition is "removed", and it is valid only
when the old verbatim factual anchor is absent from the current plan. If a fact became a
decision/requirement, edit away the old factual wording; do not merely relabel it.
prior_claim_id is contextual only and cannot transfer identity to edited wording.

RETAINED EXACT CLAIMS REQUIRING ASSESSMENT (JSON):
{assessments}

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
{{"claims":[{{"kind":"fact","scope":"external","anchor":"verbatim plan text","proposition":"one new atomic factual proposition","prior_claim_id":null,"verdict":"supported","evidence":[{{"url":"https://official.example/page","title":"Official title","publisher":"Issuing authority","source_kind":"primary","authority_basis":"The publisher issued the standard being described","location":"Section 2, table 1","quote":"Exact source passage","relation":"supports_claim"}}],"replacement":null,"rationale":"brief claim-specific assessment"}}],"coverage":{{"sections_scanned":3,"omitted_nonfacts":12,"prior_assessments":[{{"claim_id":"C-retained","verdict":"supported","rationale":"Retained exact passage still entails the unchanged proposition."}}],"prior_dispositions":[],"notes":"brief coverage note"}}}}

Allowed verdict literals: "supported", "refuted", "unverified".
Allowed scope literals: "external", "repository".
Allowed relation literals: "supports_claim", "refutes_claim",
"supports_replacement", "context".

=== PLAN ===
{plan_text}"""


def targeted_audit_instructions(
    plan_text: str, prior_state: Any, stakes: str | None, frozen_ids: Iterable[str],
) -> str:
    """Build the post-round-1 verifier prompt over only the factual edit cone."""
    frozen = frozenset(frozen_ids)
    state = normalize_state(prior_state)
    targeted_ids = set(state["claims"]) - frozen
    full_packet_ids = _full_packet_candidate_ids(prior_state, plan_text, frozen)
    prior = evidence_context(prior_state, targeted_ids)
    removals = _removal_candidates(prior_state, plan_text)
    assessments = _assessment_candidates(
        prior_state, plan_text, exclude_ids=frozen | full_packet_ids,
    )
    full_packets = evidence_context(prior_state, full_packet_ids)
    changes = changed_plan_text(prior_state, plan_text)
    stakes_text = stakes or "modest single-team internal tool; trusted operators; ordinary scale"
    return f"""You are the targeted factual-remediation phase of an autonomous plan review.

You ARE the verifier. Never invoke MCP review tools (including any registered paranoia
server), plugins, other agents, or nested reviewers. Inspect the repository and use only
your own built-in web search. Delegation would recurse and invalidate this phase.

STAKES: {stakes_text}

Round 1 already exhaustively scanned the complete plan. The server has frozen exact,
unchanged SUPPORTED claims with authoritative packets. Do NOT reassess, search for, or emit
those frozen claims. Audit only (a) added/edited factual wording in the diff below, (b) each
retained refuted or unverified claim listed below, and (c) removed-anchor dispositions.
Follow dependencies from an edited claim when necessary, but do not inventory unchanged
settled prose again. This is a cost-control boundary, not a weaker authority rule.

For every in-scope external claim, use built-in web search and prefer official/primary
sources. Reddit, forums, Stack Overflow, social media, wikis, blogs and other UGC are leads
only and can NEVER govern support or refutation. Require an exact passage, canonical
location, publisher/authority basis, and a direct entailment relation. Split conjunctions
and ranges into atomic propositions. A replacement is allowed only when authoritative
evidence entails the replacement itself.

For repository evidence use repo://path#Lx-Ly for current bytes,
repo://git/<hex-revision>:<path> for historical bytes, or repo://git/<hex-revision> for a
commit-level packet. Every location must resolve and contain the exact quote; the server rejects
malformed identifiers, missing paths, and invented or truncated passages.

Every item in RETAINED CLAIMS REQUIRING FULL EVIDENCE PACKETS must be re-researched and
returned in `claims` with its exact unchanged proposition and a current, complete evidence
packet. Do not put these IDs in `prior_assessments`: their old packets were unverified or
could not be frozen, so a compact verdict cannot repair them. The server preserves their
identity by exact proposition. Items in RETAINED REFUTED CLAIMS may instead receive one
compact current judgement in `coverage.prior_assessments` while their anchor remains.

OMIT decisions, policies, authorizations, requirements, definitions, intentions,
instructions, preferences, forecasts, and incidental facts. They do not enter active
inventory. Use claims only for new or edited factual propositions. Every absent prior claim
needs a `removed` disposition; edited wording mints a new claim and does not inherit the old
identity or verdict.

RETAINED CLAIMS REQUIRING FULL EVIDENCE PACKETS (JSON):
{full_packets}

RETAINED REFUTED CLAIMS ELIGIBLE FOR COMPACT ASSESSMENT (JSON):
{assessments}

ABSENT PRIOR ANCHOR CANDIDATES (JSON):
{removals}

PRIOR EVIDENCE PACKETS FOR THE TARGETED SET (JSON):
{prior}

CURRENT PLAN EDIT CONE (unified diff with context):
{changes}

Reply with only the marker and one JSON object; no markdown fence:

{AUDIT_MARKER}
{{"claims":[{{"kind":"fact","scope":"external","anchor":"verbatim current-plan text","proposition":"one atomic factual proposition","prior_claim_id":null,"verdict":"supported","evidence":[{{"url":"https://official.example/page","title":"Official title","publisher":"Issuing authority","source_kind":"primary","authority_basis":"The publisher issued the fact being described","location":"Section 2, table 1","quote":"Exact source passage","relation":"supports_claim"}}],"replacement":null,"rationale":"brief claim-specific assessment"}}],"coverage":{{"sections_scanned":1,"omitted_nonfacts":1,"prior_assessments":[],"prior_dispositions":[],"notes":"targeted edit-cone audit"}}}}

Allowed verdicts: "supported", "refuted", "unverified". Allowed scopes: "external",
"repository". Allowed relations: "supports_claim", "refutes_claim",
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
    assessments = _assessment_candidates(
        prior_state, plan_text, exclude_ids=frozen | full_packet_ids,
    )
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
literal "kind":"fact"; never write "fact|decision" or another pseudo-enum. Preserve
valid source packets, fix the structural error, and do not weaken evidence requirements.
Do not invoke MCP tools, paranoia-local, plugins, other agents, or nested reviewers.

{frozen_note}

RETAINED CLAIMS REQUIRING COMPLETE REPLACEMENT EVIDENCE PACKETS (JSON):
{full_packets}

Return each of these exact propositions as a full item in `claims`. Do not compactly
assess them: their retained packets are unresolved or non-freezable and cannot govern.

RETAINED REFUTED CLAIMS REQUIRING ONE ASSESSMENT EACH (JSON):
{assessments}

Return each retained exact ID once in coverage.prior_assessments using exactly claim_id,
verdict, and rationale. Do not repeat unchanged packets in claims. A missing ID is invalid.

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


def _assessment_candidates(
    prior_state: Any, plan_text: str, *, exclude_ids: Iterable[str] = (),
) -> str:
    state = normalize_state(prior_state)
    excluded = frozenset(exclude_ids)
    candidates = [
        {
            "claim_id": claim_id,
            "anchor": claim.get("anchor"),
            "proposition": claim.get("proposition"),
        }
        for claim_id, claim in state["claims"].items()
        if claim_id not in excluded
        and isinstance(claim, dict)
        and isinstance(claim.get("anchor"), str)
        and claim["anchor"].strip()
        and _anchor_in_plan(claim["anchor"], plan_text)
    ]
    return json.dumps(candidates, ensure_ascii=False, separators=(",", ":"))


def _full_packet_candidate_ids(
    prior_state: Any, plan_text: str, exclude_ids: Iterable[str] = (),
) -> set[str]:
    """Claims whose retained evidence cannot be repaired by a compact verdict."""
    state = normalize_state(prior_state)
    excluded = frozenset(exclude_ids)
    return {
        claim_id for claim_id, claim in state["claims"].items()
        if claim_id not in excluded
        and isinstance(claim, dict)
        and claim.get("verdict") != "refuted"
        and _anchor_in_plan(claim.get("anchor", ""), plan_text)
    }


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
