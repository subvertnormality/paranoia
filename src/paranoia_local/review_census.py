"""Pure protocol for staged structural review.

The model discovers findings; this module only proves that every reported item and
tracked class received one coherent, durable disposition before state can clear.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from . import class_closure as cc, staged_protocol as sp

CHECKLIST = sp.CHECKLIST
LANES = sp.LANES
BLOCKING = sp.BLOCKING
MAX_CLASS_CONTEXT_CHARS = 64_000
MAX_STAGED_PROMPT_CHARS = 5_000_000
MAX_CONSOLIDATION_PROMPT_CHARS = 1_000_000
MAX_REJECTED_PAYLOAD_CHARS = 12_000
MAX_ENGINE_FAILURE_MESSAGE_CHARS = 4_000
PHASES = frozenset({"census", "correction", "final", "clear"})
CENSUS_CACHE_VERSION = 3
PERSISTENCE_REBUT_ROUNDS = 3
PERSISTENCE_CORRECTION_LIMIT = 6
REOPEN_CORRECTION_LIMIT = 3


class CensusError(ValueError):
    pass


@dataclass(frozen=True)
class Attempt:
    role: str
    engine: str
    session_ref: str | None
    outcome: str
    duration_ms: int | None
    usage: dict[str, Any] | None
    response_sha256: str | None = None
    response_excerpt: str | None = None
    sequence: int | None = None
    returncode: int | None = None
    raw_sha256: str | None = None
    raw_excerpt: str | None = None
    failure_detail_sha256: str | None = None
    failure_detail_excerpt: str | None = None
    stderr_sha256: str | None = None
    stderr_excerpt: str | None = None
    validation_issue: str | None = None
    validation_pointer: str | None = None
    rejected_reply_sha256: str | None = None
    rejected_reply_excerpt: str | None = None
    requested_timeout_sec: int | None = None
    provider_duration_ms: int | None = None

    def json(self) -> dict[str, Any]:
        return vars(self)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()


def bounded_diagnostic(text: str, cap: int) -> str:
    """Bound diagnostic text while preserving both the governing head and tail."""
    if len(text) <= cap:
        return text
    marker = "\n… [bounded diagnostic] …\n"
    half = (cap - len(marker)) // 2
    return text[:half] + marker + text[-(cap - len(marker) - half):]


def rendered_diagnostic(text: str) -> str:
    """Render untrusted diagnostics as an inert indented Markdown code block."""
    bounded = bounded_diagnostic(text, sp.MAX_ISSUE_CHARS)
    lines = bounded.splitlines() or [""]
    return "\n".join(f"    {line}" for line in lines)


def trailer_diagnostic(text: Any) -> str:
    """Encode a diagnostic as JSON string content on exactly one trailer line."""
    return json.dumps(str(text), ensure_ascii=True)[1:-1]


def rejected_payload(
    role: str, text: str, *, sequence: int | None = None,
    validation_issue: str | None = None,
) -> dict[str, Any]:
    """Bound one rejected extracted reply; hash every string JSON can decode."""
    if len(text) <= MAX_REJECTED_PAYLOAD_CHARS:
        excerpt = text
    else:
        half = MAX_REJECTED_PAYLOAD_CHARS // 2
        excerpt = (
            text[:half]
            + "\n… [bounded rejected staged output] …\n"
            + text[-half:]
        )
    row = {
        "role":role, "sequence":sequence,
        # Engine JSON extraction can legally produce unpaired surrogates.  This
        # diagnostic digest is deliberately separate from structural digest(),
        # whose historical surrogateescape contract keys durable state.
        "sha256":hashlib.sha256(
            text.encode("utf-8", "surrogatepass")
        ).hexdigest(),
        "excerpt":excerpt,
    }
    if validation_issue is not None:
        row["validation_issue"] = bounded_diagnostic(
            validation_issue, sp.MAX_ISSUE_CHARS,
        )
    return row


def render_error_review(message: str, *, settlement_computed: bool = False) -> str:
    safe = rendered_diagnostic(str(message))
    lifecycle = (
        "A structural settlement was computed, but durable persistence could not be confirmed."
        if settlement_computed else "The staged structural review did not complete settlement."
    )
    return (
        "# STAGED REVIEW FAILED\n\n"
        f"{lifecycle} No durable structural verdict is available.\n\n"
        "## Diagnostic\n\n" + safe
    )


def attempt_trailer(attempts: Sequence[Attempt] | Sequence[dict[str, Any]]) -> str:
    rows = [row.json() if isinstance(row, Attempt) else row for row in attempts]
    retries = sum(str(row.get("role", "")).endswith("-validation-retry") for row in rows)
    invalid = sum(row.get("outcome") == "validation-invalid" for row in rows)
    execution_failed = sum(
        row.get("outcome") not in {"completed", "validation-invalid"} for row in rows
    )
    return (
        f"STAGED-ATTEMPTS: total={len(rows)} validation-retries={retries} "
        f"validation-invalid={invalid} execution-failed={execution_failed}"
    )


def normalize_state(raw: Any, *, stakes: str, snapshot: str) -> dict[str, Any]:
    sd = digest(stakes)
    if not isinstance(raw, dict) or raw.get("version") != 1 or raw.get("stakes_digest") != sd:
        return {
            "version": 1, "stakes_digest": sd, "stakes": stakes,
            "phase": "census", "snapshot_digest": snapshot, "debt": [],
        }
    out = dict(raw)
    if out.get("phase") not in PHASES or not isinstance(out.get("debt"), list):
        raise CensusError("invalid persisted review_state")
    if out["phase"] == "clear" and out.get("snapshot_digest") != snapshot:
        out.update(phase="census", snapshot_digest=snapshot, debt=[])
    return out


def validate_correction_debt(debt: Any) -> list[Mapping[str, Any]]:
    """Validate durable correction debt before either public seam dereferences it."""
    if not isinstance(debt, list):
        raise CensusError("invalid persisted review_state debt")
    seen_debt: set[str] = set()
    for index, row in enumerate(debt):
        pointer = f"/debt/{index}"
        if not isinstance(row, Mapping):
            raise CensusError(f"{pointer}: persisted debt row must be an object")
        debt_id = row.get("id")
        if not isinstance(debt_id, str) or not debt_id:
            raise CensusError(f"{pointer}/id: persisted debt id must be a nonempty string")
        if debt_id in seen_debt:
            raise CensusError(f"{pointer}/id: duplicate persisted debt id {debt_id!r}")
        seen_debt.add(debt_id)
        class_ids = row.get("class_ids", [])
        if not isinstance(class_ids, list):
            raise CensusError(f"{pointer}/class_ids: persisted class_ids must be a list")
        if any(not isinstance(class_id, str) for class_id in class_ids):
            raise CensusError(
                f"{pointer}/class_ids: persisted class references must be strings"
            )
    return debt


def plan_correction_blocking_units(
    debt: Any, active_classes: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return stable blocking units for a late plan-correction sweep."""
    rows = validate_correction_debt(debt)
    blocking_classes = [
        row["class_id"] for row in active_classes
        if row.get("severity") in BLOCKING
        and row.get("status") in cc.UNPROVEN_STATUSES
    ]
    blocking_ids = set(blocking_classes)
    units = [f"class:{class_id}" for class_id in blocking_classes]
    for row in rows:
        debt_id = row["id"]
        class_ids = row.get("class_ids", [])
        if (
            row.get("status") == "open"
            and row.get("severity") in BLOCKING
            and not any(class_id in blocking_ids for class_id in class_ids)
        ):
            units.append(f"debt:{debt_id}")
    return tuple(units)


def _valid_session_ref(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        return False
    return all(
        ch not in "\r\n\0" and ord(ch) >= 32 and ord(ch) != 127
        and not 0xD800 <= ord(ch) <= 0xDFFF
        for ch in value
    )


def validated_session_ref(value: Any) -> str | None:
    """Return usable provider session authority without ever persisting poison state."""
    return value if isinstance(value, str) and _valid_session_ref(value) else None


def normalize_correction_control(
    review_state: Mapping[str, Any], active: Sequence[cc.TrackedClass],
) -> dict[str, Any]:
    """Validate the durable correction gate, or synthesize its sole legacy shape."""
    expected = {item.class_id for item in active}
    raw = review_state.get("correction_control")
    if raw is None:
        return {
            "version": 1,
            "classes": {
                item.class_id: {
                    "reset_round": None, "reopen_count": 0,
                    "last_session_ref": None,
                }
                for item in active
            },
        }
    if (
        not isinstance(raw, dict) or set(raw) != {"version", "classes"}
        or type(raw.get("version")) is not int or raw["version"] != 1
        or not isinstance(raw.get("classes"), dict)
        or set(raw["classes"]) != expected
    ):
        raise CensusError("invalid persisted correction_control")
    rows: dict[str, dict[str, Any]] = {}
    for class_id, row in raw["classes"].items():
        if not isinstance(row, dict) or set(row) != {
            "reset_round", "reopen_count", "last_session_ref",
        }:
            raise CensusError(f"invalid correction_control row for {class_id!r}")
        reset = row["reset_round"]
        count = row["reopen_count"]
        last_round = review_state.get("last_round")
        if reset is not None and (
            type(reset) is not int or reset < 1
            or type(last_round) is not int or reset > last_round
        ):
            raise CensusError(f"invalid correction_control reset_round for {class_id!r}")
        if type(count) is not int or count < 0:
            raise CensusError(f"invalid correction_control reopen_count for {class_id!r}")
        if not _valid_session_ref(row["last_session_ref"]):
            raise CensusError(f"invalid correction_control last_session_ref for {class_id!r}")
        rows[class_id] = dict(row)
    return {"version": 1, "classes": rows}


def correction_gates(
    active: Sequence[cc.TrackedClass], control: Mapping[str, Any], *, round_no: int,
) -> list[dict[str, Any]]:
    """Project the deterministic correction obligations for this caller round label."""
    rows = control["classes"]
    gates: list[dict[str, Any]] = []
    for item in sorted(active, key=lambda value: value.class_id):
        if not item.blocking:
            continue
        row = rows[item.class_id]
        start = (
            row["reset_round"] + 1
            if row["reset_round"] is not None else item.first_round
        )
        span = round_no - start + 1
        persistence = span > PERSISTENCE_CORRECTION_LIMIT
        reopen = row["reopen_count"] >= REOPEN_CORRECTION_LIMIT
        if persistence or reopen:
            reason = (
                "persistence+reopen" if persistence and reopen
                else "persistence" if persistence else "reopen"
            )
            gates.append({
                "class_id": item.class_id, "reason": reason,
                "span": span, "reopen_count": row["reopen_count"],
            })
    return gates


def advance_correction_control(
    control: Mapping[str, Any], *, after: cc.Lineage,
    round_no: int, phase: str, reopened_class_ids: Sequence[str] = (),
    session_ref: str | None = None, recalibrated: bool = False,
    replacement_successor_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Advance control only after canonical settlement has succeeded."""
    prior = control["classes"]
    reopened = set(reopened_class_ids)
    replacements = set(replacement_successor_ids)
    current_session = validated_session_ref(session_ref)
    rows: dict[str, dict[str, Any]] = {}
    for item in after.active():
        if item.class_id in replacements:
            row = {"reset_round": round_no, "reopen_count": 0, "last_session_ref": None}
        else:
            row = dict(prior.get(item.class_id, {
                "reset_round": None, "reopen_count": 0, "last_session_ref": None,
            }))
        if item.class_id in reopened:
            row["reopen_count"] += 1
        if phase == "final" and not item.blocking:
            row = {"reset_round": None, "reopen_count": 0, "last_session_ref": None}
        elif recalibrated:
            row = {"reset_round": round_no, "reopen_count": 0, "last_session_ref": None}
        elif item.blocking:
            # Current-attempt authority replaces stale authority even when absent or
            # malformed. A bad provider session must not poison the next lineage load.
            row["last_session_ref"] = current_session
        else:
            # Closed and advisory classes have no correction gate to reset. Keeping
            # their old session would let a later bound rebut manufacture a window.
            row["last_session_ref"] = None
        rows[item.class_id] = row
    return {"version": 1, "classes": rows}


def class_context(blocks: Iterable[str]) -> str:
    text = "\n\n".join(x for x in blocks if x)
    if len(text) > MAX_CLASS_CONTEXT_CHARS:
        raise CensusError(
            f"STATE-OVERSIZED: rendered class context is {len(text)} characters; "
            f"supported maximum is {MAX_CLASS_CONTEXT_CHARS}"
        )
    return text



def minted_record_ids(
    records: Sequence[dict[str, Any]], minted: Sequence[str],
) -> dict[int, str]:
    """Map staged record positions to IDs minted by the canonical class engine."""
    indexes = [i for i, row in enumerate(records) if row.get("op") == "replace"]
    indexes.extend(i for i, row in enumerate(records) if row.get("op") == "new")
    if len(indexes) != len(minted):
        raise CensusError("minted class count does not match class records")
    return dict(zip(indexes, minted, strict=True))


def register_status(
    records: Sequence[dict[str, Any]], minted_by_record: dict[int, str], *, phase: str,
) -> str:
    operations: list[str] = []
    for index, record in enumerate(records):
        op = record.get("op")
        if op == "new":
            operations.append(f"NEW {minted_by_record[index]}")
        elif op == "replace":
            operations.append(
                f"REPLACE {record.get('class_id')} -> {minted_by_record[index]}"
            )
        elif op in {"close", "reopen", "reclassify"}:
            operations.append(f"{op.upper()} {record.get('class_id')}")
    detail = ", ".join(operations) if operations else "NONE"
    return f"staged {phase} parsed — {detail}"


def register_from_records(
    records: Sequence[dict[str, Any]], *, mechanized: bool | None,
) -> cc.Register:
    new: list[cc.NewClass] = []
    transitions: list[cc.Transition] = []
    for row in records:
        if not isinstance(row, dict):
            raise CensusError("class record must be an object")
        op = row.get("op")
        row_mechanized = mechanized if mechanized is not None else (
            "pattern" in row or "pathspec" in row
        )
        if op == "new":
            allowed = (
                {"op", "invariant", "severity", "pattern", "pathspec"}
                if row_mechanized else {"op", "invariant", "severity", "procedure"}
            )
            _exact(row, allowed, "new class record")
            if row.get("severity") not in cc.SEVERITIES:
                raise CensusError("invalid class severity")
            new.append(cc.NewClass(
                invariant=_bounded(row.get("invariant"), 1000, "class invariant"),
                severity=row.get("severity"),
                pattern=_bounded(row.get("pattern"), 2000, "pattern") if row_mechanized else None,
                pathspec=_bounded(row.get("pathspec"), 1000, "pathspec") if row_mechanized else None,
                procedure=None if row_mechanized else _bounded(row.get("procedure"), 2000, "procedure"),
            ))
        elif op in {"close", "reopen", "reclassify", "replace"}:
            if op in {"close", "reopen"}:
                _exact(row, {"op", "class_id"}, "class transition record")
            elif op == "reclassify":
                _exact(row, {"op", "class_id", "severity"}, "class transition record")
            else:
                allowed = (
                    {"op", "class_id", "invariant", "severity", "pattern", "pathspec"}
                    if row_mechanized else {"op", "class_id", "invariant", "severity", "procedure"}
                )
                _exact(row, allowed, "class replacement record")
            if op in {"reclassify", "replace"} and row.get("severity") not in cc.SEVERITIES:
                raise CensusError("invalid class severity")
            kind = {"close":"CLOSED", "reopen":"REOPEN", "reclassify":"RECLASSIFY", "replace":"REPLACE"}[op]
            transitions.append(cc.Transition(
                kind=kind, class_id=_bounded(row.get("class_id"), 120, "class id"),
                severity=row.get("severity"),
                invariant=(
                    _bounded(row.get("invariant"), 1000, "class invariant")
                    if op == "replace" else None
                ),
                pattern=(
                    _bounded(row.get("pattern"), 2000, "pattern")
                    if op == "replace" and row_mechanized else None
                ),
                pathspec=(
                    _bounded(row.get("pathspec"), 1000, "pathspec")
                    if op == "replace" and row_mechanized else None
                ),
                procedure=(
                    _bounded(row.get("procedure"), 2000, "procedure")
                    if op == "replace" and not row_mechanized else None
                ),
            ))
        else:
            raise CensusError(f"unknown class operation {op!r}")
    return cc.Register(tuple(new), tuple(transitions))


def settle_state(state: dict[str, Any], settlement: dict[str, Any], *, phase: str,
                 snapshot: str, round_no: int) -> dict[str, Any]:
    old = {d["id"]: dict(d) for d in state.get("debt", []) if isinstance(d, dict) and d.get("id")}
    for update in settlement.get("debt_updates", []):
        item = old[update["id"]]
        item.update(status=update["status"], evidence=update["evidence"], last_round=round_no)
        if update["status"] == "open":
            item["reason"] = update["reason"]
        else:
            item.pop("reason", None)
    for item in settlement.get("debt", []):
        if item["id"] in old:
            raise CensusError(f"new debt reuses durable id {item['id']!r}")
        row = dict(item)
        row["source_ids"] = [
            source["source_id"] for source in settlement.get("source_dispositions", [])
            if source["governing_id"] == item["finding_id"]
        ]
        row["class_ids"] = [
            assessment["assessment_id"]
            for assessment in settlement.get("assessment_dispositions", [])
            if assessment["governing_id"] == item["finding_id"]
        ]
        class_ref = settlement.get("_finding_class_refs", {}).get(item["finding_id"])
        if class_ref and not class_ref.startswith("record:"):
            row["class_ids"].append(class_ref)
        row["class_ids"] = list(dict.fromkeys(row["class_ids"]))
        row["class_record_indexes"] = (
            [int(class_ref.split(":", 1)[1])]
            if class_ref and class_ref.startswith("record:") else []
        )
        row["first_round"] = round_no; row["last_round"] = round_no
        old[row["id"]] = row
    active = [d for d in old.values() if d.get("status") == "open" and d.get("severity") in BLOCKING]
    next_phase = "correction" if active else ("clear" if phase == "census" else "final" if phase == "correction" else "clear")
    out = dict(state)
    out.update(phase=next_phase, snapshot_digest=snapshot, debt=list(old.values()), last_round=round_no)
    out.pop("format_debt", None)
    out.pop("validation_debt", None)
    out.pop("staged_failure", None)
    out.pop("census_cache", None)
    out.pop("unbound_classes", None)
    out.pop("unbound_class_ids", None)
    return out


def trailer(
    state: dict[str, Any], *,
    class_first_rounds: Mapping[str, int] | None = None,
    reopened_class_ids: Sequence[str] = (),
    session_ref: str | None = None,
    round_label: int | None = None,
    correction_gates: Sequence[Mapping[str, Any]] = (),
) -> str:
    open_debt = [d for d in state.get("debt", []) if d.get("status") == "open"]
    debt = [d for d in open_debt if d.get("severity") in BLOCKING]
    phase = state.get("phase", "census")
    lines = [f"STRUCTURAL-PHASE: {phase}", f"STRUCTURAL-DEBT: {len(debt)} blocking open"]
    for gate in correction_gates:
        rebut = (
            f"; rebut with session_ref={trailer_diagnostic(session_ref)}"
            if session_ref and gate.get("class_id") in (class_first_rounds or {})
            else ""
        )
        lines.append(
            f"CORRECTION-GATE: {trailer_diagnostic(gate.get('class_id'))} "
            f"reason={gate.get('reason')} span={gate.get('span')} "
            f"reopen-count={gate.get('reopen_count')} — load-bearing this round"
            f"{rebut}"
        )
    current_round = round_label if isinstance(round_label, int) else state.get("last_round")
    if isinstance(current_round, int) and class_first_rounds:
        debt_first_by_class: dict[str, int] = {}
        for item in open_debt:
            first = item.get("first_round")
            if not isinstance(first, int):
                continue
            for class_id in item.get("class_ids", []):
                if isinstance(class_id, str):
                    debt_first_by_class[class_id] = min(
                        first, debt_first_by_class.get(class_id, first),
                    )
        for class_id in sorted(class_first_rounds):
            first = class_first_rounds.get(class_id)
            if not isinstance(first, int):
                continue
            age = current_round - first + 1
            if age < PERSISTENCE_REBUT_ROUNDS:
                continue
            debt_first = debt_first_by_class.get(class_id)
            rebut = (
                f"; rebut with session_ref={trailer_diagnostic(session_ref)}"
                if session_ref else ""
            )
            lines.append(
                f"PERSISTENCE: {trailer_diagnostic(class_id)} currently open; "
                f"round-label span {age} (first raised {first}, now "
                f"{current_round})"
                + (f", current debt open since {debt_first}" if debt_first is not None
                   else ", no governing debt is currently bound")
                + " — repeated correction may be unsatisfiable within this unit's "
                f"scope{rebut}"
            )
    reopened = sorted(dict.fromkeys(
        class_id for class_id in reopened_class_ids if isinstance(class_id, str)
    ))
    if reopened:
        lines.append(
            f"REOPEN-WAVE: {len(reopened)} previously closed class(es) reopened this "
            f"round: {', '.join(trailer_diagnostic(item) for item in reopened)} — "
            "re-arm any prior disposition and reassess scope before another correction"
        )
    validation_debt = state.get("validation_debt") or state.get("format_debt")
    if state.get("staged_failure"):
        failure = state["staged_failure"]
        if isinstance(failure, dict):
            role = failure.get("role", "unknown")
            kind = failure.get("kind", "unknown")
            message = failure.get("message", "staged review failed")
            lines.append(f"STRUCTURAL-ERROR: {trailer_diagnostic(message)}")
            lines.append(f"STRUCTURAL-FAILURE: role={role} kind={kind}")
            lines.append(f"CONVERGENCE: BLOCKED — staged {kind} failure did not settle.")
        else:
            # Version-1 state written before structured failure metadata.
            lines.append(f"STRUCTURAL-ERROR: {trailer_diagnostic(failure)}")
            lines.append("CONVERGENCE: BLOCKED — staged failure did not settle.")
    elif validation_debt:
        if isinstance(validation_debt, dict):
            role = validation_debt.get("role", "consolidation-validation-retry")
            kind = validation_debt.get("kind", "validation")
            message = validation_debt.get("message", "settlement validation rejected")
            lines.append(f"STRUCTURAL-ERROR: {trailer_diagnostic(message)}")
            lines.append(f"STRUCTURAL-FAILURE: role={role} kind={kind}")
        else:
            lines.append(f"STRUCTURAL-ERROR: {trailer_diagnostic(validation_debt)}")
        lines.append("CONVERGENCE: BLOCKED — staged validation debt remains open.")
    elif state.get("unbound_class_ids"):
        lines.append("CONVERGENCE: BLOCKED — class closure remains open.")
    elif phase == "final":
        lines.append("FINAL-REGRESSION: required")
        lines.append("CONVERGENCE: BLOCKED — cold final regression is required.")
    elif phase == "clear" and not debt:
        lines.append("CONVERGENCE: NOT-BLOCKED — staged structural debt is clear.")
    else:
        lines.append("CONVERGENCE: BLOCKED — staged structural debt remains open.")
    return "\n".join(lines)


def render_review(settlement: dict[str, Any], state: dict[str, Any] | None = None) -> str:
    """Restore the stable human response while JSON remains in Review.raw/audit state."""
    findings = list(settlement.get("findings", []))
    if state is not None:
        current = {row.get("id"): dict(row) for row in findings}
        rendered: list[dict[str, Any]] = []
        consumed: set[str] = set()
        for debt in state.get("debt", []):
            if debt.get("status") != "open":
                continue
            fid = debt.get("finding_id")
            row = dict(current.get(fid, {}))
            row.update(debt)
            rendered.append(row)
            consumed.add(fid)
        rendered.extend(row for fid, row in current.items() if fid not in consumed)
        findings = rendered

    def rows(items: list[dict[str, Any]]) -> str:
        if not items:
            return "Nothing notable."
        return "\n".join(
            f"- [{f['severity']}] {f['summary']}"
            + (f" — remains open: {f['reason']}" if f.get("reason") else "")
            + (f" [classes: {', '.join(f['class_ids'])}]" if f.get("class_ids") else "")
            + f" ({', '.join(f['evidence'])})"
            for f in items
        )

    improvements = [
        f"- [{f['severity']}] {f.get('remedy') or f.get('reason') or 'Resolve the cited debt.'}"
        for f in findings
    ]
    return "\n\n".join((
        "## What works\n\nNothing notable.",
        "## What doesn't work\n\n" + rows(findings),
        "## Risks\n\nNothing notable.",
        "## Gaps\n\nNothing notable.",
        "## Improvements\n\n" + ("\n".join(improvements) if improvements else "Nothing notable."),
    ))


def resolve_anchors(
    value: Any, *, root: Any, plan_lines: int | None = None,
    trusted_roots: dict[str, Any] | None = None,
) -> None:
    """Resolve every evidence array and report all independent bad anchors together."""
    from pathlib import Path
    base = Path(root).resolve()
    issues: list[str] = []
    for pointer, anchor in _walk_evidence(value):
        path, sep, raw_line = anchor.rpartition(":")
        # `path:start-end` is accepted alongside `path:line`. The prompt asks
        # reviewers to quote the offending *lines*, so a range is the natural
        # citation for a multi-line defect and engines emit one unprompted.
        raw_start, dash, raw_end = raw_line.partition("-")
        raw_end = raw_end if dash else raw_start
        if (
            not sep or not raw_start.isdigit() or not raw_end.isdigit()
            or int(raw_start) < 1 or int(raw_end) < int(raw_start)
        ):
            issues.append(f"{pointer}: unresolvable evidence anchor {anchor!r}")
            continue
        # Bound-check the END: a range ending inside the file starts inside it.
        line = int(raw_end)
        if path == "plan":
            if plan_lines is None or line > plan_lines:
                issues.append(f"{pointer}: unresolvable plan anchor {anchor!r}")
            continue
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            issues.append(f"{pointer}: unresolvable repository anchor {anchor!r}")
            continue
        if trusted_roots and "repository" in trusted_roots and (
            not relative.parts or relative.parts[0] != "repository"
        ):
            issues.append(
                f"{pointer}: repository evidence anchor requires repository/ prefix: {anchor!r}"
            )
            continue
        anchor_base = base
        if trusted_roots and relative.parts and relative.parts[0] in trusted_roots:
            anchor_base = Path(trusted_roots[relative.parts[0]]).resolve()
            relative = Path(*relative.parts[1:])
            if not relative.parts:
                issues.append(f"{pointer}: unresolvable repository anchor {anchor!r}")
                continue
        target = anchor_base / relative
        try:
            cursor = anchor_base
            for part in relative.parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    raise OSError("symlink evidence anchors are not snapshot paths")
            resolved = target.resolve(strict=True)
            if not resolved.is_relative_to(anchor_base):
                raise OSError("evidence anchor escapes snapshot")
            count = sum(1 for _ in resolved.open("r", encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            issues.append(f"{pointer}: unresolvable repository anchor {anchor!r}")
            continue
        if line > count:
            issues.append(f"{pointer}: out-of-range repository anchor {anchor!r}")
    if issues:
        ordered = sorted(dict.fromkeys(issues))
        shown = ordered[:sp.MAX_ISSUES]
        if len(ordered) > sp.MAX_ISSUES:
            shown.append(
                f"/: {len(ordered) - sp.MAX_ISSUES} additional anchor errors omitted"
            )
        raise CensusError("\n".join(shown)[:sp.MAX_ISSUE_CHARS])


def _walk_evidence(value: Any, pointer: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            # Materialized settlement debt mirrors governing-finding evidence;
            # report only the model-owned finding pointer the retry can repair.
            if not pointer and key == "debt":
                continue
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            child_pointer = f"{pointer}/{escaped}"
            if key in {"evidence", "assessment_evidence"} and isinstance(child, list):
                for index, anchor in enumerate(child):
                    yield f"{child_pointer}/{index}", anchor
            else:
                yield from _walk_evidence(child, child_pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_evidence(child, f"{pointer}/{index}")



def _exact(row: Any, keys: set[str], label: str) -> None:
    if not isinstance(row, dict):
        raise CensusError(f"invalid {label} fields: expected an object with {sorted(keys)}")
    actual = set(row)
    if actual != keys:
        raise CensusError(
            f"invalid {label} fields: missing {sorted(keys - actual)}, "
            f"unexpected {sorted(actual - keys)}; expected exactly {sorted(keys)}"
        )


def _bounded(value: Any, cap: int, label: str) -> str:
    if (
        not isinstance(value, str) or not value.strip() or len(value) > cap
        or "\n" in value or "\r" in value
    ):
        raise CensusError(f"{label} must be 1..{cap} characters")
    return value
