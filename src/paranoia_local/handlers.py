"""Tool dispatch logic, separated from MCP wiring so it is unit-testable with
an injected fake engine and clock.

Each handler: resolve inputs (call arg > `.paranoia.toml` > default), build the
task body, compose it with the adversarial instructions, run the reviewer in
the right working directory (an isolated worktree for committed reviews, the
live repo for dirty ones), write an audit record, and return the review with a
footer exposing the session reference for `rebut`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from . import arbitration, class_closure as cc
from . import engines as eng, external_sources, inert_git, inert_tree
from . import logs, orientation, plan_claims as pc, prompts, review_census as rc
from . import staged_protocol as sp
from .config import load_repo_config, resolve
from .engines import Engine, Review
from .worktree import worktree_at



Clock = Callable[[], str]

PLAN_EVIDENCE_PHASE_TIMEOUT_SEC = 300
PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC = 300
PLAN_EVIDENCE_SCHEDULING_SLACK_SEC = 60
PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC = 6960
PLAN_REVIEW_TOTAL_TIMEOUT_SEC = 7080
PLAN_STRUCTURAL_PHASE_TIMEOUT_SEC = 2400
PLAN_REGISTER_RETRY_TIMEOUT_SEC = 600
PLAN_TEARDOWN_RESERVE_SEC = 120
STAGED_CENSUS_LANE_TIMEOUT_SEC = 1800
STAGED_CONSOLIDATION_TIMEOUT_SEC = 1200
STAGED_FOLLOWUP_TIMEOUT_SEC = 2400
STAGED_FORMAT_RETRY_TIMEOUT_SEC = 600
STAGED_CENSUS_RESERVE_SEC = 4320
STAGED_FOLLOWUP_RESERVE_SEC = 3120
MAX_PLAN_EVIDENCE_MODEL_CALLS = 22
PLAN_BINDING_MARKER = "=== PLAN EVIDENCE BINDING JSON ==="
MAX_PLAN_BINDING_BATCH_CHARS = 400_000
MAX_PLAN_EXPANDED_PROMPT_CHARS = 685_000
MAX_BINDING_DIAGNOSTIC_CHARS = 2_000
MAX_BINDING_LOCATION_CHARS = 1_000
MAX_BINDING_PASSAGE_CHARS = 8_000
MAX_ATTESTATION_REPLY_CHARS = 500_000
MAX_ATTESTATION_REASON_CHARS = 1_000
MAX_PLAN_CAPTURE_SOURCES = 200
MAX_PLAN_BINDING_BATCHES = 5
MAX_PLAN_ATTESTATION_BATCHES = 5


class _OmittedBinding:
    __slots__ = ()


_OMITTED_BINDING = _OmittedBinding()


@dataclass(frozen=True)
class _ValidationReview(Review):
    """A successful provider response rejected by local claim validation."""

    validation_detail: str = ""


def _attempt(
    role: str, engine: Engine, review: Review, *, sequence: int | None = None,
) -> rc.Attempt:
    response = review.text or ""
    projection = _review_failure_projection(review) if review.error else {}
    return rc.Attempt(
        role, engine.name, review.session_ref,
        "failed" if review.error else "completed",
        review.duration_ms, review.usage,
        hashlib.sha256(response.encode("utf-8", "surrogatepass")).hexdigest()
        if response else None,
        response[:4000] if response else None, sequence,
        **projection,
    )


def _review_failure_projection(review: Review) -> dict[str, Any]:
    def channel(text: str | None) -> tuple[str, str]:
        value = text or ""
        return (
            hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest(),
            value[:4000],
        )

    raw_sha, raw_excerpt = channel(getattr(review, "raw", None))
    detail_sha, detail_excerpt = channel(getattr(review, "failure_detail", None))
    stderr_sha, stderr_excerpt = channel(getattr(review, "stderr", None))
    return {
        "returncode": getattr(review, "returncode", None),
        "raw_sha256": raw_sha, "raw_excerpt": raw_excerpt,
        "failure_detail_sha256": detail_sha,
        "failure_detail_excerpt": detail_excerpt,
        "stderr_sha256": stderr_sha, "stderr_excerpt": stderr_excerpt,
    }


def _engine_failure_error(review: Review, *, role: str) -> rc.CensusError:
    kind = (
        "timeout" if review.returncode == 124
        else "unavailable" if review.returncode == 127
        else "cancellation" if review.returncode in {-15, -2, 130, 143}
        else "provider" if review.returncode == 0
        else "execution"
    )
    detail = rc.bounded_diagnostic(
        review.failure_detail or review.text or review.raw or "engine failure",
        rc.MAX_ENGINE_FAILURE_MESSAGE_CHARS,
    )
    error = rc.CensusError(detail)
    error.stage_role = role  # type: ignore[attr-defined]
    error.failure_kind = kind  # type: ignore[attr-defined]
    error.engine_failure = _review_failure_projection(review)  # type: ignore[attr-defined]
    return error


def _staged_call(
    *, role: str, engine: Engine, prompt: str, cwd: Path, model: str, effort: str,
    timeout: int, parser: Callable[[str], dict[str, Any]],
    on_progress: Callable[[str], None] | None = None,
    next_sequence: Callable[[], int] | None = None,
    web_search: bool = False,
    response_schema: dict[str, Any] | None = None,
) -> tuple[Review, dict[str, Any], list[rc.Attempt], list[dict[str, Any]]]:
    """One schema-constrained staged call plus one same-session correction."""
    sequence = next_sequence() if next_sequence else None
    review = engine.run(
        prompt, cwd, model, effort, web_search, timeout=timeout,
        response_schema=response_schema, **_progress_kwargs(on_progress),
    )
    attempts = [_attempt(role, engine, review, sequence=sequence)]
    if review.error:
        error = _engine_failure_error(review, role=role)
        error.attempts = attempts  # type: ignore[attr-defined]
        raise error
    try:
        return review, parser(review.text), attempts, []
    except rc.CensusError as first:
        first_issue = rc.bounded_diagnostic(str(first), sp.MAX_ISSUE_CHARS)
        rejected = [rc.rejected_payload(
            role, review.text, sequence=attempts[-1].sequence,
            validation_issue=first_issue,
        )]
        attempts[-1] = replace(
            attempts[-1], outcome="validation-invalid", validation_issue=first_issue,
        )
        if not review.session_ref:
            error = rc.CensusError(
                f"{role} validation invalid and has no resumable session: {first_issue}"
            )
            error.stage_role = role  # type: ignore[attr-defined]
            error.failure_kind = "validation"  # type: ignore[attr-defined]
            error.attempts = attempts  # type: ignore[attr-defined]
            error.rejected_payloads = rejected  # type: ignore[attr-defined]
            raise error from first
        retry_sequence = next_sequence() if next_sequence else None
        retry = engine.resume(
            review.session_ref,
            "Your staged JSON was rejected: " + first_issue +
            "\nFix every reported violation in the complete object, not only the first one. "
            "Return the complete schema-conforming JSON object.",
            cwd, model, effort, web_search,
            timeout=min(STAGED_FORMAT_RETRY_TIMEOUT_SEC, timeout),
            response_schema=response_schema,
            **_progress_kwargs(on_progress),
        )
        attempts.append(_attempt(
            f"{role}-validation-retry", engine, retry, sequence=retry_sequence,
        ))
        if retry.error:
            error = _engine_failure_error(
                retry, role=f"{role}-validation-retry",
            )
            error.attempts = attempts  # type: ignore[attr-defined]
            error.rejected_payloads = rejected  # type: ignore[attr-defined]
            raise error from first
        try:
            parsed = parser(retry.text)
        except rc.CensusError as second:
            second_issue = rc.bounded_diagnostic(str(second), sp.MAX_ISSUE_CHARS)
            rejected.append(rc.rejected_payload(
                f"{role}-validation-retry", retry.text,
                sequence=attempts[-1].sequence,
                validation_issue=second_issue,
            ))
            attempts[-1] = replace(
                attempts[-1], outcome="validation-invalid",
                validation_issue=second_issue,
            )
            second.stage_role = f"{role}-validation-retry"  # type: ignore[attr-defined]
            second.failure_kind = "validation"  # type: ignore[attr-defined]
            second.attempts = attempts  # type: ignore[attr-defined]
            second.rejected_payloads = rejected  # type: ignore[attr-defined]
            raise
        return retry, parsed, attempts, rejected


def _staged_class_trailer(closure: "_ClosureRound", status: str) -> str:
    """Render the canonical class surface on every staged result path."""
    if closure.lineage is None:
        return (
            f"CLASS-REGISTER: {status}\n"
            "CLASS-CLOSURE: STATE-UNAVAILABLE — lineage could not be loaded."
        )
    return cc.render_trailer(
        closure.lineage, register_status=status, include_verdict=False,
    )


def _staged_error(message: str, *, role: str, kind: str) -> rc.CensusError:
    error = rc.CensusError(message)
    error.stage_role = role  # type: ignore[attr-defined]
    error.failure_kind = kind  # type: ignore[attr-defined]
    return error


def _staged_class_context(blocks: list[str]) -> str:
    try:
        return rc.class_context(blocks)
    except rc.CensusError as exc:
        raise _staged_error(
            str(exc), role="active-class-preflight", kind="validation",
        ) from exc


def _staged_lane_prompt(
    *, mode: str, lane: str, active_classes: list[dict[str, Any]], body: str,
) -> str:
    instructions = (
        f"{prompts.staged_census_instructions(mode, lane)}\n"
        f"{sp.citation_instructions(mode)}"
    )
    lane_body = (
        f"ROLE: census lane {lane}\nCHECKLIST: {json.dumps(sp.CHECKLIST)}\n"
        "ACTIVE CLASSES: "
        f"{json.dumps(active_classes if lane == 'integrity' else [])}\n\n{body}"
    )
    return prompts.compose(instructions, lane_body)


def _validate_materialized_class_records(
    parsed: dict[str, Any], *, mode: str, lineage: cc.Lineage, round_no: int,
) -> None:
    """Collect independent canonical-engine faults before spending the one retry."""
    issues: list[str] = []
    pointers = parsed.get("_class_record_pointers", [])
    valid_records: list[dict[str, Any]] = []
    for index, record in enumerate(parsed["class_records"]):
        try:
            single = rc.register_from_records(
                [record], mechanized=None if mode == cc.BRANCH_MODE else False,
            )
            cc.apply_register(cc.copy_lineage(lineage), single, round_no=round_no)
            valid_records.append(record)
        except (cc.RegisterError, rc.CensusError) as exc:
            pointer = pointers[index] if index < len(pointers) else f"/class_records/{index}"
            issues.append(f"{pointer}: invalid class operation: {exc}")
    def validate_group(records: list[dict[str, Any]], pointer: str) -> bool:
        try:
            register = rc.register_from_records(
                records,
                mechanized=None if mode == cc.BRANCH_MODE else False,
            )
            cc.apply_register(cc.copy_lineage(lineage), register, round_no=round_no)
        except (cc.RegisterError, rc.CensusError) as exc:
            issues.append(f"{pointer}: {exc}")
            return False
        return True

    new_records = [record for record in valid_records if record.get("op") == "new"]
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in valid_records:
        class_id = record.get("class_id")
        if isinstance(class_id, str):
            groups.setdefault(class_id, []).append(record)
    group_valid = True
    if len(new_records) > 1:
        group_valid = validate_group(
            new_records, "/: invalid combined new-class set",
        ) and group_valid
    for class_id, records in sorted(groups.items()):
        if len(records) > 1:
            group_valid = validate_group(
                records, f"/: invalid combined class actions for {class_id!r}",
            ) and group_valid
    if valid_records and group_valid:
        validate_group(valid_records, "/: invalid combined class operation set")
    if issues:
        raise rc.CensusError(
            "\n".join(sorted(dict.fromkeys(issues)))[:sp.MAX_ISSUE_CHARS]
        )


def _raise_staged_validation_issues(issues: list[str]) -> None:
    """Raise one bounded deterministic diagnostic spanning validation layers."""
    ordered = sorted(dict.fromkeys(issues))
    if not ordered:
        return
    shown = ordered[:sp.MAX_ISSUES]
    if len(ordered) > sp.MAX_ISSUES:
        shown.append(
            f"/: {len(ordered) - sp.MAX_ISSUES} additional validation errors omitted"
        )
    raise rc.CensusError("\n".join(shown)[:sp.MAX_ISSUE_CHARS])


def _census_cache_binding(
    *, mode: str, snapshot: str, stakes: str, body: str,
    active_classes: list[dict[str, Any]], existing_debt: list[dict[str, Any]],
    engine_name: str, model: str, effort: str, web_search: bool,
    plan_lines: int | None, lane_prompts: dict[str, str],
) -> dict[str, Any]:
    canonical_classes = json.dumps(
        sorted(active_classes, key=lambda row: row["class_id"]),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    complete_input = json.dumps({
        "mode":mode, "snapshot_digest":snapshot, "stakes":stakes, "body":body,
        "active_classes":active_classes, "existing_debt":existing_debt,
        "engine":engine_name, "model":model, "effort":effort,
        "web_search":web_search, "plan_lines":plan_lines,
        "lane_prompts":lane_prompts,
        "lane_schemas":{
            lane:sp.canonical_schema(sp.provider_schema(sp.lane_schema(mode, lane)))
            for lane in sp.LANES[mode]
        },
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "version":rc.CENSUS_CACHE_VERSION,
        "mode":mode,
        "snapshot_digest":snapshot,
        "stakes_digest":rc.digest(stakes),
        "input_digest":rc.digest(complete_input),
        "active_classes_digest":rc.digest(canonical_classes),
    }


def _cached_census_manifests(
    state: dict[str, Any], *, binding: dict[str, Any], lanes: tuple[str, ...],
    validate: Callable[[str, str], dict[str, Any]],
) -> list[dict[str, Any]] | None:
    cache = state.get("census_cache")
    if not isinstance(cache, dict) or any(cache.get(key) != value for key, value in binding.items()):
        return None
    raw = cache.get("manifests")
    if not isinstance(raw, list) or len(raw) != len(lanes):
        return None
    by_lane = {
        item.get("lane"): item for item in raw
        if isinstance(item, dict) and isinstance(item.get("lane"), str)
    }
    if set(by_lane) != set(lanes):
        return None
    validated: list[dict[str, Any]] = []
    try:
        for lane in lanes:
            validated.append(validate(json.dumps(by_lane[lane], ensure_ascii=False), lane))
    except rc.CensusError:
        return None
    return validated


def _cacheable_consolidation_error(error: rc.CensusError) -> bool:
    attempts = getattr(error, "attempts", [])
    return (
        getattr(error, "stage_role", None) in {
            "consolidation", "consolidation-validation-retry",
        }
        and getattr(error, "failure_kind", None) == "validation"
        and bool(attempts) and all(
            attempt.outcome == "validation-invalid" for attempt in attempts
        )
    )


def _settle_staged_failure(
    closure: "_ClosureRound", *, stakes: str, snapshot: str, error: rc.CensusError,
    mode: str,
) -> tuple[Review, str, list[dict[str, Any]]]:
    assert closure.lineage is not None
    state = rc.normalize_state(closure.lineage.review_state, stakes=stakes, snapshot=snapshot)
    state.pop("census_cache", None)
    state.pop("validation_debt", None)
    state.pop("staged_failure", None)
    state.pop("format_debt", None)
    cache = getattr(error, "census_cache", None)
    rejected_payloads = getattr(error, "rejected_payloads", [])
    if isinstance(cache, dict):
        state["validation_debt"] = {
            "role":getattr(error, "stage_role", "consolidation-validation-retry"),
            "kind":"validation",
            "message":str(error),
        }
    else:
        state["staged_failure"] = {
            "role":getattr(error, "stage_role", "unknown"),
            "kind":getattr(error, "failure_kind", "unknown"),
            "message":str(error),
        }
        engine_failure = getattr(error, "engine_failure", None)
        if isinstance(engine_failure, dict):
            state["staged_failure"]["engine_failure"] = deepcopy(engine_failure)
    failure_key = "validation_debt" if isinstance(cache, dict) else "staged_failure"
    if rejected_payloads:
        state[failure_key]["rejected_payloads"] = deepcopy(rejected_payloads)
    if isinstance(cache, dict):
        state["census_cache"] = deepcopy(cache)
    closure.lineage.review_state = state
    closure.staged_manifests = getattr(error, "manifests", [])
    closure.rejected_payloads = deepcopy(rejected_payloads)
    try:
        cc.save_lineage(closure.state_root, closure.lineage)
    except cc.StateUnavailable as exc:
        closure.unavailable = str(exc)
        message = f"lineage state unavailable after staged failure: {exc}"
        review = Review(
            text=rc.render_error_review(f"[paranoia-local error] {message}"),
            session_ref=None, raw=message, returncode=2, error=True,
        )
        trailer = (
            "CLASS-REGISTER: staged rejected; failure state persistence unavailable\n"
            f"CLASS-CLOSURE: STATE-UNAVAILABLE — {exc}\n"
            f"{rc.attempt_trailer(getattr(error, 'attempts', []))}\n"
            "CONVERGENCE: BLOCKED — staged failure state may not have persisted."
        )
        if mode == cc.PLAN_MODE and getattr(closure, "claims_enabled", False):
            trailer = f"{pc.render_trailer(closure.lineage.claim_state)}\n{trailer}"
        return review, trailer, [a.json() for a in getattr(error, "attempts", [])]
    closure._settled = True
    closure.register_status = (
        f"staged rejected: {rc.trailer_diagnostic(error)}"
    )
    attempts = [a.json() for a in getattr(error, "attempts", [])]
    review = Review(
        text=rc.render_error_review(
            f"[paranoia-local error] staged review rejected: {error}"
        ),
        session_ref=None, raw=str(error), returncode=2, error=True,
    )
    trailer = "\n".join((
        _staged_class_trailer(closure, closure.register_status),
        rc.trailer(state),
        rc.attempt_trailer(attempts),
    ))
    if mode == cc.PLAN_MODE and getattr(closure, "claims_enabled", False):
        trailer = f"{pc.render_trailer(closure.lineage.claim_state)}\n{trailer}"
    return review, trailer, attempts


def _state_unavailable_review(
    closure: "_ClosureRound", *, mode: str, claim_state: dict[str, Any] | None = None,
) -> tuple[Review, str, list[dict[str, Any]]]:
    """Return the established blocked result without running or mutating staged state."""
    reason = closure.unavailable or "lineage state is unavailable"
    review = Review(
        text=rc.render_error_review(
            f"[paranoia-local error] lineage state unavailable: {reason}"
        ),
        session_ref=None, raw=reason, returncode=2, error=True,
    )
    trailer = (
        "CLASS-REGISTER: staged state unavailable\n"
        f"CLASS-CLOSURE: STATE-UNAVAILABLE — {reason}\n"
        f"{rc.attempt_trailer([])}\n"
        "CONVERGENCE: BLOCKED — lineage state could not be used this round."
    )
    if (
        mode == cc.PLAN_MODE and claim_state is not None
        and getattr(closure, "claims_enabled", False)
    ):
        trailer = f"{pc.render_trailer(claim_state)}\n{trailer}"
    return review, trailer, []


def _structural_pending_review(
    closure: "_ClosureRound", *, mode: str, stakes: str, snapshot: str, reason: str,
) -> tuple[Review, str, list[dict[str, Any]]]:
    """Settle a zero-attempt plan round whose structural reserve no longer fits."""
    error = _staged_error(
        reason, role="structural-reserve-preflight", kind="deadline",
    )
    return _settle_staged_failure(
        closure, stakes=stakes, snapshot=snapshot, error=error, mode=mode,
    )


def _staged_structural_review(
    *, engine: Engine, cwd: Path, model: str, effort: str, mode: str, body: str,
    closure: "_ClosureRound", stakes: str, snapshot: str, round_no: int,
    on_progress: Callable[[str], None] | None, plan_lines: int | None = None,
    web_search: bool = False,
) -> tuple[Review, str, list[dict[str, Any]]]:
    """Run census/correction/final and atomically settle it into the open lineage."""
    assert closure.lineage is not None
    lineage = closure.lineage
    _staged_class_context(closure._blocks())
    state = rc.normalize_state(lineage.review_state, stakes=stakes, snapshot=snapshot)
    if lineage.debt:
        # A pre-staging malformed-register round is not silently normalized into an
        # empty verified register. Its only autonomous recovery is a fresh cold census
        # that sees the exact durable failure it supersedes.
        state = rc.normalize_state(None, stakes=stakes, snapshot=snapshot)
        state["debt"] = [{
            "id":"legacy-register", "finding_id":"legacy-register",
            "status":"open", "severity":cc.BLOCKER,
            "summary":"A pre-staging review left unresolved class-register debt.",
            "reason":str(lineage.debt.get("reason", "unresolved register failure")),
            "remedy":"Use the cold census to explicitly retain or discharge this debt.",
            "evidence":[], "source_ids":[], "class_ids":[],
            "first_round":lineage.debt.get("round", 0),
            "last_round":lineage.debt.get("round", 0),
        }]
        body += "\n\nLEGACY REGISTER DEBT REQUIRING COLD RE-AUDIT:\n" + json.dumps(
            lineage.debt, ensure_ascii=False,
        )
    phase = state["phase"]
    active_classes = [
        {
            "class_id": c.class_id, "invariant": c.invariant,
            "severity": c.severity, "status": c.status, "mechanized": c.mechanized,
            "pattern": c.pattern, "pathspec": c.pathspec, "procedure": c.procedure,
        }
        for c in lineage.active()
    ]
    active_ids = [c["class_id"] for c in active_classes]
    debt_class_ids = {
        cid for debt in state.get("debt", []) if debt.get("status") == "open"
        for cid in debt.get("class_ids", [])
    }
    unbound_blocking = {
        c.class_id for c in lineage.blocking() if c.class_id not in debt_class_ids
    }
    has_blocking_debt = any(
        d.get("status") == "open" and d.get("severity") in rc.BLOCKING
        for d in state.get("debt", [])
    )
    if phase == "census" and (
        state.get("unbound_class_ids") or state.get("unbound_classes")
    ) and has_blocking_debt:
        # State written by the earlier over-broad gate already has actionable debt;
        # resume targeted correction rather than paying for a redundant census.
        state["phase"] = phase = "correction"
    if phase != "census" and unbound_blocking and not has_blocking_debt:
        # A reopened or migrated class without governing staged debt needs the broad
        # integrity lane, not an empty targeted correction that can never settle it.
        state["phase"] = phase = "census"
    attempts: list[rc.Attempt] = []
    rejected_payloads: list[dict[str, Any]] = []
    sequence_lock = Lock()
    sequence_value = 0

    def next_sequence() -> int:
        nonlocal sequence_value
        with sequence_lock:
            sequence_value += 1
            return sequence_value

    def validate_lane(
        text: str, lane: str, *, canonical: bool = False,
    ) -> dict[str, Any]:
        try:
            if canonical:
                parsed = sp.decode_canonical_lane(text, mode=mode, lane=lane)
                issues: list[str] = []
            else:
                parsed, issues = sp.decode_lane_with_issues(
                    text, mode=mode, lane=lane,
                )
        except sp.ProtocolError as exc:
            raise rc.CensusError(str(exc)) from exc
        try:
            sp.validate_lane_value(
                parsed, lane=lane,
                active_classes=active_classes if lane == "integrity" else (),
            )
        except sp.ProtocolError as exc:
            issues.extend(str(exc).splitlines())
        trusted_roots = None
        repository_alias = cwd / "repository"
        if mode == cc.PLAN_MODE and repository_alias.is_symlink():
            trusted_roots = {"repository": repository_alias.resolve(strict=True)}
        elif mode == cc.BRANCH_MODE:
            trusted_roots = {"repository": cwd.resolve(strict=True)}
        try:
            rc.resolve_anchors(
                parsed, root=cwd, plan_lines=plan_lines, trusted_roots=trusted_roots,
            )
        except rc.CensusError as exc:
            issues.extend(str(exc).splitlines())
        _raise_staged_validation_issues(issues)
        return parsed

    def validate_settlement(
        text: str, *, source_ids: list[str], assessment_ids: list[str],
        source_severities: dict[str, str] | None = None,
        assessment_verdicts: dict[str, str] | None = None,
        assessment_findings: dict[str, str | None] | None = None,
        assessment_evidence: dict[str, list[str]] | None = None,
        known_debt: list[str] | None = None, role: str,
    ) -> dict[str, Any]:
        del assessment_ids, known_debt
        try:
            value, issues = sp.decode_decision_with_issues(
                text, mode=mode, role=role, active_classes=active_classes,
                durable_debt=state.get("debt", []),
            )
        except sp.ProtocolError as exc:
            raise rc.CensusError(str(exc)) from exc
        parsed: dict[str, Any] | None = None
        try:
            parsed = sp.materialize_decision_value(
                value, mode=mode, role=role,
                source_ids=source_ids, source_severities=source_severities,
                assessment_verdicts=assessment_verdicts,
                assessment_findings=assessment_findings,
                assessment_evidence=assessment_evidence,
                active_classes=active_classes,
                durable_debt=state.get("debt", []),
            )
        except sp.ProtocolError as exc:
            issues.extend(str(exc).splitlines())
        trusted_roots = None
        repository_alias = cwd / "repository"
        if mode == cc.PLAN_MODE and repository_alias.is_symlink():
            trusted_roots = {"repository": repository_alias.resolve(strict=True)}
        elif mode == cc.BRANCH_MODE:
            trusted_roots = {"repository": cwd.resolve(strict=True)}
        try:
            rc.resolve_anchors(
                value, root=cwd, plan_lines=plan_lines, trusted_roots=trusted_roots,
            )
        except rc.CensusError as exc:
            issues.extend(str(exc).splitlines())
        class_view = parsed
        if class_view is None:
            records, pointers = sp.class_record_candidates(value)
            class_view = {
                "class_records": records,
                "_class_record_pointers": pointers,
            }
        try:
            _validate_materialized_class_records(
                class_view, mode=mode, lineage=lineage, round_no=round_no,
            )
        except rc.CensusError as exc:
            issues.extend(str(exc).splitlines())
        _raise_staged_validation_issues(issues)
        assert parsed is not None
        return parsed

    if phase == "census":
        lanes = sp.LANES[mode]
        lane_prompts = {
            lane:_staged_lane_prompt(
                mode=mode, lane=lane, active_classes=active_classes, body=body,
            )
            for lane in lanes
        }
        existing_debt = [
            d for d in state.get("debt", []) if d.get("status") == "open"
        ]
        consolidation_context = json.dumps({
            "role": "census", "stakes": stakes,
            "active_classes": active_classes, "existing_debt": existing_debt,
        }, ensure_ascii=False, separators=(",", ":"))
        if len(consolidation_context) > sp.MAX_CONSOLIDATION_CONTEXT_CHARS:
            raise _staged_error(
                "consolidation static context is "
                f"{len(consolidation_context)} characters; maximum is "
                f"{sp.MAX_CONSOLIDATION_CONTEXT_CHARS}",
                role="consolidation-input", kind="validation",
            )
        cache_binding = _census_cache_binding(
            mode=mode, snapshot=snapshot, stakes=stakes, body=body,
            active_classes=active_classes, existing_debt=existing_debt,
            engine_name=engine.name, model=model, effort=effort,
            web_search=web_search, plan_lines=plan_lines,
            lane_prompts=lane_prompts,
        )

        def run_lane(
            lane: str,
        ) -> tuple[str, Review, dict[str, Any], list[rc.Attempt], list[dict[str, Any]]]:
            prompt = lane_prompts[lane]
            if len(prompt) > rc.MAX_STAGED_PROMPT_CHARS:
                raise _staged_error(
                    f"staged lane prompt is {len(prompt)} characters",
                    role=f"census-{lane}", kind="validation",
                )
            result, parsed, lane_attempts, lane_rejected = _staged_call(
                role=f"census-{lane}", engine=engine, prompt=prompt, cwd=cwd,
                model=model, effort=effort, timeout=STAGED_CENSUS_LANE_TIMEOUT_SEC,
                on_progress=on_progress,
                web_search=web_search,
                response_schema=sp.provider_schema(sp.lane_schema(mode, lane)),
                parser=lambda text: validate_lane(text, lane), next_sequence=next_sequence,
            )
            renamed = {f["id"]: f"{lane}:{f['id']}" for f in parsed["findings"]}
            for finding in parsed["findings"]:
                finding["id"] = renamed[finding["id"]]
            for coverage in parsed["coverage"]:
                coverage["finding_ids"] = [renamed[fid] for fid in coverage["finding_ids"]]
            for assessment in parsed["class_assessments"]:
                if assessment["finding_id"] is not None:
                    assessment["finding_id"] = renamed[assessment["finding_id"]]
            return lane, result, parsed, lane_attempts, lane_rejected

        manifests = _cached_census_manifests(
            state, binding=cache_binding, lanes=lanes,
            validate=lambda text, lane: validate_lane(
                text, lane, canonical=True,
            ),
        )
        if manifests is None:
            lane_rows = []
            lane_errors: list[tuple[str, rc.CensusError]] = []
            with ThreadPoolExecutor(max_workers=3) as pool:
                pending = {pool.submit(run_lane, lane): lane for lane in lanes}
                for future in as_completed(pending):
                    try:
                        lane_rows.append(future.result())
                    except rc.CensusError as error:
                        lane_errors.append((pending[future], error))
            lane_rows.sort(key=lambda row: lanes.index(row[0]))
            if lane_errors:
                lane_errors.sort(key=lambda row: lanes.index(row[0]))
                all_attempts = [a for row in lane_rows for a in row[3]]
                all_attempts.extend(
                    a for _, error in lane_errors for a in getattr(error, "attempts", [])
                )
                all_attempts.sort(key=lambda item: item.sequence or 0)
                failed_rejected = [
                    (lanes.index(lane_name), position, payload)
                    for lane_name, error in lane_errors
                    for position, payload in enumerate(
                        getattr(error, "rejected_payloads", [])
                    )
                ]
                successful_rejected = [
                    (lanes.index(row[0]), position, payload)
                    for row in lane_rows
                    for position, payload in enumerate(row[4])
                ]
                failed_rejected.extend(successful_rejected)
                failed_rejected.sort(key=lambda row: (
                    row[2].get("sequence") is None,
                    row[2].get("sequence") or 0,
                    row[0], row[1],
                ))
                first_error = lane_errors[0][1]
                first_error.attempts = all_attempts  # type: ignore[attr-defined]
                first_error.rejected_payloads = [  # type: ignore[attr-defined]
                    payload for _, _, payload in failed_rejected
                ]
                first_error.manifests = [  # type: ignore[attr-defined]
                    row[2] for row in lane_rows
                ]
                raise first_error
            for _, _, _, lane_attempts, lane_rejected in lane_rows:
                attempts.extend(lane_attempts)
                rejected_payloads.extend(lane_rejected)
            manifests = [row[2] for row in lane_rows]
        elif on_progress is not None:
            on_progress("reusing validated census lanes after settlement rejection")
        closure.staged_manifests = manifests
        source_ids = [f["id"] for m in manifests for f in m["findings"]]
        source_severities = {f["id"]: f["severity"] for m in manifests for f in m["findings"]}
        assessment_ids = [a["class_id"] for m in manifests for a in m["class_assessments"]]
        assessment_verdicts = {
            a["class_id"]: a["verdict"] for m in manifests for a in m["class_assessments"]
        }
        assessment_findings = {
            a["class_id"]: a["finding_id"] for m in manifests for a in m["class_assessments"]
        }
        assessment_evidence = {
            a["class_id"]: list(a["evidence"])
            for m in manifests for a in m["class_assessments"]
        }
        consolidation_body = json.dumps({
            "role": "census", "stakes": stakes, "manifests": manifests,
            "active_classes": active_classes,
            "existing_debt": existing_debt,
        }, ensure_ascii=False, separators=(",", ":"))
        try:
            prompt = prompts.compose(
                f"{prompts.staged_consolidation_instructions(mode)}\n"
                f"{sp.citation_instructions(mode)}\n"
                f"{sp.class_decision_instructions('census', active_classes=active_classes)}",
                consolidation_body,
            )
            if len(prompt) > rc.MAX_CONSOLIDATION_PROMPT_CHARS:
                raise _staged_error(
                    f"consolidation prompt is {len(prompt)} characters",
                    role="consolidation", kind="validation",
                )
            review, settlement, call_attempts, call_rejected = _staged_call(
                role="consolidation", engine=engine, prompt=prompt, cwd=cwd,
                model=model, effort=effort, timeout=STAGED_CONSOLIDATION_TIMEOUT_SEC,
                on_progress=on_progress,
                web_search=web_search,
                response_schema=sp.provider_schema(sp.decision_schema(
                    mode, "census", active_classes=active_classes,
                )),
                next_sequence=next_sequence,
                parser=lambda text: validate_settlement(
                    text, source_ids=source_ids, source_severities=source_severities,
                    assessment_ids=assessment_ids,
                    assessment_verdicts=assessment_verdicts,
                    assessment_findings=assessment_findings,
                    assessment_evidence=assessment_evidence,
                    known_debt=[
                        d["id"] for d in state.get("debt", []) if d.get("status") == "open"
                    ],
                    role="census",
                ),
            )
        except rc.CensusError as error:
            cacheable = _cacheable_consolidation_error(error)
            error.attempts = [  # type: ignore[attr-defined]
                *attempts, *getattr(error, "attempts", []),
            ]
            combined_rejected = [
                *rejected_payloads, *getattr(error, "rejected_payloads", []),
            ]
            combined_rejected.sort(key=lambda row: (
                row.get("sequence") is None, row.get("sequence") or 0,
            ))
            error.rejected_payloads = combined_rejected  # type: ignore[attr-defined]
            error.manifests = manifests  # type: ignore[attr-defined]
            if cacheable:
                error.census_cache = {  # type: ignore[attr-defined]
                    **cache_binding, "manifests":deepcopy(manifests),
                }
            raise
        attempts.extend(call_attempts)
        rejected_payloads.extend(call_rejected)
    else:
        role = "final" if phase == "final" else "correction"
        open_debt = [d for d in state.get("debt", []) if d.get("status") == "open"]
        existing = [d["id"] for d in open_debt]
        outcome_class_ids = sp.expected_outcome_class_ids(
            role, active_classes=active_classes, durable_debt=open_debt,
        )
        stage_body = json.dumps({
            "role": role, "stakes": stakes, "existing_debt": open_debt,
            "active_classes": active_classes,
            "checklist": list(sp.CHECKLIST) if role == "final" else [],
            "artifact": body,
        }, ensure_ascii=False)
        prompt = prompts.compose(
            f"{prompts.staged_followup_instructions(mode)}\n"
            f"{sp.citation_instructions(mode)}\n"
            f"{sp.class_decision_instructions(role, active_classes=active_classes, outcome_class_ids=outcome_class_ids)}",
            stage_body,
        )
        if len(prompt) > rc.MAX_STAGED_PROMPT_CHARS:
            raise _staged_error(
                f"{role} prompt is {len(prompt)} characters",
                role=role, kind="validation",
            )
        review, settlement, call_attempts, call_rejected = _staged_call(
            role=role, engine=engine, prompt=prompt, cwd=cwd, model=model, effort=effort,
            timeout=STAGED_FOLLOWUP_TIMEOUT_SEC, on_progress=on_progress,
            next_sequence=next_sequence,
            web_search=web_search,
            response_schema=sp.provider_schema(sp.decision_schema(
                mode, role, active_classes=active_classes,
                outcome_class_ids=outcome_class_ids,
            )),
            parser=lambda text: validate_settlement(
                text, source_ids=[],
                assessment_ids=active_ids if role == "final" else [],
                known_debt=existing, role=role,
            ),
        )
        attempts.extend(call_attempts)
        rejected_payloads.extend(call_rejected)

    draft = cc.copy_lineage(lineage)
    register = rc.register_from_records(
        settlement["class_records"], mechanized=None if mode == cc.BRANCH_MODE else False,
    )
    minted = cc.apply_register(draft, register, round_no=round_no)
    minted_by_record = rc.minted_record_ids(settlement["class_records"], minted)
    lineage.classes, lineage.next_seq, lineage.exemptions = (
        draft.classes, draft.next_seq, draft.exemptions
    )
    if mode == cc.BRANCH_MODE:
        closure._sweep(only=minted)
    state = rc.settle_state(state, settlement, phase=phase, snapshot=snapshot, round_no=round_no)
    replacements = {
        cid: cls.superseded_by for cid, cls in lineage.classes.items()
        if cls.status == cc.SUPERSEDED and cls.superseded_by
    }
    for debt in state.get("debt", []):
        debt.setdefault("class_ids", []).extend(
            minted_by_record[index] for index in debt.pop("class_record_indexes", [])
        )
        if debt.get("status") == "open":
            debt["class_ids"] = [
                replacements.get(cid, cid) for cid in debt.get("class_ids", [])
            ]
        debt["class_ids"] = list(dict.fromkeys(debt["class_ids"]))
    claim_blocked = (
        mode == cc.PLAN_MODE and closure.claims_enabled
        and pc.is_blocked(lineage.claim_state)
    )
    mapped_classes = {
        cid for debt in state.get("debt", []) if debt.get("status") == "open"
        for cid in debt.get("class_ids", [])
    }
    unbound = [c for c in lineage.blocking() if c.class_id not in mapped_classes]
    has_blocking_debt = any(
        d.get("status") == "open" and d.get("severity") in rc.BLOCKING
        for d in state.get("debt", [])
    )
    if unbound:
        state["phase"] = "correction" if has_blocking_debt else "census"
        state["unbound_class_ids"] = [c.class_id for c in unbound]
        state.pop("unbound_classes", None)
    elif lineage.blocking() or claim_blocked:
        state["phase"] = "correction"
    lineage.review_state = state
    lineage.debt = None
    lineage.rounds += 1
    register_status = rc.register_status(
        settlement["class_records"], minted_by_record, phase=phase,
    )
    rejected_payloads.sort(key=lambda row: (
        row.get("sequence") is None, row.get("sequence") or 0,
    ))
    closure.rejected_payloads = deepcopy(rejected_payloads)
    try:
        cc.save_lineage(closure.state_root, lineage)
    except cc.StateUnavailable as exc:
        closure.unavailable = str(exc)
        closure.staged_settlement = settlement
        message = f"lineage state unavailable after staged settlement: {exc}"
        failed = Review(
            text=rc.render_error_review(
                f"[paranoia-local error] {message}", settlement_computed=True,
            ),
            session_ref=review.session_ref, raw=message, returncode=2, error=True,
        )
        trailer = (
            f"CLASS-REGISTER: {register_status}; persistence unavailable\n"
            f"CLASS-CLOSURE: STATE-UNAVAILABLE — {exc}\n"
            f"{rc.attempt_trailer(attempts)}\n"
            "CONVERGENCE: BLOCKED — this staged settlement may not have persisted."
        )
        if mode == cc.PLAN_MODE and closure.claims_enabled:
            trailer = f"{pc.render_trailer(lineage.claim_state)}\n{trailer}"
        return failed, trailer, [a.json() for a in attempts]
    closure._settled = True
    closure.register_status = register_status
    closure.staged_settlement = settlement
    review = replace(review, text=rc.render_review(settlement, state))
    trailer = "\n".join((
        cc.render_trailer(
            lineage, register_status=closure.register_status, minted=minted,
            include_verdict=False,
        ),
        rc.trailer(state),
        rc.attempt_trailer(attempts),
    ))
    if mode == cc.PLAN_MODE and closure.claims_enabled:
        trailer = f"{pc.render_trailer(lineage.claim_state)}\n{trailer}"
    attempts.sort(key=lambda item: item.sequence or 0)
    return review, trailer, [a.json() for a in attempts]


def _default_clock() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def _require_repo(arguments: dict[str, Any]) -> Path:
    rp = arguments.get("repo_path")
    if not rp:
        raise ValueError("repo_path is required")
    repo = Path(rp).resolve()
    if not repo.exists():
        raise ValueError(f"repo_path does not exist: {repo}")
    if not (repo / ".git").exists():
        raise ValueError(f"not a git repo (no .git): {repo}")
    return repo


def _no_repo_cwd() -> Path:
    return Path(tempfile.gettempdir())


def _footer(review: Review, engine: Engine) -> str:
    if review.session_ref:
        note = (
            f"\n\n---\n_paranoia-local · engine={engine.name} · "
            f"session_ref=`{review.session_ref}` — to dispute a finding, call `rebut` "
            f"with this session_ref and your counter-evidence._"
        )
    else:
        note = f"\n\n---\n_paranoia-local · engine={engine.name}_"
    # Surface a failed run explicitly — a non-zero exit or an in-band engine error means
    # the text below may be an error message or a truncated/aborted review, not a verdict.
    prefix = ""
    if review.error:
        prefix = (
            f"⚠️ REVIEW FAILED (engine={engine.name}, exit={review.returncode}) — treat the "
            f"output below as an error, not a completed review.\n\n"
        )
    return prefix + (review.text or "[empty review]") + note


def _progress_kwargs(on_progress: Callable[[str], None] | None) -> dict[str, Any]:
    """Pass on_progress only when set — injected engines may predate the kwarg."""
    return {"on_progress": on_progress} if on_progress is not None else {}


ONE_SHOT_HINT = "pass `class_closure: false` for a one-shot review"


def _require_converge(converge: bool, closure_on: bool) -> None:
    """Class closure runs ONLY on the converge path (`class_closure_plan.md` §3), so
    `converge: false` silently disabled it while `round` was still demanded — a call that
    looked gated, emitted no trailer, and let a reviewer's own `CONVERGED` end a loop with
    a blocking class live. There must be exactly ONE escape, and it must be explicit.
    """
    if closure_on and not converge:
        raise ValueError(
            "class closure runs only on the converge path, so `converge: false` would "
            "silently disable it and return no CONVERGENCE trailer. Pass `converge: true` "
            "to keep the gate — note `converge` also resolves from .paranoia.toml, so "
            "removing a call argument may not be enough — or "
            f"{ONE_SHOT_HINT} to review without one."
        )


def _require_round(review_round: Any, closure_on: bool, tool: str) -> None:
    """`round` is what makes a loop terminate: `_CALIBRATION`'s severity floor only exists
    from round 3, so a loop driven without it reports at round-1 severity forever and has
    no mechanical stopping pressure. Required whenever class closure is tracking a loop,
    and deliberately NOT required in the one-shot mode, which has no next round to floor.
    """
    if review_round is None:
        # Omission is the one-shot mode's privilege: there is no next round to floor.
        if not closure_on:
            return
    # A SUPPLIED round is checked in BOTH modes. `_calibration` renders ROUND only for an
    # int >= 1, so 0 and "3" are the same thing to the reviewer as omitting it — no floor —
    # and silently ignoring one the caller took the trouble to pass is how a loop believes
    # it has a floor it never had.
    if not isinstance(review_round, int) or isinstance(review_round, bool) or review_round < 1:
        # Only suggest the escape when it is not already taken — an error whose remedy the
        # caller has already applied reads as a bug in the tool.
        escape = f", or {ONE_SHOT_HINT}" if closure_on else ""
        raise ValueError(
            f"{tool} needs `round` as an integer >= 1 (incremented each cold round), got "
            f"{review_round!r}: any other value produces no ROUND line, so the reviewer "
            "never reaches the round-3 severity floor and the loop has no terminating "
            f"pressure. Pass round: 1 for a first round{escape}."
        )


STAKES_NOTICE = ("STAKES: unstated — the reviewer assumed a modest internal tool. Set "
                 "`stakes` per call, or once for the project in .paranoia.toml; pass "
                 "`stakes: \"unstated\"` to accept that reading deliberately and silence "
                 "this line.")


def _resolve_stakes(stakes: object) -> tuple[str | None, bool]:
    """`arbitrate`'s trick, minus its requirement: the literal `unstated` is an EXPLICIT
    acceptance of one fixed reading (`arbitration.STAKES_DEFAULT`, byte-identical on every
    call) rather than an accidental omission, so it calibrates the reviewer AND silences
    the notice. Returns (stakes_text, notice_needed).

    Stakes stay optional here, unlike `arbitrate` where they gate a decision: the fallback
    is the SAFE reading, so a gate would refuse valid work to prevent a miscalibration the
    caller can simply be shown. Surfacing beats blocking (plan proposal §1.3).
    """
    text = str(stakes).strip() if stakes is not None else ""
    if not text:
        return None, True
    if text.lower() == arbitration.STAKES_UNSTATED:
        return arbitration.STAKES_DEFAULT, False
    return text, False


def _stakes_notice(needed: bool) -> str:
    return f"\n\n{STAKES_NOTICE}" if needed else ""


def _calibration(stakes: str | None, review_round: int | None) -> str | None:
    """Render the reviewer-calibration block. STAKES bounds legitimate concern
    (findings beyond it are out of scope); ROUND sets the severity floor across a
    convergence loop (round >=3 reports MAJOR-or-higher only, withholding MINOR
    and OUT-OF-SCOPE). Both optional; absent → the reviewer assumes a modest
    internal tool and reports everything."""
    lines: list[str] = []
    if stakes:
        lines.append(f"STAKES: {stakes}")
    if isinstance(review_round, int) and not isinstance(review_round, bool) and review_round >= 1:
        lines.append(f"ROUND: {review_round}")
    if not lines:
        return None
    return "=== REVIEW CALIBRATION ===\n" + "\n".join(lines)


def _prepend(block: str | None, body: str) -> str:
    return f"{block}\n\n{body}" if block else body


def _log(
    log_dir: Path,
    tool: str,
    engine: Engine,
    review: Review,
    now: Clock,
    extra: dict[str, Any],
) -> None:
    logs.write_log(
        log_dir,
        tool=tool,
        record={
            "engine": engine.name,
            "session_ref": review.session_ref,
            "returncode": review.returncode,
            "error": review.error,
            "text": review.text,
            **(_review_failure_projection(review) if review.error else {}),
            **extra,
        },
        timestamp=now(),
    )


def critique_branch(
    arguments: dict[str, Any],
    *,
    engine: Engine,
    log_dir: Path = logs.DEFAULT_LOG_DIR,
    now: Clock = _default_clock,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    repo = _require_repo(arguments)
    cfg = load_repo_config(repo)

    base_ref = resolve("base_ref", arguments.get("base_ref"), cfg, "main")
    head_ref = arguments.get("head_ref", "HEAD")
    include_unc = bool(arguments.get("include_uncommitted", False))
    isolate = bool(resolve("isolate", arguments.get("isolate"), cfg, True))
    project_summary = resolve("project_summary", arguments.get("project_summary"), cfg, None)
    diff_intent = arguments.get("diff_intent")
    focus = arguments.get("focus")
    already = list(arguments.get("already_raised", []))
    model = resolve("model", arguments.get("model"), cfg, engine.default_model)
    effort = resolve("effort", arguments.get("effort"), cfg, "high")
    web_search = bool(resolve("web_search", arguments.get("web_search"), cfg, True))
    # Converge (packet) mode is ON by default: pre-gather a deterministic evidence packet
    # and review it against an immutable materialized snapshot. Pass converge=false (call
    # arg or .paranoia.toml) to fall back to the legacy in-place review.
    converge = bool(resolve("converge", arguments.get("converge"), cfg, True))
    max_packet_chars = int(
        resolve("max_packet_chars", arguments.get("max_packet_chars"), cfg, orientation.MAX_PACKET_CHARS)
    )
    # Calibration: STAKES (project-level, so also honoured from .paranoia.toml) bounds
    # scope; ROUND (per-call, raised each convergence round) sets the severity floor.
    closure_on = bool(resolve("class_closure", arguments.get("class_closure"), cfg, True))
    _require_converge(converge, closure_on)
    _require_round(arguments.get("round"), closure_on, "critique_branch")
    stakes, no_stakes = _resolve_stakes(resolve("stakes", arguments.get("stakes"), cfg, None))
    calibration = _calibration(stakes, arguments.get("round"))
    if (converge and closure_on and include_unc
            and arguments.get("head_ref") not in (None, "HEAD")
            and not arguments.get("lineage")):
        # resolve_target discards head_ref for a dirty review and snapshots the checkout, so
        # accepting it would key this round's classes to a branch that was never reviewed.
        # An explicit `lineage` says the caller has chosen the key deliberately, so it is
        # honoured rather than rejected — an error whose remedy it also refuses is no remedy.
        raise ValueError(
            "include_uncommitted reviews the current checkout, so head_ref="
            f"{arguments['head_ref']!r} would not be the reviewed ref. Drop head_ref, or pass "
            "an explicit `lineage` to choose the key yourself, or `class_closure: false`."
        )

    target = orientation.resolve_target(repo, base_ref, head_ref, include_unc)

    if converge:
        return _converge_branch_review(
            repo, engine, target=target, base_ref=base_ref, head_ref=head_ref,
            project_summary=project_summary, diff_intent=diff_intent, focus=focus,
            already=already, model=model, effort=effort, web_search=web_search,
            max_packet_chars=max_packet_chars, calibration=calibration,
            stakes=stakes or "",
            log_dir=log_dir, now=now, on_progress=on_progress,
            closure_on=closure_on, closure_args=arguments,
            review_round=arguments.get("round"), include_unc=include_unc,
        ) + _stakes_notice(no_stakes)

    packet = orientation.build_orientation(
        repo, target, project_summary, diff_intent, focus, already
    )
    prompt = prompts.compose(prompts.CODE_REVIEW_INSTRUCTIONS, _prepend(calibration, packet))

    if target.is_dirty or not isolate:
        review = engine.run(prompt, repo, model, effort, web_search,
                            **_progress_kwargs(on_progress))
    else:
        with worktree_at(repo, head_ref) as wt:
            review = engine.run(prompt, wt, model, effort, web_search,
                                **_progress_kwargs(on_progress))

    _log(log_dir, "critique_branch", engine, review, now,
         {"target": target.description, "model": model,
          "round": arguments.get("round"), "already_raised": already})
    return _footer(review, engine) + _stakes_notice(no_stakes)


def _converge_branch_review(
    repo: Path,
    engine: Engine,
    *,
    target: orientation.Target,
    base_ref: str,
    head_ref: str | None,
    project_summary: str | None,
    diff_intent: str | None,
    focus: str | None,
    already: list[str],
    model: str,
    effort: str,
    web_search: bool,
    max_packet_chars: int,
    calibration: str | None,
    stakes: str,
    log_dir: Path,
    now: Clock,
    on_progress: Callable[[str], None] | None,
    closure_on: bool = False,
    closure_args: dict[str, Any] | None = None,
    review_round: int | None = None,
    include_unc: bool = False,
    state_root: Path | None = None,
) -> str:
    """Opt-in convergence path: pre-gather a deterministic packet so the reviewer skips
    the re-read/re-grep turns, and review it against an IMMUTABLE materialized worktree
    (which always applies here, overriding isolate=false — mixed-revision evidence off a
    live mutable tree is exactly what this prevents)."""
    if target.is_dirty:
        if orientation.has_head(repo):
            base_id = orientation.resolve_head(repo)
            parent: str | None = base_id
        else:
            # Unborn repo (files, no commit yet): base off git's empty tree, parentless wrapper.
            base_id = orientation.empty_tree(repo)
            parent = None
        head_id = orientation.wrap_commit(repo, orientation.snapshot_tree(repo, base_id), parent)
    else:
        base_id = orientation.resolve_ref(repo, base_ref)
        head_id = orientation.resolve_ref(repo, head_ref or "HEAD")

    closure = _ClassClosure(
        repo, head_id, args=closure_args or {}, round_no=review_round or 1,
        is_dirty=target.is_dirty, base_ref=base_ref, head_ref=head_ref,
        state_root=state_root or cc.default_state_root(), stamp=now(),
    ) if closure_on else None
    blocks = closure.prepare() if closure else []

    # EVERYTHING after prepare() is inside the latch's cleanup: packet building, worktree
    # entry and the engine call can all raise, and a latch stranded there would make every
    # later round STATE-UNAVAILABLE over a fault that already surfaced to the caller. A
    # failed *write* is the one case that deliberately keeps the latch (see `release`).
    attempt_ledger: list[dict[str, Any]] = []
    try:
        packet = orientation.build_packet(
            repo, base_id, head_id,
            project_summary=project_summary, diff_intent=diff_intent, focus=focus,
            already_raised=already, class_blocks=blocks, max_chars=max_packet_chars,
        )
        instructions = prompts.CODE_REVIEW_INSTRUCTIONS_PACKET
        if closure:
            instructions += "\n\n" + prompts.CLASS_REGISTER_INSTRUCTIONS
        prompt = prompts.compose(instructions, _prepend(calibration, packet))

        with worktree_at(repo, head_id) as wt:
            if closure and closure.unavailable:
                review, trailer, attempt_ledger = _state_unavailable_review(
                    closure, mode=cc.BRANCH_MODE,
                )
            elif closure and type(engine) in (eng.CodexEngine, eng.ClaudeEngine):
                structural_snapshot = rc.digest(f"{base_id}\0{head_id}\0{packet}")
                try:
                    review, trailer, attempt_ledger = _staged_structural_review(
                        engine=engine, cwd=wt, model=model,
                        effort=effort, mode=cc.BRANCH_MODE,
                        body=f"=== REVIEW STAKES ===\n{stakes}\n\n{packet}",
                        closure=closure, stakes=stakes,
                        snapshot=structural_snapshot,
                        round_no=review_round or 1, on_progress=on_progress,
                        web_search=web_search,
                    )
                except rc.CensusError as error:
                    review, trailer, attempt_ledger = _settle_staged_failure(
                        closure, stakes=stakes, snapshot=structural_snapshot, error=error,
                        mode=cc.BRANCH_MODE,
                    )
            else:
                review = engine.run(prompt, wt, model, effort, web_search,
                                    **_progress_kwargs(on_progress))
                # Settle inside the worktree: a register retry resumes the same session and
                # must see the same materialized snapshot the review did.
                trailer = closure.settle(review, engine, wt, model, effort, web_search,
                                         on_progress) if closure else None
    except BaseException:
        if closure:
            closure.abandon()
        raise
    finally:
        if closure:
            closure.release()

    _log(log_dir, "critique_branch", engine, review, now,
         {"target": target.description, "model": model, "mode": "converge-packet",
          # Which suppression list and which round produced this prompt: without them an
          # incident cannot be replayed even with the snapshot ids below.
          "round": review_round, "already_raised": already,
          "usage": review.usage, "duration_ms": review.duration_ms,
          # Recorded so a future incident IS replayable: the plan's own acceptance
          # replay was impossible because these were never written down.
          "base_id": base_id, "head_id": head_id,
          "lineage": closure.lineage_id if closure else None,
          # The retry's register is what actually changed durable state, so it belongs in
          # the audit record; the original review only carries the malformed attempt.
          "retry_register": closure.retry_register if closure else None,
          "attempt_ledger": attempt_ledger,
          "rejected_payloads": getattr(closure, "rejected_payloads", None) if closure else None,
          "staged_manifests": getattr(closure, "staged_manifests", None) if closure else None,
          "staged_settlement": getattr(closure, "staged_settlement", None) if closure else None})
    body = _footer(review, engine)
    if closure and closure.retry_register:
        # Same reason, for the operator: a CLOSED or a corrected predicate that the retry
        # supplied would otherwise be invisible in everything they can see.
        body += ("\n\n---\n_The register below was supplied on retry and is what this "
                 f"round applied:_\n\n{closure.retry_register.strip()}")
    return f"{body}\n\n{trailer}" if trailer else body


def _plan_body(
    plan: sp.ArtifactView,
    context: str | None,
    focus: str | None,
    already: list[str],
    repo_grounded: bool,
    class_blocks: list[str] | None = None,
) -> str:
    parts: list[str] = []
    if repo_grounded:
        parts.append(
            "=== REPOSITORY IS AVAILABLE ===\n"
            "You are inside the repository this plan concerns. Read the code to test "
            "every premise the plan makes about current behaviour."
        )
    if context:
        parts.append(f"=== CONTEXT ===\n{context}")
    if focus:
        parts.append(f"=== REVIEWER FOCUS ===\n{focus}")
    parts.append(
        "=== PLAN — DISPLAYED PREFIXES ARE CITATION COORDINATES, NOT PLAN TEXT ===\n"
        + plan.rendered
    )
    if already:
        rendered = "\n".join(f"- {c}" for c in already)
        parts.append(
            "=== Already-raised — do NOT restate; hunt for what they missed ===\n" + rendered
        )
    # AFTER already_raised, never before: the class blocks carry explicit precedence over
    # it, and a reviewer reading in order obeys the closer instruction (plan §2.12).
    parts.extend(class_blocks or [])
    return "\n\n".join(parts)


def critique_plan(
    arguments: dict[str, Any],
    *,
    engine: Engine,
    log_dir: Path = logs.DEFAULT_LOG_DIR,
    now: Clock = _default_clock,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    plan_text = arguments.get("plan_text")
    plan_path = arguments.get("plan_path")
    if plan_text and plan_path:
        raise ValueError("critique_plan takes plan_text OR plan_path, not both")
    if not plan_text and not plan_path:
        raise ValueError("critique_plan requires plan_text or plan_path")
    if plan_path:
        try:
            plan_text = Path(plan_path).read_text(encoding="utf-8", errors="replace")
        except (FileNotFoundError, IsADirectoryError, PermissionError, OSError) as exc:
            raise ValueError(f"cannot read plan_path: {exc}") from exc
    plan_view = sp.ArtifactView.from_text(plan_text)

    context = arguments.get("context")
    focus = arguments.get("focus")
    already = list(arguments.get("already_raised", []))
    # Required, not "strongly recommended": PLAN_REVIEW_INSTRUCTIONS calls testing the
    # plan's premises against the code the reviewer's single most valuable job, and an
    # ungrounded plan review cannot do it. Every one of the 225 logged plan reviews
    # passed a repo, so this refuses nothing anyone actually does.
    repo = _require_repo(arguments)
    cwd = repo
    plan_repo_path: str | None = None
    if plan_path:
        try:
            plan_repo_path = Path(plan_path).resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            pass
    cfg = load_repo_config(repo)

    model = resolve("model", arguments.get("model"), cfg, engine.default_model)
    effort = resolve("effort", arguments.get("effort"), cfg, "high")
    web_search = bool(resolve("web_search", arguments.get("web_search"), cfg, True))

    # Verification is ON for the bundled engines.  Capability detection keeps injected
    # test engines and third-party adapters backward-compatible unless a test/caller opts
    # in explicitly.  A web-disabled verification run would defeat the feature's primary
    # purpose, so it is rejected rather than quietly degrading to repository-only checks.
    claim_verification = bool(arguments.get(
        "claim_verification", getattr(engine, "native_web", False)
    ))
    if claim_verification and not web_search:
        raise ValueError(
            "claim verification requires the reviewer's built-in web search; "
            "web_search: false is incompatible with claim_verification: true"
        )
    if claim_verification and type(engine) in (eng.CodexEngine, eng.ClaudeEngine):
        try:
            inert_git.require_supported_version()
            eng.require_evidence_profile(engine)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc

    # Call argument ONLY — `.paranoia.toml` is deliberately not consulted. A per-project
    # setting could never suffice anyway, since the lineage is inherently per-seam, and
    # sharing the branch key would give one name two meanings across two tools.
    closure_on = bool(arguments.get("class_closure", True))
    lineage_id = arguments.get("lineage")
    if closure_on and not lineage_id:
        raise ValueError(
            "class_closure for a plan review needs an explicit `lineage`: a plan has no "
            "branch to key state to, and deriving one from the plan's text or path would "
            "mint a fresh empty lineage whenever either changed — reporting NOT-BLOCKED "
            "with every tracked class silently dropped. Pass a globally unique, "
            f"mode-qualified key (e.g. 'myproject-42-plan'), or {ONE_SHOT_HINT}."
        )
    _require_round(arguments.get("round"), closure_on, "critique_plan")
    stakes, no_stakes = _resolve_stakes(resolve("stakes", arguments.get("stakes"), cfg, None))
    calibration = _calibration(stakes, arguments.get("round"))

    closure = _PlanClassClosure(
        lineage_id, round_no=arguments.get("round") or 1,
        state_root=cc.default_state_root(), stamp=now(),
    ) if closure_on else None
    blocks = closure.prepare() if closure else []

    if closure and closure.lineage is not None:
        prior_review = closure.lineage.review_state
        current_stakes_digest = rc.digest(stakes or "")
        claim_history = pc.normalize_state(closure.lineage.claim_state)
        unknown_calibration = (
            not isinstance(prior_review, dict)
            or prior_review.get("version") != 1
            or prior_review.get("stakes_digest") != current_stakes_digest
        )
        has_prior_state = bool(
            closure.lineage.rounds or closure.lineage.classes
            or claim_history["claims"] or claim_history.get("debt")
            or claim_history.get("plan_snapshot")
        )
        if (
            type(engine) in (eng.CodexEngine, eng.ClaudeEngine)
            and unknown_calibration and has_prior_state
        ):
            # Structural calibration and claim authority share the same stakes. When the
            # claim phase is disabled, retain its packets exactly but remember that no
            # verdict may freeze across this transition. The next enabled call performs
            # a full audit over that preserved inventory.
            closure.lineage.claim_reverify_required = True
            closure.lineage.classes = {
                cid: replace(cls, status=cc.OPEN) if not cls.mechanized else cls
                for cid, cls in closure.lineage.classes.items()
            }
            blocks = closure._blocks()
    claim_state: dict[str, Any] = (
        closure.lineage.claim_state
        if closure and closure.lineage is not None
        else pc.empty_state()
    )

    verified_profile = (
        claim_verification and type(engine) in (eng.CodexEngine, eng.ClaudeEngine)
    )
    plan_deadline = (
        time.monotonic() + PLAN_REVIEW_TOTAL_TIMEOUT_SEC if verified_profile else None
    )
    claim_status = "disabled"
    claim_duration_ms: int | None = None
    attempt_ledger: list[dict[str, Any]] = []
    if claim_verification:
        claim_started = time.monotonic()
        if closure and closure.unavailable:
            claim_state = pc.with_debt(
                claim_state,
                pc.AuditError(f"lineage state unavailable: {closure.unavailable}"),
                round_no=arguments.get("round") or 1,
                plan_text=plan_text,
            )
            claim_status = "state-unavailable"
        else:
            try:
                claim_state, claim_status = _verify_plan_claims(
                    plan_text, claim_state, lineage_id=lineage_id or "one-shot-plan",
                    round_no=arguments.get("round") or 1, stakes=stakes,
                    engine=engine, repo=repo, model=model, effort=effort,
                    plan_repo_path=plan_repo_path,
                    on_progress=on_progress,
                    attempt_ledger=attempt_ledger,
                    force_exhaustive=bool(
                        closure and closure.lineage
                        and closure.lineage.claim_reverify_required
                    ),
                    deadline=(
                        min(
                            plan_deadline - PLAN_TEARDOWN_RESERVE_SEC,
                            claim_started + PLAN_EVIDENCE_TOTAL_TIMEOUT_SEC,
                        )
                        if plan_deadline is not None else None
                    ),
                )
            except BaseException:
                # This is before the structural-review try/finally below, so release the
                # already-open lineage latch here rather than stranding the seam.
                if closure:
                    closure.abandon()
                    closure.release()
                raise
            if closure and closure.lineage is not None:
                closure.lineage.claim_state = claim_state
                if claim_status.startswith("parsed"):
                    closure.lineage.claim_reverify_required = False
                # Persist useful evidence before the structural reviewer runs.  If that
                # later CLI call fails, the next autonomous round reuses the completed
                # research instead of starting over.  The existing pending latch still
                # protects this same atomic lineage file.
                try:
                    cc.save_lineage(closure.state_root, closure.lineage)
                except cc.StateUnavailable as exc:
                    closure.unavailable = str(exc)
        blocks.append(pc.review_context(claim_state))
        claim_duration_ms = int((time.monotonic() - claim_started) * 1000)
    if closure:
        closure.claims_enabled = claim_verification
        closure.claim_state = claim_state

    trailer: str | None = None
    try:
        body = _plan_body(plan_view, context, focus, already, repo_grounded=bool(repo),
                          class_blocks=blocks)
        instructions = (
            prompts.PLAN_REVIEW_CORE_INSTRUCTIONS
            if closure else prompts.PLAN_REVIEW_INSTRUCTIONS
        )
        if closure:
            instructions += "\n\n" + prompts.PLAN_CLASS_REGISTER_INSTRUCTIONS
        prompt = prompts.compose(instructions, _prepend(calibration, body))
        staged_profile = bool(
            closure and type(engine) in (eng.CodexEngine, eng.ClaudeEngine)
        )
        if type(engine) in (eng.CodexEngine, eng.ClaudeEngine) and (claim_verification or closure):
            parent = orientation.resolve_head(repo) if orientation.has_head(repo) else None
            snapshot = orientation.wrap_commit(
                repo,
                orientation.snapshot_tree(
                    repo, parent or orientation.empty_tree(repo),
                ),
                parent,
            )
            structural_snapshot = rc.digest(f"{plan_text}\0{snapshot}")
            with inert_tree.evidence_workspace(repo, snapshot) as workspace:
                reviewer = engine.for_role(eng.ROLE_REPOSITORY)
                review_cwd = workspace.cwd_for(engine.name)
                isolated_prompt = prompt + (
                    "\n\nThe pinned repository evidence root is `repository/`. Treat that "
                    "prefix as the project root; no live Git or web tools are available."
                )
                staged_phase = (
                    rc.normalize_state(
                        closure.lineage.review_state, stakes=stakes or "",
                        snapshot=structural_snapshot,
                    )["phase"]
                    if closure and closure.lineage else "census"
                )
                structural_reserve = (
                    STAGED_CENSUS_RESERVE_SEC
                    if staged_phase == "census" else STAGED_FOLLOWUP_RESERVE_SEC
                )
                if closure and closure.unavailable:
                    review, trailer, structural_attempts = _state_unavailable_review(
                        closure, mode=cc.PLAN_MODE, claim_state=claim_state,
                    )
                    attempt_ledger.extend(structural_attempts)
                elif plan_deadline is not None and (
                    time.monotonic() + structural_reserve > plan_deadline
                ):
                    pending_reason = (
                        "verified evidence work completed and was persisted, but the "
                        "whole-plan deadline leaves insufficient time for the bounded "
                        "structural review; rerun to reuse frozen claims"
                    )
                    if closure:
                        review, trailer, structural_attempts = _structural_pending_review(
                            closure, mode=cc.PLAN_MODE, stakes=stakes or "",
                            snapshot=structural_snapshot, reason=pending_reason,
                        )
                        attempt_ledger.extend(structural_attempts)
                    else:
                        review = Review(
                            text=f"[paranoia-local error] {pending_reason}",
                            session_ref=None, raw=pending_reason, returncode=124, error=True,
                        )
                elif closure:
                    staged_body = body + (
                        "\n\nThe pinned repository evidence root is `repository/`. Treat that "
                        "prefix as the project root; no live Git or web tools are available."
                    )
                    try:
                        review, trailer, structural_attempts = _staged_structural_review(
                            engine=reviewer, cwd=review_cwd, model=model, effort=effort,
                            mode=cc.PLAN_MODE,
                            body=f"=== REVIEW STAKES ===\n{stakes or ''}\n\n{staged_body}",
                            closure=closure, stakes=stakes or "", snapshot=structural_snapshot,
                            round_no=arguments.get("round") or 1, on_progress=on_progress,
                            plan_lines=plan_view.line_count,
                        )
                    except rc.CensusError as error:
                        review, trailer, structural_attempts = _settle_staged_failure(
                            closure, stakes=stakes or "", snapshot=structural_snapshot,
                            error=error, mode=cc.PLAN_MODE,
                        )
                    attempt_ledger.extend(structural_attempts)
                else:
                    review = reviewer.run(
                        isolated_prompt, review_cwd, model, effort, False,
                        timeout=PLAN_STRUCTURAL_PHASE_TIMEOUT_SEC,
                        **_progress_kwargs(on_progress),
                    )
                if closure:
                    closure.deadline = plan_deadline
                if closure and not staged_profile:
                    trailer = closure.settle(
                        review, reviewer, review_cwd, model, effort, False, on_progress,
                    )
        else:
            review = engine.run(prompt, cwd, model, effort, web_search,
                                **_progress_kwargs(on_progress))
            trailer = closure.settle(review, engine, cwd, model, effort, web_search,
                                     on_progress) if closure else None
    except BaseException:
        if closure:
            closure.abandon()
        raise
    finally:
        if closure:
            closure.release()

    _log(log_dir, "critique_plan", engine, review, now, {
        "grounded": bool(repo), "model": model,
        # None of this was recorded before, so a plan seam was not reconstructible at
        # all — neither what was suppressed nor which plan was reviewed.
        "round": arguments.get("round"),
        "already_raised": already,
        "plan_digest": hashlib.sha256(plan_text.encode("utf-8", "surrogateescape")).hexdigest()[:16],
        "plan_path": plan_path,
        "class_closure": closure_on,
        "lineage": lineage_id if closure else None,
        "register_status": closure.register_status if closure else None,
        "claim_verification": claim_verification,
        "claim_status": claim_status,
        "claim_duration_ms": claim_duration_ms,
        "claim_model_calls": sum(
            1 for item in attempt_ledger if str(item.get("role", "")).startswith("claim-")
        ),
        "claim_counts": {
            verdict: sum(
                1 for claim in pc.normalize_state(claim_state)["claims"].values()
                if claim.get("verdict") == verdict
            ) for verdict in sorted(pc.VERDICTS)
        } if claim_verification else None,
        # The retry's register is what actually changed durable state, so the original
        # (rejected) block alone would misreport the round.
        "retry_register": closure.retry_register if closure else None,
        "attempt_ledger": attempt_ledger,
        "rejected_payloads": getattr(closure, "rejected_payloads", None) if closure else None,
        "staged_manifests": getattr(closure, "staged_manifests", None) if closure else None,
        "staged_settlement": getattr(closure, "staged_settlement", None) if closure else None,
    })
    body_text = _footer(review, engine) + _stakes_notice(no_stakes)
    if closure and closure.retry_register:
        body_text += ("\n\n---\n_The register below was supplied on retry and is what this "
                      f"round applied:_\n\n{closure.retry_register.strip()}")
    if trailer:
        return f"{body_text}\n\n{trailer}"
    if claim_verification:
        # One-shot mode deliberately has no computed convergence contract: without a
        # parsed class register the server cannot mechanically incorporate a successful
        # structural review's FATAL/MAJOR findings.  Evidence and prose remain useful,
        # but only the tracked two-role path may issue governing combined clearance.
        return f"{body_text}\n\n{pc.render_trailer(claim_state)}"
    return body_text


def _verify_plan_claims(
    plan_text: str,
    prior_state: dict[str, Any],
    *,
    lineage_id: str,
    round_no: int,
    stakes: str | None,
    engine: Engine,
    repo: Path,
    model: str,
    effort: str,
    plan_repo_path: str | None,
    on_progress: Callable[[str], None] | None,
    attempt_ledger: list[dict[str, Any]] | None = None,
    deadline: float | None = None,
    force_exhaustive: bool = False,
) -> tuple[dict[str, Any], str]:
    """Run exhaustive round 1, then verify only the external-claim edit cone."""
    targeted = pc.has_prior_snapshot(prior_state) and not force_exhaustive
    server_capture_required = type(engine) in (eng.CodexEngine, eng.ClaudeEngine)
    frozen = (
        pc.frozen_supported_ids(
            prior_state, plan_text, repo=repo, plan_repo_path=plan_repo_path,
            require_capture_attestation=server_capture_required,
        )
        if targeted else frozenset()
    )
    prior = pc.normalize_state(prior_state)
    if (
        targeted
        and prior.get("plan_snapshot") == plan_text
        and len(frozen) == len(prior["claims"])
        and not prior.get("debt")
    ):
        state = pc.reconcile(
            prior_state, pc.Audit((), {"notes": "unchanged frozen claim inventory"}, (), ()),
            lineage_id=lineage_id, round_no=round_no, plan_text=plan_text,
            frozen_ids=frozen, repo=repo, plan_repo_path=plan_repo_path,
        )
        return state, f"reused {len(frozen)} unchanged supported packets; no claim model call"
    if on_progress:
        if targeted:
            on_progress(
                f"verifying the external-claim edit cone; {len(frozen)} unchanged supported "
                "claims reuse frozen authoritative packets"
            )
        else:
            on_progress(
                "verifying external facts, design principles, and behaviors against "
                "authoritative web evidence"
            )
    prompt = (
        pc.targeted_audit_instructions(plan_text, prior_state, stakes, frozen)
        if targeted else pc.audit_instructions(plan_text, prior_state, stakes)
    )
    claim_engine: Any = engine
    captured_engine: _CapturedClaimEngine | None = None
    if server_capture_required:
        captured_engine = _CapturedClaimEngine(
            engine, plan_text=plan_text, repo=repo, plan_repo_path=plan_repo_path,
            prior_state=prior_state, frozen_ids=frozen, deadline=deadline,
            attempt_ledger=attempt_ledger,
        )
        claim_engine = captured_engine
    review = claim_engine.run(
        prompt, repo, model, effort, True, timeout=3600,
        **_progress_kwargs(on_progress),
    )
    if captured_engine is None and attempt_ledger is not None:
        attempt_ledger.append(_attempt("claim-audit", engine, review).json())
    if review.error:
        validation_invalid = isinstance(review, _ValidationReview)
        error = pc.AuditError(
            review.validation_detail if validation_invalid else (
                f"claim-audit reviewer failed (exit {review.returncode})"
            ),
            review.raw,
            failure_detail=review.failure_detail or "", stderr=review.stderr or "",
            returncode=review.returncode,
        )
        return pc.with_debt(
            prior_state, error, round_no=round_no, plan_text=plan_text, frozen_ids=frozen,
        ), "validation-invalid" if validation_invalid else "failed"
    allow_missing = bool(captured_engine and captured_engine.allow_missing)
    try:
        audit = pc.parse_audit(
            review.text, plan_text, repo=repo, plan_repo_path=plan_repo_path,
        )
        pc.validate_prior_coverage(
            prior_state, audit, plan_text=plan_text, raw=review.text, frozen_ids=frozen,
            repo=repo, plan_repo_path=plan_repo_path, allow_missing=allow_missing,
        )
        status = (
            f"parsed {len(audit.claims)} new + {len(audit.assessments)} targeted retained"
            f" + {len(frozen)} frozen"
        )
        if allow_missing:
            status += "; localized retained omission after discovery correction"
    except pc.AuditError as first:
        if not review.session_ref or not hasattr(engine, "resume"):
            return (
                pc.with_debt(
                    prior_state, first, round_no=round_no, plan_text=plan_text,
                    frozen_ids=frozen,
                ),
                f"malformed: {first.reason}",
            )
        retry = claim_engine.resume(
            review.session_ref, pc.retry_instructions(
                first, plan_text, prior_state, frozen_ids=frozen,
            ), repo,
            model, effort, True, timeout=3600, **_progress_kwargs(on_progress),
        )
        if captured_engine is None and attempt_ledger is not None:
            attempt_ledger.append(_attempt("claim-audit-retry", engine, retry).json())
        if retry.error:
            second = pc.AuditError(
                f"initial audit invalid ({first.reason}); correction call failed "
                f"(exit {retry.returncode})",
                retry.raw,
                failure_detail=retry.failure_detail or "", stderr=retry.stderr or "",
                returncode=retry.returncode,
            )
            return pc.with_debt(
                prior_state, second, round_no=round_no, plan_text=plan_text,
                frozen_ids=frozen,
            ), "retry-failed"
        try:
            # The retry is the final model call. Localize any remaining invalid claim
            # so valid packets and dispositions survive with explicit blocking debt.
            audit = pc.parse_audit(
                retry.text, plan_text, allow_partial=True, repo=repo,
                plan_repo_path=plan_repo_path,
            )
            pc.validate_prior_coverage(
                prior_state, audit, plan_text=plan_text, raw=retry.text,
                frozen_ids=frozen, repo=repo, plan_repo_path=plan_repo_path,
                allow_missing=True,
            )
            allow_missing = True
            status = (
                f"parsed after retry: {len(audit.claims)} new + "
                f"{len(audit.assessments)} targeted retained + {len(frozen)} frozen"
            )
            if audit.issues:
                status += f"; {len(audit.issues)} localized invalid"
        except pc.AuditError as second_error:
            combined = pc.AuditError(
                f"initial audit invalid ({first.reason}); correction invalid "
                f"({second_error.reason})",
                (review.text or "") + "\n--- CORRECTION ---\n" + (retry.text or ""),
            )
            return pc.with_debt(
                prior_state, combined, round_no=round_no, plan_text=plan_text,
                frozen_ids=frozen,
            ), "retry-malformed"
    state = pc.reconcile(
        prior_state, audit, lineage_id=lineage_id, round_no=round_no,
        plan_text=plan_text, frozen_ids=frozen, repo=repo,
        plan_repo_path=plan_repo_path,
        allow_missing=allow_missing,
    )
    if captured_engine is not None:
        captured_engine.close()
    return state, status


class _CapturedClaimEngine:
    """Adapt the existing claim lifecycle to discovery -> capture -> binding.

    The outer lifecycle still owns retained packets, retry debt, and reconciliation.
    This adapter only ensures the audit it receives cannot cite provider-reported text.
    """

    def __init__(
        self, engine: Engine, *, plan_text: str, repo: Path,
        plan_repo_path: str | None, prior_state: dict[str, Any] | None = None,
        frozen_ids: frozenset[str] = frozenset(),
        deadline: float | None = None,
        attempt_ledger: list[dict[str, Any]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.engine = engine
        self.plan_text = plan_text
        self.repo = repo
        self.plan_repo_path = plan_repo_path
        self.prior_state = prior_state or {}
        self.frozen_ids = frozen_ids
        self.deadline = deadline
        self.attempt_ledger = attempt_ledger
        self.clock = clock
        self.model_calls = 0
        self.launch = Path(tempfile.mkdtemp(prefix="paranoia-plan-evidence-"))
        self.binding_engine: Engine | None = None
        self.expanded_captures: set[tuple[int, int]] = set()
        self.last_session: str | None = None
        self.discovery: pc.Audit | None = None
        self.allow_missing = False
        self.captures: dict[tuple[int, int], external_sources.Capture] = {}
        self.attestation_raw = ""
        self.non_model_deadline: float | None = None

    def close(self) -> None:
        shutil.rmtree(self.launch, ignore_errors=True)

    def __del__(self) -> None:
        self.close()

    def run(
        self, prompt: str, cwd: Path, model: str, effort: str, web_search: bool,
        **kwargs: Any,
    ) -> Review:
        discovery_kwargs = dict(kwargs)
        try:
            self._admit_complete_graph()
            discovery_kwargs["timeout"] = self._next_model_timeout(reserve_calls=2)
        except pc.AuditError as error:
            return self._deadline_failure(error)
        discoverer = self.engine.for_role(eng.ROLE_DISCOVERY)
        first = discoverer.run(
            prompt, self.launch, model, effort, True, **discovery_kwargs,
        )
        self._record("claim-discovery", discoverer, first)
        if first.error or not first.session_ref:
            return first
        raw_parts = [first.raw]
        try:
            discovery = self._parse_discovery(first.text)
        except pc.AuditError as error:
            self._mark_last_validation_invalid(str(error), first, "/claims")
            try:
                discovery_kwargs["timeout"] = self._next_model_timeout()
            except pc.AuditError as deadline_error:
                return self._deadline_failure(deadline_error, first.session_ref, raw_parts)
            corrected = discoverer.resume(
                first.session_ref,
                pc.retry_instructions(
                    error, self.plan_text, self.prior_state,
                    frozen_ids=self.frozen_ids,
                ),
                self.launch, model, effort, True, **discovery_kwargs,
            )
            self._record(
                "claim-discovery-validation-retry", discoverer, corrected,
            )
            raw_parts.append(corrected.raw)
            if corrected.error or not corrected.session_ref:
                return corrected
            try:
                discovery = self._parse_discovery(corrected.text)
            except pc.AuditError as second:
                self._mark_last_validation_invalid(
                    str(second), corrected, "/claims",
                )
                # The discovery role has spent its one correction. If the corrected
                # document is otherwise valid and only retained coverage is incomplete,
                # preserve its useful packets and let reconciliation carry each omission
                # forward as unverified. Other schema/transition errors remain wholesale.
                try:
                    discovery = pc.parse_audit(
                        corrected.text, self.plan_text, repo=self.repo,
                        plan_repo_path=self.plan_repo_path,
                    )
                    pc.validate_prior_coverage(
                        self.prior_state, discovery, plan_text=self.plan_text,
                        raw=corrected.text, frozen_ids=self.frozen_ids, repo=self.repo,
                        plan_repo_path=self.plan_repo_path, allow_missing=True,
                    )
                except pc.AuditError:
                    detail = pc.bounded_diagnostic(
                        f"initial: {error.reason}\ncorrection: {second.reason}"
                    )
                    return _ValidationReview(
                        text=f"[paranoia-local error] discovery audit invalid: {second}",
                        session_ref=corrected.session_ref,
                        raw="\n--- discovery correction ---\n".join(raw_parts),
                        returncode=corrected.returncode, error=True,
                        failure_detail=corrected.failure_detail,
                        stderr=corrected.stderr, validation_detail=detail,
                    )
                self.allow_missing = True
            session_ref = corrected.session_ref
        else:
            session_ref = first.session_ref

        try:
            self.non_model_deadline = self.clock() + PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC
            if self.deadline is not None:
                self.non_model_deadline = min(self.non_model_deadline, self.deadline)
            captures = self._capture(discovery)
            self.discovery = discovery
            self.captures = captures
            self.binding_engine = self.engine.for_role(eng.ROLE_BINDING)
            binding_kwargs = dict(kwargs)
            binding_kwargs["timeout"] = PLAN_EVIDENCE_PHASE_TIMEOUT_SEC
            audit, binding_reviews = self._bind_indexed(
                session_ref, discovery, captures, model, effort, binding_kwargs,
            )
        except pc.AuditError as error:
            return Review(
                text=f"[paranoia-local error] binding audit invalid: {error}",
                session_ref=session_ref, raw=error.raw, error=True,
                failure_detail=error.failure_detail_raw, stderr=error.stderr_raw,
                returncode=error.returncode if error.returncode is not None else 1,
            )
        raw_parts.extend(item.raw for item in binding_reviews)

        attested = self._attest(audit, model, effort)
        if isinstance(attested, Review):
            return attested
        raw_parts.append(self.attestation_raw)
        last_binding = binding_reviews[-1] if binding_reviews else first
        self.last_session = last_binding.session_ref
        return Review(
            text=_render_audit(attested),
            session_ref=last_binding.session_ref,
            raw="\n--- phase ---\n".join(raw_parts),
            usage=last_binding.usage,
            duration_ms=last_binding.duration_ms,
        )

    def _next_model_timeout(self, *, reserve_calls: int = 1) -> int:
        if self.model_calls + reserve_calls > MAX_PLAN_EVIDENCE_MODEL_CALLS:
            raise pc.AuditError(
                "plan evidence model-call ceiling cannot admit the initial call and its "
                f"reserved correction ({self.model_calls}+{reserve_calls} > "
                f"{MAX_PLAN_EVIDENCE_MODEL_CALLS})"
            )
        if self.deadline is not None and (
            self.clock() + PLAN_EVIDENCE_PHASE_TIMEOUT_SEC * reserve_calls
            > self.deadline
        ):
            raise pc.AuditError(
                "plan evidence deadline leaves insufficient time for the initial call and "
                f"its {reserve_calls - 1} reserved correction call(s)"
            )
        self.model_calls += 1
        return PLAN_EVIDENCE_PHASE_TIMEOUT_SEC

    def _admit_complete_graph(self) -> None:
        required = (
            MAX_PLAN_EVIDENCE_MODEL_CALLS * PLAN_EVIDENCE_PHASE_TIMEOUT_SEC
            + PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC
        )
        if self.deadline is not None and self.clock() + required > self.deadline:
            raise pc.AuditError(
                "plan evidence deadline cannot admit the complete maximum model-call "
                f"graph plus {PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC} seconds of capture "
                "and bounded local processing"
            )

    def _record(self, role: str, engine: Engine, review: Review) -> None:
        if self.attempt_ledger is not None:
            self.attempt_ledger.append(_attempt(role, engine, review).json())

    def _mark_last_validation_invalid(
        self, issue: str, review: Review, pointer: str,
    ) -> None:
        if self.attempt_ledger:
            row = self.attempt_ledger[-1]
            row["outcome"] = "validation-invalid"
            row["validation_issue"] = rc.bounded_diagnostic(
                issue, sp.MAX_ISSUE_CHARS,
            )
            row["validation_pointer"] = pointer
            row.update(_review_failure_projection(review))
            row["rejected_reply_sha256"] = hashlib.sha256(
                review.text.encode("utf-8", "surrogatepass")
            ).hexdigest()
            row["rejected_reply_excerpt"] = rc.bounded_diagnostic(
                review.text, rc.MAX_REJECTED_PAYLOAD_CHARS,
            )

    @staticmethod
    def _deadline_failure(
        error: pc.AuditError, session_ref: str | None = None,
        raw_parts: list[str] | None = None,
    ) -> Review:
        return Review(
            text=f"[paranoia-local error] evidence budget exhausted: {error}",
            session_ref=session_ref, raw="\n--- phase ---\n".join(raw_parts or []),
            returncode=124, error=True,
        )

    def _parse_discovery(self, text: str) -> pc.Audit:
        """Validate governing inventory before any URL is captured."""
        audit = pc.parse_audit(
            text, self.plan_text, repo=self.repo,
            plan_repo_path=self.plan_repo_path,
        )
        pc.validate_prior_coverage(
            self.prior_state, audit, plan_text=self.plan_text, raw=text,
            frozen_ids=self.frozen_ids, repo=self.repo,
            plan_repo_path=self.plan_repo_path,
        )
        return audit

    def resume(
        self, session_ref: str, prompt: str, cwd: Path, model: str, effort: str,
        web_search: bool, **kwargs: Any,
    ) -> Review:
        role = self.binding_engine or self.engine.for_role(eng.ROLE_BINDING)
        binding_kwargs = dict(kwargs)
        try:
            binding_kwargs["timeout"] = self._next_model_timeout()
        except pc.AuditError as error:
            return self._deadline_failure(error, session_ref)
        corrected = role.resume(
            session_ref, prompt, self.launch, model, effort, False, **binding_kwargs,
        )
        self._record("claim-binding-outer-retry", role, corrected)
        if corrected.error or self.discovery is None:
            return corrected
        try:
            audit = self._parse_bound(corrected.text, self.discovery, self.captures)
        except pc.AuditError as error:
            return Review(
                text=f"[paranoia-local error] corrected binding audit invalid: {error}",
                session_ref=corrected.session_ref, raw=corrected.raw, error=True,
            )
        attested = self._attest(audit, model, effort)
        if isinstance(attested, Review):
            return attested
        return Review(
            text=_render_audit(attested), session_ref=corrected.session_ref,
            raw=corrected.raw + "\n--- cold attestation ---\n" + self.attestation_raw,
            usage=corrected.usage,
            duration_ms=corrected.duration_ms,
        )

    def _capture(
        self, audit: pc.Audit,
    ) -> dict[tuple[int, int], external_sources.Capture]:
        candidates: list[external_sources.CandidateSource] = []
        keys: list[tuple[int, int]] = []
        for claim_index, claim in enumerate(audit.claims):
            for evidence_index, item in enumerate(claim["evidence"]):
                candidate = external_sources.CandidateSource(
                    item["url"], item["title"], item["publisher"],
                    item["source_kind"], item["authority_basis"], item["relation"],
                )
                candidates.append(candidate)
                keys.append((claim_index, evidence_index))
        if len(candidates) > MAX_PLAN_CAPTURE_SOURCES:
            raise pc.AuditError(
                f"plan audit proposed {len(candidates)} sources; aggregate capture ceiling is "
                f"{MAX_PLAN_CAPTURE_SOURCES}"
            )
        captured = external_sources.capture_all(
            candidates, workers=16, deadline=self.non_model_deadline,
            clock=self.clock,
        )
        self._check_non_model_deadline()
        return dict(zip(keys, captured, strict=True))

    def _check_non_model_deadline(self) -> None:
        if self.non_model_deadline is not None and self.clock() > self.non_model_deadline:
            raise pc.AuditError(
                "plan evidence capture and pre-binding processing exceeded its aggregate "
                f"{PLAN_EVIDENCE_NON_MODEL_RESERVE_SEC}-second reserve"
            )

    @staticmethod
    def _binding_prompt(rendered: str, issue: str | None = None) -> str:
        if issue is None:
            lead = (
                "Bind every indexed candidate below using only its server capture. Return "
                "exactly one row per (claim_index,evidence_index); preserve both indices. "
                "A capture_ref points to an earlier row in this batch with identical final "
                "URL and content/text digests; use that earlier row's line-numbered text. "
                "Use binding_target as the exact proposition to bind. Copy a precise "
                "location and exact passage only when usable, otherwise use nulls. Do not "
                "return claims or source metadata.\n\n"
                f"{PLAN_BINDING_MARKER}\n"
                '{"bindings":[{"claim_index":0,"evidence_index":0,"usable":true,'
                '"location":"section/table/page","passage":"exact captured passage"}]}\n\n'
            )
        else:
            lead = (
                f"Your indexed binding was rejected: {issue}. Return one corrected "
                f"{PLAN_BINDING_MARKER} object for exactly this batch. If a passage did "
                "not match, copy it character-for-character from line_numbered_text "
                "without line numbers, ellipses, normalization, or paraphrase.\n\n"
            )
        return lead + rendered

    @classmethod
    def _binding_prompts_fit(cls, rows: list[dict[str, Any]], limit: int) -> bool:
        rendered = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        issue = "x" * MAX_BINDING_DIAGNOSTIC_CHARS
        return max(
            len(cls._binding_prompt(rendered)),
            len(cls._binding_prompt(rendered, issue)),
        ) <= limit

    @staticmethod
    def _binding_target(claim: dict[str, Any], item: dict[str, Any]) -> str:
        if item["relation"] == "supports_replacement":
            return str(claim.get("replacement") or "")
        return str(claim["proposition"])

    @staticmethod
    def _attestation_prompt(items: list[dict[str, Any]]) -> str:
        return (
            "You are a cold evidence attester with no web or repository tools. Independently "
            "judge only whether each named publisher governs the exact proposition and whether "
            "the exact passage entails the declared relation in the supplied captured context. "
            "Return only:\n=== EVIDENCE ATTESTATION JSON ===\n"
            '{"attestations":[{"claim_index":0,"evidence_index":0,'
            '"publisher_authority":true,"authority_reason":"specific reason",'
            '"passage_entailment":true,"entailment_reason":"specific reason"}]}\n\n'
            + json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        )

    @staticmethod
    def _attestation_correction_prompt(rendered: str, issue: str) -> str:
        return (
            f"Your cold evidence attestation was rejected: {issue}. Return one corrected "
            "=== EVIDENCE ATTESTATION JSON === object for exactly this packet.\n\n"
            + rendered
        )

    @classmethod
    def _attestation_prompts_fit(
        cls, items: list[dict[str, Any]], limit: int,
    ) -> bool:
        rendered = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        return max(
            len(cls._attestation_prompt(items)),
            len(cls._attestation_correction_prompt(
                rendered, "x" * MAX_BINDING_DIAGNOSTIC_CHARS,
            )),
        ) <= limit

    def _expanded_source_fits(
        self, row: dict[str, Any], claim: dict[str, Any], item: dict[str, Any],
        capture: external_sources.Capture,
    ) -> bool:
        if not self._binding_prompts_fit([row], MAX_PLAN_EXPANDED_PROMPT_CHARS):
            return False
        worst = "\x01"
        attestation = {
            "claim_index": row["claim_index"],
            "evidence_index": row["evidence_index"],
            "proposition": self._binding_target(claim, item),
            "publisher": item["publisher"],
            "authority_basis": item["authority_basis"],
            "relation": item["relation"],
            "location": worst * MAX_BINDING_LOCATION_CHARS,
            "passage": worst * MAX_BINDING_PASSAGE_CHARS,
            "capture": {
                "final_url": capture.final_url,
                "status": capture.status,
                "content_type": capture.content_type,
                "content_sha256": capture.content_sha256,
                "text_sha256": capture.text_sha256,
                "complete_line_numbered_text": external_sources.numbered_text(
                    capture.text or ""
                ),
            },
        }
        return self._attestation_prompts_fit(
            [attestation], MAX_PLAN_EXPANDED_PROMPT_CHARS,
        )

    def _expanded_source_allowed(
        self, row: dict[str, Any], claim: dict[str, Any], item: dict[str, Any],
        capture: external_sources.Capture,
    ) -> bool:
        effective = replace(
            capture.candidate,
            url=capture.final_url or capture.candidate.url,
        )
        plan_self = bool(
            self.plan_repo_path
            and pc._is_plan_self_url(
                effective.url, self.repo, self.plan_repo_path,
            )
        )
        return (
            external_sources.structurally_governing(effective)
            and not plan_self
            and self._expanded_source_fits(row, claim, item, capture)
        )

    def _binding_batches(
        self, discovery: pc.Audit,
        captures: dict[tuple[int, int], external_sources.Capture],
    ) -> list[list[dict[str, Any]]]:
        batches: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        seen_captures: dict[
            tuple[str | None, str | None, str | None], tuple[int, int]
        ] = {}
        for (claim_index, evidence_index), capture in captures.items():
            if not capture.usable:
                continue
            claim = discovery.claims[claim_index]
            item = claim["evidence"][evidence_index]
            identity = (capture.final_url, capture.content_sha256, capture.text_sha256)
            referenceable = all(identity)

            def make_row(capture_ref: tuple[int, int] | None) -> dict[str, Any]:
                return {
                    "claim_index": claim_index,
                    "evidence_index": evidence_index,
                    "proposition": claim["proposition"],
                    "binding_target": self._binding_target(claim, item),
                    "candidate": {
                        key: item[key] for key in (
                            "url", "title", "publisher", "source_kind",
                            "authority_basis", "relation",
                        )
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
                        "capture_ref": (
                            None if capture_ref is None else {
                                "claim_index": capture_ref[0],
                                "evidence_index": capture_ref[1],
                            }
                        ),
                        "line_numbered_text": (
                            "" if capture_ref is not None else
                            external_sources.numbered_text(capture.text or "")
                        ),
                    },
                }

            capture_ref = seen_captures.get(identity) if referenceable else None
            row = make_row(capture_ref)
            if current and not self._binding_prompts_fit(
                current + [row], MAX_PLAN_BINDING_BATCH_CHARS,
            ):
                standalone = make_row(None)
                if (
                    not self._binding_prompts_fit(
                        [standalone], MAX_PLAN_BINDING_BATCH_CHARS,
                    )
                    and not self._expanded_source_allowed(
                        standalone, claim, item, capture,
                    )
                ):
                    captures[(claim_index, evidence_index)] = replace(
                        capture, text=None,
                        error=external_sources.BINDING_BUDGET_ERROR,
                    )
                    continue
                batches.append(current)
                current = []
                seen_captures = {}
                capture_ref = None
                row = standalone
            if not self._binding_prompts_fit([row], MAX_PLAN_BINDING_BATCH_CHARS):
                if self._expanded_source_allowed(row, claim, item, capture):
                    batches.append([row])
                    self.expanded_captures.add((claim_index, evidence_index))
                    current = []
                    seen_captures = {}
                    continue
                capture = replace(
                    capture, text=None,
                    error=external_sources.BINDING_BUDGET_ERROR,
                )
                captures[(claim_index, evidence_index)] = capture
                continue
            current.append(row)
            if referenceable and capture_ref is None:
                seen_captures[identity] = (claim_index, evidence_index)
        if current:
            batches.append(current)
        if len(batches) > MAX_PLAN_BINDING_BATCHES:
            raise pc.AuditError(
                f"captured evidence requires {len(batches)} binding batches; aggregate ceiling "
                f"is {MAX_PLAN_BINDING_BATCHES} batches of "
                f"{MAX_PLAN_BINDING_BATCH_CHARS} characters"
            )
        return batches

    def _bind_indexed(
        self, session_ref: str, discovery: pc.Audit,
        captures: dict[tuple[int, int], external_sources.Capture],
        model: str, effort: str, binding_kwargs: dict[str, Any],
    ) -> tuple[pc.Audit, list[Review]]:
        assert self.binding_engine is not None
        decisions: dict[
            tuple[int, int], tuple[str, str] | None | _OmittedBinding
        ] = {}
        reviews: list[Review] = []
        current_session = session_ref
        batches = self._binding_batches(discovery, captures)
        self._check_non_model_deadline()
        self.non_model_deadline = None
        decisions.update({key: None for key, capture in captures.items() if not capture.usable})
        for batch in batches:
            rendered = json.dumps(batch, ensure_ascii=False, separators=(",", ":"))
            instruction = self._binding_prompt(rendered)
            only_key = (batch[0]["claim_index"], batch[0]["evidence_index"])
            expanded = len(batch) == 1 and only_key in self.expanded_captures

            def source_local_failure(detail: str) -> None:
                capture = captures[only_key]
                captures[only_key] = replace(
                    capture, text=None,
                    error=pc.bounded_diagnostic(detail),
                )
                decisions[only_key] = None

            call_kwargs = dict(binding_kwargs)
            call_kwargs["timeout"] = self._next_model_timeout(reserve_calls=2)
            review = self.binding_engine.resume(
                current_session, instruction, self.launch, model, effort, False,
                **call_kwargs,
            )
            self._record("claim-binding", self.binding_engine, review)
            reviews.append(review)
            if review.error or not review.session_ref:
                if expanded:
                    source_local_failure(
                        review.failure_detail or review.stderr or
                        "dedicated expanded binding call failed"
                    )
                    continue
                raise pc.AuditError(
                    "captured-text binding call failed", review.raw,
                    failure_detail=review.failure_detail or "", stderr=review.stderr or "",
                    returncode=review.returncode,
                )
            try:
                parsed = self._parse_indexed_binding(review.text, batch, captures)
            except pc.AuditError as first:
                self._mark_last_validation_invalid(str(first), review, "/bindings")
                call_kwargs["timeout"] = self._next_model_timeout()
                issue = pc.bounded_diagnostic(str(first))[:MAX_BINDING_DIAGNOSTIC_CHARS]
                correction = self.binding_engine.resume(
                    review.session_ref,
                    self._binding_prompt(rendered, issue),
                    self.launch, model, effort, False, **call_kwargs,
                )
                self._record(
                    "claim-binding-validation-retry", self.binding_engine, correction,
                )
                reviews.append(correction)
                if correction.error or not correction.session_ref:
                    if expanded:
                        source_local_failure(
                            correction.failure_detail or correction.stderr or
                            "dedicated expanded binding correction failed"
                        )
                        continue
                    raise pc.AuditError(
                        "captured-text binding correction failed", correction.raw,
                        failure_detail=correction.failure_detail or "",
                        stderr=correction.stderr or "",
                        returncode=correction.returncode,
                    )
                try:
                    parsed = self._parse_indexed_binding(
                        correction.text, batch, captures,
                    )
                except pc.AuditError as second:
                    self._mark_last_validation_invalid(
                        str(second), correction, "/bindings",
                    )
                    if expanded:
                        source_local_failure(str(second))
                        continue
                    raise
                review = correction
            decisions.update(parsed)
            current_session = review.session_ref

        claims = [deepcopy(claim) for claim in discovery.claims]
        for claim_index, claim in enumerate(claims):
            claim["capture_attestations"] = []
            claim["capture_provenance"] = []
            for evidence_index, item in enumerate(claim["evidence"]):
                capture = captures[(claim_index, evidence_index)]
                requested_url = item["url"]
                item["url"] = capture.final_url or item["url"]
                claim["capture_provenance"].append({
                    "evidence_index": evidence_index,
                    "requested_url": requested_url,
                    "final_url": capture.final_url,
                    "status": capture.status,
                    "content_type": capture.content_type,
                    "fallback_attempted": capture.fallback_attempted,
                    "content_sha256": capture.content_sha256,
                    "text_sha256": capture.text_sha256,
                    "error": (
                        external_sources._bounded_error(capture.error)
                        if capture.error else None
                    ),
                })
                binding = decisions[(claim_index, evidence_index)]
                if binding is _OMITTED_BINDING:
                    item["relation"] = "context"
                    item["location"] = "No binding row returned for captured source"
                    item["quote"] = "The model omitted this captured-source binding."
                elif binding is None:
                    item["relation"] = "context"
                    if not capture.usable:
                        detail = " ".join(
                            (capture.error or "capture contained no extracted text").split()
                        )
                        item["location"] = "Server capture unavailable"
                        item["quote"] = f"Server capture unavailable: {detail}"
                    else:
                        item["location"] = "Captured source explicitly marked unusable"
                        item["quote"] = "No usable captured-text passage was returned."
                else:
                    item["location"], item["quote"] = binding
        combined = pc.Audit(
            tuple(claims), discovery.coverage, discovery.dispositions,
            discovery.assessments,
        )
        audit = pc.parse_audit(
            _render_audit(combined), self.plan_text, repo=self.repo,
            plan_repo_path=self.plan_repo_path, require_capture_provenance=True,
        )
        return audit, reviews

    def _parse_indexed_binding(
        self, text: str, batch: list[dict[str, Any]],
        captures: dict[tuple[int, int], external_sources.Capture],
    ) -> dict[tuple[int, int], tuple[str, str] | None | _OmittedBinding]:
        if text.count(PLAN_BINDING_MARKER) != 1:
            raise pc.AuditError(f"expected exactly one {PLAN_BINDING_MARKER} marker", text)
        tail = text.split(PLAN_BINDING_MARKER, 1)[1].strip()
        try:
            value, end = json.JSONDecoder().raw_decode(tail)
        except json.JSONDecodeError as exc:
            raise pc.AuditError(f"invalid indexed binding JSON: {exc}", text) from exc
        if tail[end:].strip() or not isinstance(value, dict) or set(value) != {"bindings"}:
            raise pc.AuditError("invalid indexed binding envelope", text)
        raw = value["bindings"]
        expected = {(row["claim_index"], row["evidence_index"]) for row in batch}
        if not isinstance(raw, list):
            raise pc.AuditError("indexed binding rows must be an array", text)
        result: dict[
            tuple[int, int], tuple[str, str] | None | _OmittedBinding
        ] = {}
        for row in raw:
            if not isinstance(row, dict) or set(row) != {
                "claim_index", "evidence_index", "usable", "location", "passage",
            }:
                raise pc.AuditError("indexed binding row fields are invalid", text)
            if type(row["claim_index"]) is not int or type(row["evidence_index"]) is not int:
                raise pc.AuditError("indexed binding row indices must be integers", text)
            key = (row["claim_index"], row["evidence_index"])
            if key not in expected or key in result or type(row["usable"]) is not bool:
                raise pc.AuditError("indexed binding row identity is invalid or duplicated", text)
            if not row["usable"]:
                if row["location"] is not None or row["passage"] is not None:
                    raise pc.AuditError("unusable indexed binding must contain nulls", text)
                result[key] = None
                continue
            capture = captures[key]
            if not capture.usable or not capture.text:
                raise pc.AuditError("indexed binding used an unavailable capture", text)
            try:
                location = pc._one_line(row["location"], "binding.location")
                passage = pc._one_line(row["passage"], "binding.passage")
            except ValueError as exc:
                raise pc.AuditError(str(exc), text) from exc
            if len(location) > MAX_BINDING_LOCATION_CHARS:
                raise pc.AuditError(
                    f"binding.location exceeds {MAX_BINDING_LOCATION_CHARS} characters", text,
                )
            if len(passage) > MAX_BINDING_PASSAGE_CHARS:
                raise pc.AuditError(
                    f"binding.passage exceeds {MAX_BINDING_PASSAGE_CHARS} characters", text,
                )
            if not external_sources.passage_matches(passage, capture.text):
                raise pc.AuditError("indexed binding passage is not in captured text", text)
            result[key] = (location, passage)
        # Exhaustive identity remains server-owned. A model omission cannot support a
        # claim, but it also need not discard independently valid rows from this batch.
        # Materialize each missing expected key as a distinct conservative outcome;
        # unknown and duplicate keys have already failed above. Keeping omission
        # separate from an explicit unusable judgement preserves truthful provenance.
        for key in sorted(expected - result.keys()):
            result[key] = _OMITTED_BINDING
        return result

    def _parse_bound(
        self, text: str, discovery: pc.Audit,
        captures: dict[tuple[int, int], external_sources.Capture],
    ) -> pc.Audit:
        audit = pc.parse_audit(
            text, self.plan_text, repo=self.repo, plan_repo_path=self.plan_repo_path,
        )
        if len(audit.claims) != len(discovery.claims) or audit.assessments:
            raise pc.AuditError("binding changed or omitted the discovered claim inventory", text)
        immutable_claim = ("kind", "scope", "anchor", "proposition", "prior_claim_id")
        immutable_source = (
            "title", "publisher", "source_kind", "authority_basis", "relation",
        )
        for claim_index, (claim, original) in enumerate(
            zip(audit.claims, discovery.claims, strict=True)
        ):
            if any(claim.get(key) != original.get(key) for key in immutable_claim):
                raise pc.AuditError("binding changed claim identity or metadata", text)
            if len(claim["evidence"]) != len(original["evidence"]):
                raise pc.AuditError("binding omitted a discovered source", text)
            for evidence_index, (item, discovered) in enumerate(
                zip(claim["evidence"], original["evidence"], strict=True)
            ):
                capture = captures.get((claim_index, evidence_index))
                allowed_url = capture.final_url if capture and capture.final_url else discovered["url"]
                if item["url"] != allowed_url or any(
                    item[key] != discovered[key] for key in immutable_source
                ):
                    raise pc.AuditError("binding changed immutable source metadata", text)
                if not capture or not capture.usable or not capture.text:
                    raise pc.AuditError("binding cited an unavailable capture", text)
                if not external_sources.passage_matches(item["quote"], capture.text):
                    raise pc.AuditError("binding quote does not occur in captured text", text)
        return audit

    def _attest(self, audit: pc.Audit, model: str, effort: str) -> pc.Audit | Review:
        items: list[dict[str, Any]] = []
        local_failures: dict[tuple[int, int], str] = {}
        for claim_index, claim in enumerate(audit.claims):
            for evidence_index, item in enumerate(claim["evidence"]):
                if item["source_kind"] not in pc.AUTHORITATIVE_KINDS:
                    continue
                if item["relation"] not in {"supports_claim", "refutes_claim", "supports_replacement"}:
                    continue
                if item["relation"] == "supports_replacement" and not claim.get("replacement"):
                    continue
                capture = self.captures.get((claim_index, evidence_index))
                attested_proposition = (
                    claim["replacement"]
                    if item["relation"] == "supports_replacement"
                    else claim["proposition"]
                )
                capture_data: dict[str, Any] = {
                    "final_url": capture.final_url if capture else None,
                    "status": capture.status if capture else None,
                    "content_type": capture.content_type if capture else None,
                    "content_sha256": capture.content_sha256 if capture else None,
                    "text_sha256": capture.text_sha256 if capture else None,
                }
                if (claim_index, evidence_index) in self.expanded_captures and capture:
                    capture_data["complete_line_numbered_text"] = (
                        external_sources.numbered_text(capture.text or "")
                    )
                items.append({
                    "claim_index": claim_index,
                    "evidence_index": evidence_index,
                    "proposition": attested_proposition,
                    "publisher": item["publisher"],
                    "authority_basis": item["authority_basis"],
                    "relation": item["relation"],
                    "location": item["location"],
                    "passage": item["quote"],
                    "capture": capture_data,
                })
        attester = self.engine.for_role(eng.ROLE_TEXT)
        ordinary_items = [
            row for row in items
            if (row["claim_index"], row["evidence_index"]) not in self.expanded_captures
        ]
        ordinary: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for row in ordinary_items:
            if current and not self._attestation_prompts_fit(
                current + [row], MAX_PLAN_BINDING_BATCH_CHARS,
            ):
                ordinary.append(current)
                current = []
            if not self._attestation_prompts_fit(
                [row], MAX_PLAN_BINDING_BATCH_CHARS,
            ):
                local_failures[(row["claim_index"], row["evidence_index"])] = (
                    "one ordinary attestation item exceeds the exact prompt bound"
                )
                continue
            current.append(row)
        if current:
            ordinary.append(current)
        expanded = [
            [row] for row in items
            if (row["claim_index"], row["evidence_index"]) in self.expanded_captures
        ]
        attestation_batches = ordinary + expanded
        if len(attestation_batches) > MAX_PLAN_ATTESTATION_BATCHES:
            return Review(
                text=(
                    "[paranoia-local error] evidence attestation requires "
                    f"{len(attestation_batches)} batches; aggregate ceiling is "
                    f"{MAX_PLAN_ATTESTATION_BATCHES}"
                ),
                session_ref=None,
                raw="",
                returncode=1,
                error=True,
            )
        decisions: dict[tuple[int, int], dict[str, Any]] = {}
        attestation_raw: list[str] = []

        def parse_attestation(
            review: Review, attestation_batch: list[dict[str, Any]],
        ) -> dict[tuple[int, int], dict[str, Any]]:
            if len(review.text) > MAX_ATTESTATION_REPLY_CHARS:
                raise ValueError(
                    "attestation reply exceeds "
                    f"{MAX_ATTESTATION_REPLY_CHARS} characters"
                )
            tail = review.text.split("=== EVIDENCE ATTESTATION JSON ===", 1)[1].strip()
            value, end = json.JSONDecoder().raw_decode(tail)
            if tail[end:].strip() or set(value) != {"attestations"}:
                raise ValueError("invalid attestation envelope")
            rows = value["attestations"]
            if not isinstance(rows, list) or len(rows) != len(attestation_batch):
                raise ValueError("attestation inventory differs from the requested inventory")
            expected = {
                (row["claim_index"], row["evidence_index"])
                for row in attestation_batch
            }
            parsed: dict[tuple[int, int], dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict) or set(row) != {
                    "claim_index", "evidence_index", "publisher_authority",
                    "authority_reason", "passage_entailment", "entailment_reason",
                }:
                    raise ValueError("invalid attestation row")
                if type(row["claim_index"]) is not int or type(
                    row["evidence_index"]
                ) is not int:
                    raise ValueError("attestation row indices must be integers")
                key = (row["claim_index"], row["evidence_index"])
                if key not in expected or key in parsed or key in decisions:
                    raise ValueError("unknown or duplicate attestation row")
                if type(row["publisher_authority"]) is not bool or type(
                    row["passage_entailment"]
                ) is not bool:
                    raise ValueError("attestation verdicts must be booleans")
                if not isinstance(row["authority_reason"], str) or not row[
                    "authority_reason"
                ].strip() or not isinstance(row["entailment_reason"], str) or not row[
                    "entailment_reason"
                ].strip():
                    raise ValueError("attestation reasons must be non-empty strings")
                if len(row["authority_reason"]) > MAX_ATTESTATION_REASON_CHARS or len(
                    row["entailment_reason"]
                ) > MAX_ATTESTATION_REASON_CHARS:
                    raise ValueError(
                        "attestation reason exceeds "
                        f"{MAX_ATTESTATION_REASON_CHARS} characters"
                    )
                parsed[key] = row
            return parsed

        for attestation_batch in attestation_batches:
            prompt = self._attestation_prompt(attestation_batch)
            limit = (
                MAX_PLAN_EXPANDED_PROMPT_CHARS
                if len(attestation_batch) == 1 and (
                    attestation_batch[0]["claim_index"],
                    attestation_batch[0]["evidence_index"],
                ) in self.expanded_captures
                else MAX_PLAN_BINDING_BATCH_CHARS
            )
            if not self._attestation_prompts_fit(attestation_batch, limit):
                for row in attestation_batch:
                    local_failures[(row["claim_index"], row["evidence_index"])] = (
                        "evidence attestation prompt or correction exceeds its "
                        f"{limit}-character bound"
                    )
                continue
            try:
                timeout = self._next_model_timeout(reserve_calls=2)
            except pc.AuditError as error:
                return self._deadline_failure(error, raw_parts=attestation_raw)
            review = attester.run(
                prompt, self.launch, model, effort, False, timeout=timeout,
            )
            self._record("claim-attestation", attester, review)
            attestation_raw.append(review.raw)
            if review.error:
                if len(attestation_batch) == 1 and (
                    attestation_batch[0]["claim_index"],
                    attestation_batch[0]["evidence_index"],
                ) in self.expanded_captures:
                    key = (
                        attestation_batch[0]["claim_index"],
                        attestation_batch[0]["evidence_index"],
                    )
                    local_failures[key] = pc.bounded_diagnostic(
                        review.failure_detail or review.stderr or review.text
                        or "dedicated expanded attestation call failed"
                    )
                    continue
                return review
            try:
                parsed = parse_attestation(review, attestation_batch)
            except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                self._mark_last_validation_invalid(
                    str(exc), review, "/attestations",
                )
                issue = pc.bounded_diagnostic(str(exc))[:MAX_BINDING_DIAGNOSTIC_CHARS]
                if not review.session_ref:
                    if len(attestation_batch) == 1 and (
                        attestation_batch[0]["claim_index"],
                        attestation_batch[0]["evidence_index"],
                    ) in self.expanded_captures:
                        key = (
                            attestation_batch[0]["claim_index"],
                            attestation_batch[0]["evidence_index"],
                        )
                        local_failures[key] = pc.bounded_diagnostic(str(exc))
                        continue
                    return Review(
                        text="[paranoia-local error] evidence attestation invalid and "
                        f"cannot be corrected without a provider session: {exc}",
                        raw=review.raw, error=True,
                    )
                rendered = json.dumps(
                    attestation_batch, ensure_ascii=False, separators=(",", ":"),
                )
                try:
                    timeout = self._next_model_timeout()
                except pc.AuditError as error:
                    return self._deadline_failure(error, raw_parts=attestation_raw)
                correction = attester.resume(
                    review.session_ref,
                    self._attestation_correction_prompt(rendered, issue),
                    self.launch, model, effort, False, timeout=timeout,
                )
                self._record("claim-attestation-validation-retry", attester, correction)
                attestation_raw.append(correction.raw)
                if correction.error:
                    if len(attestation_batch) == 1 and (
                        attestation_batch[0]["claim_index"],
                        attestation_batch[0]["evidence_index"],
                    ) in self.expanded_captures:
                        key = (
                            attestation_batch[0]["claim_index"],
                            attestation_batch[0]["evidence_index"],
                        )
                        local_failures[key] = pc.bounded_diagnostic(
                            correction.failure_detail or correction.stderr
                            or correction.text
                            or "dedicated expanded attestation correction failed"
                        )
                        continue
                    return correction
                try:
                    parsed = parse_attestation(correction, attestation_batch)
                except (
                    ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError,
                ) as second:
                    self._mark_last_validation_invalid(
                        str(second), correction, "/attestations",
                    )
                    if len(attestation_batch) == 1 and (
                        attestation_batch[0]["claim_index"],
                        attestation_batch[0]["evidence_index"],
                    ) in self.expanded_captures:
                        key = (
                            attestation_batch[0]["claim_index"],
                            attestation_batch[0]["evidence_index"],
                        )
                        local_failures[key] = pc.bounded_diagnostic(str(second))
                        continue
                    return Review(
                        text=f"[paranoia-local error] evidence attestation invalid: {second}",
                        session_ref=correction.session_ref, raw=correction.raw, error=True,
                    )
            decisions.update(parsed)
        self.attestation_raw = "\n--- attestation ---\n".join(attestation_raw)
        try:
            if len(decisions) + len(local_failures) != len(items):
                raise ValueError("attestation inventory differs from the requested inventory")
        except ValueError as exc:
            return Review(text=f"[paranoia-local error] {exc}", error=True)
        claims = [dict(claim) for claim in audit.claims]
        for index, claim in enumerate(claims):
            claim["capture_attestations"] = []
            for evidence_index, item in enumerate(claim["evidence"]):
                row = decisions.get((index, evidence_index))
                local_failure = local_failures.get((index, evidence_index))
                bounded_local_failure = (
                    rc.bounded_diagnostic(
                        local_failure, MAX_ATTESTATION_REASON_CHARS,
                    )
                    if local_failure else None
                )
                capture = self.captures.get((index, evidence_index))
                if capture is None or not capture.text_sha256:
                    continue
                provenance: dict[str, Any] = {
                    "evidence_index": evidence_index,
                    "final_url": capture.final_url or item["url"],
                    "text_sha256": capture.text_sha256,
                    "relation": item["relation"],
                    "publisher_authority": row["publisher_authority"] if row else False,
                    "authority_reason": row["authority_reason"] if row else (
                        bounded_local_failure
                        or "Server-owned source processing failure prevented attestation."
                    ),
                    "passage_entailment": row["passage_entailment"] if row else False,
                    "entailment_reason": row["entailment_reason"] if row else (
                        bounded_local_failure
                        or "No provider passage was accepted from the retained capture."
                    ),
                    "fallback_attempted": capture.fallback_attempted,
                }
                if capture.content_sha256:
                    provenance["content_sha256"] = capture.content_sha256
                if capture.status is not None:
                    provenance["status"] = capture.status
                if capture.content_type:
                    provenance["content_type"] = capture.content_type
                if capture.error or local_failure:
                    provenance["capture_error"] = external_sources._bounded_error(
                        local_failure or capture.error
                    )
                claim["capture_attestations"].append(provenance)
                if local_failure:
                    for capture_row in claim.get("capture_provenance", []):
                        if capture_row.get("evidence_index") == evidence_index:
                            capture_row["error"] = external_sources._bounded_error(
                                local_failure
                            )
                            break
            relation = "supports_claim" if claim["verdict"] == "supported" else "refutes_claim"
            qualifying = any(
                item["relation"] == relation
                and (decision := decisions.get((index, evidence_index))) is not None
                and decision["publisher_authority"] is True
                and decision["passage_entailment"] is True
                for evidence_index, item in enumerate(claim["evidence"])
            )
            if claim["verdict"] in {"supported", "refuted"} and not qualifying:
                claim["verdict"] = "unverified"
                claim["replacement"] = None
                claim["rationale"] = (
                    str(claim.get("rationale", ""))
                    + " Cold evidence attestation did not accept both publisher authority and passage entailment."
                ).strip()
            if claim.get("replacement") and not any(
                item["relation"] == "supports_replacement"
                and (decision := decisions.get((index, evidence_index))) is not None
                and decision["publisher_authority"] is True
                and decision["passage_entailment"] is True
                for evidence_index, item in enumerate(claim["evidence"])
            ):
                claim["replacement"] = None
                claim["rationale"] = (
                    str(claim.get("rationale", ""))
                    + " Cold evidence attestation did not accept the exact replacement."
                ).strip()
        return pc.Audit(
            tuple(claims), audit.coverage, audit.dispositions, audit.assessments,
            audit.issues, audit.raw_sha256, audit.rejected_excerpt,
        )


def _render_audit(audit: pc.Audit) -> str:
    return pc.AUDIT_MARKER + "\n" + json.dumps(
        {"claims": list(audit.claims), "coverage": audit.coverage},
        ensure_ascii=False, separators=(",", ":"),
    )


def _query_body(
    question: str, files: list[dict], focus: str | None, repo_grounded: bool
) -> str:
    parts: list[str] = []
    if repo_grounded:
        parts.append(
            "=== REPOSITORY IS AVAILABLE ===\n"
            "Answer by reading the actual code, data, and git history in your working "
            "directory — not from assumption."
        )
    if files:
        hints = "\n".join(
            f"- {f.get('path', '?')}" + (f" ({f['reason']})" if f.get("reason") else "")
            for f in files
        )
        parts.append(f"=== FILES THE CALLER SUGGESTS LOOKING AT ===\n{hints}")
    if focus:
        parts.append(f"=== FOCUS ===\n{focus}")
    parts.append(f"=== QUESTION ===\n{question}")
    return "\n\n".join(parts)


def query(
    arguments: dict[str, Any],
    *,
    engine: Engine,
    log_dir: Path = logs.DEFAULT_LOG_DIR,
    now: Clock = _default_clock,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    question = arguments.get("question")
    if not question:
        raise ValueError("query requires a question")

    repo_path = arguments.get("repo_path")
    repo = _require_repo(arguments) if repo_path else None
    cwd = repo if repo else _no_repo_cwd()
    cfg = load_repo_config(repo) if repo else {}
    files = list(arguments.get("files", []))
    focus = arguments.get("focus")

    model = resolve("model", arguments.get("model"), cfg, engine.default_model)
    # query is a quick double-check, not a full review — lower reasoning effort.
    effort = resolve("effort", arguments.get("effort"), cfg, "medium")
    web_search = bool(resolve("web_search", arguments.get("web_search"), cfg, True))

    body = _query_body(question, files, focus, repo_grounded=bool(repo))
    prompt = prompts.compose(prompts.QUERY_INSTRUCTIONS, body)
    review = engine.run(prompt, cwd, model, effort, web_search,
                        **_progress_kwargs(on_progress))

    _log(log_dir, "query", engine, review, now, {"model": model})
    return _footer(review, engine)


def rebut(
    arguments: dict[str, Any],
    *,
    engine: Engine,
    log_dir: Path = logs.DEFAULT_LOG_DIR,
    now: Clock = _default_clock,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    session_ref = arguments.get("session_ref")
    rebuttal = arguments.get("rebuttal")
    if not session_ref:
        raise ValueError("rebut requires session_ref (from a prior review's footer)")
    if not rebuttal:
        raise ValueError("rebut requires rebuttal (your counter-evidence)")
    repo = _require_repo(arguments)
    cfg = load_repo_config(repo)

    model = resolve("model", arguments.get("model"), cfg, engine.default_model)
    effort = resolve("effort", arguments.get("effort"), cfg, "high")
    web_search = bool(resolve("web_search", arguments.get("web_search"), cfg, True))

    body = f"=== AUTHOR'S COUNTER-EVIDENCE ===\n{rebuttal}"
    prompt = prompts.compose(prompts.REBUT_INSTRUCTIONS, body)
    review = engine.resume(session_ref, prompt, repo, model, effort, web_search,
                           **_progress_kwargs(on_progress))

    _log(log_dir, "rebut", engine, review, now, {"session_ref": session_ref, "model": model})
    return _footer(review, engine)


class _ClosureRound:
    """Orchestration for one round of class closure: the impure half of `class_closure`.

    Split from the pure core so the protocol stays testable without a repository, and
    kept in one object so the round's two halves — the blocks handed to the reviewer,
    and the verdict computed from its register — cannot drift apart.

    Every failure path here BLOCKS and returns the review text. A paid review is never
    discarded over a formatting miss, and a storage fault is never allowed to read as
    an all-clear.

    Two subclasses: `_ClassClosure` (branch — mechanized predicates swept against a git
    snapshot) and `_PlanClassClosure` (plan — unmechanized only, no repository). The
    settle/latch/retry half is identical for both and lives here; everything that
    touches git is a hook the plan subclass turns off.
    """

    #: Which lineage mode this round may open. A plan round loading branch state would
    #: have to sweep predicates it has no snapshot for, or carry a stale `closed`.
    mode = cc.BRANCH_MODE
    #: Plan registers may not carry PATTERN/PATHSPEC — a regex over prose closes on a
    #: rewording (see `cc.parse_register`).
    allow_mechanized = True

    def __init__(self, lineage_id: str, *, round_no: int, state_root: Path,
                 stamp: str) -> None:
        self.lineage_id, self.round_no = lineage_id, round_no
        self.state_root, self.stamp = Path(state_root), stamp
        self.lineage: cc.Lineage | None = None
        self.unavailable: str | None = None
        #: The retry text, held back until the round has actually applied AND persisted it.
        #: A failed, malformed or transition-invalid retry must never be reported as what
        #: the round applied while durable state says otherwise.
        self._retry_candidate: str | None = None
        self.retry_register: str | None = None
        self.register_status: str | None = None
        self.deadline: float | None = None
        self.claims_enabled = False
        self._latched = False
        self._settled = False

    def prepare(self) -> list[str]:
        """Load state, re-check what the lineage already holds, and render the blocks."""
        try:
            self.lineage = cc.load_lineage(self.state_root, self.lineage_id,
                                           stamp=self.stamp, mode=self.mode)
        except cc.StateUnavailable as exc:
            self.unavailable = str(exc)
            return []
        try:
            cc.open_latch(self.state_root, self.lineage_id)
        except cc.StateUnavailable as exc:
            # The review still runs and is still returned; it simply cannot be settled.
            self.unavailable = str(exc)
            return []
        self._latched = True
        self._before_sweep()
        self._sweep()
        return self._blocks()

    # ── hooks the plan subclass turns off ──

    def _before_sweep(self) -> None:
        """Branch-only: fold `exempt`/`unexempt` arguments in before the sweep."""

    def _sweep(self, only: list[str] | None = None) -> None:
        """Branch-only: re-run every mechanized predicate. A plan lineage holds none."""

    def _blocks(self) -> list[str]:
        assert self.lineage is not None
        return [b for b in (cc.render_unmechanized(self.lineage),) if b]

    def settle(self, review: Review, engine: Engine, repo: Path, model: str, effort: str,
               web_search: bool, on_progress: Callable[[str], None] | None) -> str:
        if self.unavailable or self.lineage is None:
            return (f"CLASS-CLOSURE: STATE-UNAVAILABLE — {self.unavailable}\n"
                    "CONVERGENCE: BLOCKED — lineage state could not be used this round.")
        lineage = self.lineage
        if review.error:
            # A CLI failure or timeout is not a review. Recording debt or applying whatever
            # text came back would let a broken run mutate durable state — and the plan
            # requires a failed engine call to leave the lineage byte-identical.
            self._settled = True
            return (f"CLASS-CLOSURE: not evaluated — the review failed "
                    f"(exit {review.returncode}); lineage state is unchanged.\n"
                    "CONVERGENCE: BLOCKED — no verdict can be computed from a failed review.")
        status, minted = cc.NONE, []
        try:
            minted, status = self._register(review, engine, repo, model, effort,
                                            web_search, on_progress)
            # Round 10: a class registered by THIS review does not exist until now, so it
            # must be evaluated before the verdict — otherwise a new MAJOR class and
            # NOT-BLOCKED could ship in the same response.
            self._sweep(only=minted)
            lineage.debt = None
        except cc.RegisterError as exc:
            lineage.debt = {"round": self.round_no, "reason": str(exc)}
            status = f"malformed: {exc}"

        lineage.rounds += 1
        try:
            cc.save_lineage(self.state_root, lineage)
        except cc.StateUnavailable as exc:
            # The latch deliberately STAYS: a write that may have half-happened must block
            # the next round rather than let it start from an empty lineage.
            return (f"CLASS-CLOSURE: STATE-UNAVAILABLE — {exc}\n"
                    "CONVERGENCE: BLOCKED — this round's classes were not persisted.")
        self._settled = True
        self.register_status = status
        if lineage.debt is None:
            self.retry_register = self._retry_candidate
        return self._render_trailer(lineage, register_status=status, minted=minted)

    def _render_trailer(
        self, lineage: cc.Lineage, *, register_status: str, minted: list[str]
    ) -> str:
        return cc.render_trailer(lineage, register_status=register_status, minted=minted)

    def abandon(self) -> None:
        """The round died before it could settle. Nothing was written, so the latch has
        nothing to protect and must not outlive the exception that is already propagating."""
        self._settled = True

    def release(self) -> None:
        """Clear the pending latch once the round is over WITHOUT an unresolved write.

        Called from a `finally` covering everything after `prepare()`, so no failure between
        the two can strand the latch and block every later round on a fault the caller has
        already been told about. A failed *write* does not release: that is the one
        genuinely ambiguous case, and the one the latch exists for.
        """
        if self._latched and self._settled:
            cc.clear_latch(self.state_root, self.lineage_id)
            self._latched = False

    # ── internals ──

    def _register(self, review: Review, engine: Engine, repo: Path, model: str, effort: str,
                  web_search: bool, on_progress: Callable[[str], None] | None
                  ) -> tuple[list[str], str]:
        """Parse AND apply the register as one transaction, retried once as a whole.

        Splitting them meant only *syntactic* failures earned the retry: an unknown class
        id, a superseded source, two transitions against one class or a cap violation all
        went straight to durable debt, costing the operator a whole extra review round for
        what is usually a reviewer typo — the principal cost this feature has under these
        stakes.
        """
        try:
            return self._attempt(review.text)
        except cc.RegisterError as first:
            if not review.session_ref or not hasattr(engine, "resume"):
                # Claude's supported non-JSON fallback has no session to resume, and an
                # injected engine may predate `resume` (the reason `_progress_kwargs`
                # exists). Retrying either would raise and replace the paid review with
                # an error — the one outcome this path must never produce.
                raise first
            if self.deadline is not None and (
                time.monotonic() + PLAN_REGISTER_RETRY_TIMEOUT_SEC
                + PLAN_TEARDOWN_RESERVE_SEC > self.deadline
            ):
                raise cc.RegisterError(
                    "whole-plan deadline leaves insufficient time for the bounded "
                    "class-register retry"
                ) from first
            retry_kwargs = _progress_kwargs(on_progress)
            if self.deadline is not None:
                retry_kwargs["timeout"] = PLAN_REGISTER_RETRY_TIMEOUT_SEC
            retry = engine.resume(
                review.session_ref, prompts.register_retry(str(first)), repo, model, effort,
                web_search, **retry_kwargs)
            self._retry_candidate = retry.text
            if retry.error:
                # A failed CLI still returns text, and that text can contain a parseable
                # NONE or CLOSED block. Trusting it would let a broken retry mutate durable
                # state — the same reason `settle` refuses a failed review outright.
                raise cc.RegisterError(
                    f"the register retry itself failed (exit {retry.returncode})"
                ) from first
            minted, count = self._attempt(retry.text)   # a second failure raises, and blocks
            return minted, f"parsed after retry: {count}"

    def _attempt(self, text: str) -> tuple[list[str], str]:
        """Apply `text`'s register to a draft, and adopt it only if the whole thing holds."""
        assert self.lineage is not None
        register = cc.parse_register(text, allow_mechanized=self.allow_mechanized)
        draft = cc.copy_lineage(self.lineage)
        minted = cc.apply_register(draft, register, round_no=self.round_no)
        self.lineage.classes = draft.classes
        self.lineage.next_seq = draft.next_seq
        self.lineage.exemptions = draft.exemptions
        return minted, _count(register)


class _ClassClosure(_ClosureRound):
    """Branch mode: mechanized predicates re-run against one immutable git snapshot."""

    def __init__(self, repo: Path, head_id: str, *, args: dict[str, Any], round_no: int,
                 is_dirty: bool, base_ref: str, head_ref: str | None,
                 state_root: Path, stamp: str) -> None:
        super().__init__(
            _lineage_id(repo, base_ref, head_ref, is_dirty, args.get("lineage")),
            round_no=round_no, state_root=state_root, stamp=stamp,
        )
        self.repo, self.head_id, self.args = repo, head_id, args
        self.budget = cc.Budget()

    def _before_sweep(self) -> None:
        self._apply_exemption_args()

    def _sweep(self, only: list[str] | None = None) -> None:
        assert self.lineage is not None
        cc.sweep(self.lineage, self._grep(), only=only, budget=self.budget,
                 clock=time.monotonic)

    def _blocks(self) -> list[str]:
        assert self.lineage is not None
        return [b for b in (cc.render_unclosed(self.lineage),
                            cc.render_unmechanized(self.lineage),
                            cc.render_exempt(self.lineage)) if b]

    def _grep(self) -> cc.GitGrep:
        return cc.make_grep(self.repo, self.head_id, runner=_run_git)

    def _apply_exemption_args(self) -> None:
        assert self.lineage is not None
        for e in self.args.get("exempt", []) or []:
            self.lineage.exemptions.append(cc.Exemption(
                class_id=e["class_id"], path=e["path"], line=int(e["line"]),
                fingerprint=cc.fingerprint(e.get("line_text", "")),
            ))
        drop = {(e["class_id"], e["path"], int(e["line"]))
                for e in (self.args.get("unexempt", []) or [])}
        if drop:
            self.lineage.exemptions = [
                e for e in self.lineage.exemptions
                if (e.class_id, e.path, e.line) not in drop
            ]


class _PlanClassClosure(_ClosureRound):
    """Plan mode: unmechanized classes only, no repository, and no `git grep` ever.

    Inherits the whole settle/latch/retry half unchanged. The base's `_sweep` is a no-op
    and is NOT overridden here — that is the contract: plan mode must never construct a
    grep, because a predicate over plan prose closes the moment the wording changes.
    """

    mode = cc.PLAN_MODE
    allow_mechanized = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.claims_enabled = False
        self.claim_state: dict[str, Any] = {}

    def _render_trailer(
        self, lineage: cc.Lineage, *, register_status: str, minted: list[str]
    ) -> str:
        if not self.claims_enabled:
            return super()._render_trailer(
                lineage, register_status=register_status, minted=minted
            )
        class_text = cc.render_trailer(
            lineage, register_status=register_status, minted=minted
        ).replace("CONVERGENCE:", "CLASS-CONVERGENCE:", 1)
        claim_text = pc.render_trailer(self.claim_state)
        blockers: list[str] = []
        if lineage.debt or lineage.blocking():
            blockers.append("class closure")
        if pc.is_blocked(self.claim_state):
            blockers.append("external claim closure")
        if blockers:
            final = "CONVERGENCE: BLOCKED — " + " and ".join(blockers) + " remain open."
        else:
            final = (
                "CONVERGENCE: NOT-BLOCKED — no blocking class is unclosed and every "
                "active external claim is supported by frozen or current authoritative evidence."
            )
        return f"{claim_text}\n{class_text}\n{final}"


def _lineage_id(repo: Path, base_ref: str, head_ref: str | None, is_dirty: bool,
                explicit: str | None) -> str:
    if explicit:
        return explicit
    if is_dirty or not head_ref or head_ref == "HEAD":
        # `symbolic-ref` reads the ref HEAD POINTS AT rather than resolving it to an
        # object, so it works before the first commit — `rev-parse` exits 128 there and
        # would break the supported unborn-repository first review.
        name = _git_line(["git", "symbolic-ref", "-q", "HEAD"], repo)
    else:
        name = _git_line(["git", "rev-parse", "--symbolic-full-name", head_ref], repo)
    if not name:
        raise ValueError(
            "class closure cannot derive a lineage: the reviewed ref is not a branch "
            "(a detached HEAD or a raw commit). Pass `lineage` explicitly, or "
            "`class_closure: false`."
        )
    key = "\0".join([str(repo.resolve()), base_ref, name])
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _git_line(argv: list[str], repo: Path) -> str:
    proc = subprocess.run(argv, cwd=repo, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _run_git(argv: list[str], cwd: Path, timeout: int) -> tuple[int, bytes, bytes]:
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(str(exc)) from exc
    return proc.returncode, proc.stdout, proc.stderr


def _count(register: cc.Register) -> str:
    """`NONE` and `parsed 0` are different facts about a review, and an operator reading
    the trailer needs to tell an empty register from one whose records were all accepted."""
    total = len(register.new_classes) + len(register.transitions)
    return cc.NONE if total == 0 else f"parsed {total}"
