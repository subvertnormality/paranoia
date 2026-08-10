"""Pure protocol for staged structural review.

The model discovers findings; this module only proves that every reported item and
tracked class received one coherent, durable disposition before state can clear.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from . import class_closure as cc

CHECKLIST = (
    "artifact-complete", "repository-premises", "transformations", "consumers",
    "failure-recovery", "tests-acceptance", "docs-operations", "consistency",
    "proportionality",
)
LANES = {
    cc.PLAN_MODE: ("domain", "execution", "integrity"),
    cc.BRANCH_MODE: ("behaviour", "execution", "integrity"),
}
BLOCKING = frozenset({cc.FATAL, cc.BLOCKER, cc.MAJOR})
LANE_MARKER = "=== REVIEW CENSUS JSON ==="
SETTLEMENT_MARKER = "=== REVIEW SETTLEMENT JSON ==="
MAX_LANE_CHARS = 48_000
MAX_SUMMARY_CHARS = 2_000
MAX_ANCHOR_CHARS = 512
MAX_CLASS_CONTEXT_CHARS = 64_000
MAX_STAGED_PROMPT_CHARS = 5_000_000
MAX_CONSOLIDATION_PROMPT_CHARS = 400_000
PHASES = frozenset({"census", "correction", "final", "clear"})


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

    def json(self) -> dict[str, Any]:
        return vars(self)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()


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


def class_context(blocks: Iterable[str]) -> str:
    text = "\n\n".join(x for x in blocks if x)
    if len(text) > MAX_CLASS_CONTEXT_CHARS:
        raise CensusError(
            f"STATE-OVERSIZED: rendered class context is {len(text)} characters; "
            f"supported maximum is {MAX_CLASS_CONTEXT_CHARS}"
        )
    return text


def parse_lane(text: str, *, lane: str, class_ids: Sequence[str] = ()) -> dict[str, Any]:
    obj = _object(text, LANE_MARKER, MAX_LANE_CHARS)
    if obj.get("lane") != lane:
        raise CensusError(f"lane must be {lane!r}")
    coverage = _list(obj, "coverage")
    got = [row.get("id") for row in coverage if isinstance(row, dict)]
    if sorted(got) != sorted(CHECKLIST) or len(got) != len(set(got)):
        raise CensusError("coverage must contain every checklist id exactly once")
    finding_ids: set[str] = set()
    for row in coverage:
        _exact(row, {"id", "status", "summary", "evidence"}, "coverage row")
        if row["status"] not in {"covered", "finding", "not_applicable"}:
            raise CensusError("invalid coverage status")
        _bounded(row["summary"], MAX_SUMMARY_CHARS, "coverage summary")
        _anchors(row["evidence"])
    for finding in _list(obj, "findings"):
        _exact(finding, {"id", "severity", "summary", "evidence", "remedy"}, "finding")
        fid = _bounded(finding["id"], 120, "finding id")
        if fid in finding_ids:
            raise CensusError(f"duplicate finding id {fid}")
        finding_ids.add(fid)
        if finding["severity"] not in cc.SEVERITIES:
            raise CensusError("invalid finding severity")
        _bounded(finding["summary"], MAX_SUMMARY_CHARS, "finding summary")
        _bounded(finding["remedy"], MAX_SUMMARY_CHARS, "finding remedy")
        _anchors(finding["evidence"])
    assessments = _list(obj, "class_assessments")
    expected = set(class_ids) if lane == "integrity" else set()
    seen: set[str] = set()
    for row in assessments:
        _exact(row, {"class_id", "verdict", "evidence", "finding_id"}, "class assessment")
        cid = row["class_id"]
        if cid in seen or cid not in expected:
            raise CensusError(f"unexpected or duplicate class assessment {cid!r}")
        seen.add(cid)
        if row["verdict"] not in {"satisfied", "violated"}:
            raise CensusError("invalid class verdict")
        _anchors(row["evidence"])
        if row["verdict"] == "violated" and row.get("finding_id") not in finding_ids:
            raise CensusError("violated class must name a lane finding")
        if row["verdict"] == "satisfied" and row.get("finding_id") is not None:
            raise CensusError("satisfied class cannot name a finding")
    if seen != expected:
        raise CensusError("integrity lane must assess every active class exactly once")
    return obj


def parse_settlement(
    text: str, *, source_ids: Sequence[str], assessment_ids: Sequence[str],
    known_debt: Sequence[str] = (), role: str = "census",
) -> dict[str, Any]:
    obj = _object(text, SETTLEMENT_MARKER, MAX_CONSOLIDATION_PROMPT_CHARS)
    if obj.get("role") != role:
        raise CensusError(f"settlement role must be {role!r}")
    findings = _list(obj, "findings")
    finding_ids = _unique_ids(findings, "governing finding")
    debt = _list(obj, "debt")
    debt_ids = _unique_ids(debt, "debt")
    source_rows = _list(obj, "source_dispositions")
    _exact_dispositions(source_rows, source_ids, finding_ids, "source_id")
    assessment_rows = _list(obj, "assessment_dispositions")
    _exact_dispositions(assessment_rows, assessment_ids, finding_ids, "assessment_id", allow_null=True)
    for finding in findings:
        _exact(finding, {"id", "severity", "summary", "evidence", "remedy"}, "governing finding")
        if finding["severity"] not in cc.SEVERITIES:
            raise CensusError("invalid governing severity")
        _bounded(finding["summary"], MAX_SUMMARY_CHARS, "governing summary")
        _bounded(finding["remedy"], MAX_SUMMARY_CHARS, "governing remedy")
        _anchors(finding["evidence"])
        if finding["severity"] in BLOCKING:
            matches = [d for d in debt if d.get("finding_id") == finding["id"] and d.get("status") == "open"]
            if len(matches) != 1:
                raise CensusError("each blocking finding needs exactly one open debt record")
    for item in debt:
        _exact(item, {"id", "finding_id", "severity", "summary", "evidence", "status"}, "debt")
        if item["finding_id"] not in finding_ids or item["status"] not in {"open", "closed"}:
            raise CensusError("invalid debt mapping")
        _anchors(item["evidence"])
    updates = _list(obj, "debt_updates")
    seen_updates: set[str] = set()
    for item in updates:
        _exact(item, {"id", "status", "evidence"}, "debt update")
        if item["id"] in seen_updates or item["id"] not in set(known_debt):
            raise CensusError("unexpected or duplicate debt update")
        seen_updates.add(item["id"])
        if item["status"] not in {"open", "closed"}:
            raise CensusError("invalid debt-update status")
        _anchors(item["evidence"])
    if known_debt and seen_updates != set(known_debt):
        raise CensusError("every existing debt item must be updated exactly once")
    _list(obj, "class_records")
    return obj


def register_from_records(records: Sequence[dict[str, Any]], *, mechanized: bool) -> cc.Register:
    new: list[cc.NewClass] = []
    transitions: list[cc.Transition] = []
    for row in records:
        if not isinstance(row, dict):
            raise CensusError("class record must be an object")
        op = row.get("op")
        if op == "new":
            new.append(cc.NewClass(
                invariant=_bounded(row.get("invariant"), 1000, "class invariant"),
                severity=row.get("severity"), pattern=row.get("pattern") if mechanized else None,
                pathspec=row.get("pathspec") if mechanized else None,
                procedure=None if mechanized else _bounded(row.get("procedure"), 2000, "procedure"),
            ))
        elif op in {"close", "reopen", "reclassify", "replace"}:
            kind = {"close":"CLOSED", "reopen":"REOPEN", "reclassify":"RECLASSIFY", "replace":"REPLACE"}[op]
            transitions.append(cc.Transition(
                kind=kind, class_id=row.get("class_id"), severity=row.get("severity"),
                invariant=row.get("invariant"), pattern=row.get("pattern"),
                pathspec=row.get("pathspec"), procedure=row.get("procedure"),
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
    for item in settlement.get("debt", []):
        row = dict(item); row["first_round"] = round_no; row["last_round"] = round_no
        old[row["id"]] = row
    active = [d for d in old.values() if d.get("status") == "open" and d.get("severity") in BLOCKING]
    next_phase = "correction" if active else ("clear" if phase == "census" else "final" if phase == "correction" else "clear")
    out = dict(state)
    out.update(phase=next_phase, snapshot_digest=snapshot, debt=list(old.values()), last_round=round_no)
    return out


def trailer(state: dict[str, Any]) -> str:
    debt = [d for d in state.get("debt", []) if d.get("status") == "open" and d.get("severity") in BLOCKING]
    phase = state.get("phase", "census")
    lines = [f"STRUCTURAL-PHASE: {phase}", f"STRUCTURAL-DEBT: {len(debt)} blocking open"]
    if phase == "final":
        lines.append("FINAL-REGRESSION: required")
        lines.append("CONVERGENCE: BLOCKED — cold final regression is required.")
    elif phase == "clear" and not debt:
        lines.append("CONVERGENCE: NOT-BLOCKED — staged structural debt is clear.")
    else:
        lines.append("CONVERGENCE: BLOCKED — staged structural debt remains open.")
    return "\n".join(lines)


def _object(text: str, marker: str, cap: int) -> dict[str, Any]:
    if len(text) > cap:
        raise CensusError(f"reply exceeds {cap} characters")
    pos = text.rfind(marker)
    raw = text[pos + len(marker):].strip() if pos >= 0 else text.strip()
    try: obj = json.loads(raw)
    except json.JSONDecodeError as exc: raise CensusError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict): raise CensusError("JSON result must be an object")
    return obj


def _list(obj: dict[str, Any], key: str) -> list[Any]:
    value = obj.get(key)
    if not isinstance(value, list): raise CensusError(f"{key} must be a list")
    return value


def _exact(row: Any, keys: set[str], label: str) -> None:
    if not isinstance(row, dict) or set(row) != keys: raise CensusError(f"invalid {label} fields")


def _bounded(value: Any, cap: int, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > cap:
        raise CensusError(f"{label} must be 1..{cap} characters")
    return value


def _anchors(value: Any) -> None:
    if not isinstance(value, list) or not value: raise CensusError("evidence anchors cannot be empty")
    for anchor in value: _bounded(anchor, MAX_ANCHOR_CHARS, "evidence anchor")


def _unique_ids(rows: Sequence[Any], label: str) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in ids:
            raise CensusError(f"invalid or duplicate {label} id")
        ids.add(row["id"])
    return ids


def _exact_dispositions(rows: Sequence[Any], expected: Sequence[str], targets: set[str], key: str,
                        allow_null: bool = False) -> None:
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {key, "governing_id"}:
            raise CensusError(f"invalid {key} disposition")
        target = row["governing_id"]
        if (row[key] in seen or row[key] not in set(expected)
                or (target not in targets and not (allow_null and target is None))):
            raise CensusError(f"invalid or duplicate {key} disposition")
        seen.add(row[key])
    if seen != set(expected): raise CensusError(f"every {key} must be dispositioned exactly once")
