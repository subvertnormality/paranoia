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
    response_sha256: str | None = None
    response_excerpt: str | None = None

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
    source_severities: dict[str, str] | None = None,
    assessment_verdicts: dict[str, str] | None = None,
    class_states: dict[str, tuple[str, bool, str]] | None = None,
    class_mechanized: bool | None = None,
    known_debt: Sequence[str] = (), role: str = "census",
) -> dict[str, Any]:
    obj = _object(text, SETTLEMENT_MARKER, MAX_CONSOLIDATION_PROMPT_CHARS)
    if obj.get("role") != role:
        raise CensusError(f"settlement role must be {role!r}")
    if role == "final":
        parsed_final = parse_lane(
            LANE_MARKER + "\n" + json.dumps({
                "lane": "integrity", "coverage": obj.get("coverage"),
                "findings": obj.get("findings"),
                "class_assessments": obj.get("class_assessments"),
            }),
            lane="integrity", class_ids=assessment_ids,
        )
        assessment_ids = [a["class_id"] for a in parsed_final["class_assessments"]]
        assessment_verdicts = {
            a["class_id"]: a["verdict"] for a in parsed_final["class_assessments"]
        }
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
    by_id = {f["id"]: f for f in findings}
    # FATAL and BLOCKER both block, but they are not interchangeable labels: a
    # plan-level impossibility must not be hidden by consolidating it as BLOCKER.
    rank = {cc.OUT_OF_SCOPE: 0, cc.MINOR: 1, cc.MAJOR: 2, cc.BLOCKER: 3, cc.FATAL: 4}
    for row in source_rows:
        source_severity = (source_severities or {}).get(row["source_id"])
        if source_severity and rank[by_id[row["governing_id"]]["severity"]] < rank[source_severity]:
            raise CensusError("governing severity cannot downgrade a source finding")
    for item in debt:
        _exact(item, {"id", "finding_id", "status"}, "debt")
        if item["finding_id"] not in finding_ids or item["status"] not in {"open", "closed"}:
            raise CensusError("invalid debt mapping")
        governing = by_id[item["finding_id"]]
        item.update(
            severity=governing["severity"], summary=governing["summary"],
            evidence=list(governing["evidence"]),
        )
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
    disposition_by_class = {r["assessment_id"]: r["governing_id"] for r in assessment_rows}
    operation_by_class: dict[str, str] = {}
    for record in obj["class_records"]:
        cid = record.get("class_id") if isinstance(record, dict) else None
        if cid:
            if class_states is not None and cid not in class_states:
                raise CensusError(f"class operation names unknown active class {cid!r}")
            if cid in operation_by_class:
                raise CensusError("more than one class operation against one assessment")
            operation_by_class[cid] = record.get("op")
            if role == "correction" and record.get("op") in {"reclassify", "replace"}:
                replacement_severity = record.get("severity")
                prior_severity = class_states[cid][2] if class_states else None
                if replacement_severity not in rank:
                    raise CensusError("invalid class severity")
                if prior_severity and rank[replacement_severity] < rank[prior_severity]:
                    raise CensusError("correction cannot downgrade an active class")
    for cid, verdict in (assessment_verdicts or {}).items():
        target = disposition_by_class.get(cid)
        if verdict == "violated" and target is None:
            raise CensusError("violated class assessment must map to a governing finding")
        if verdict == "satisfied" and target is not None:
            raise CensusError("satisfied class assessment cannot map to a finding")
        if class_states and cid in class_states:
            status, mechanized, prior_severity = class_states[cid]
            op = operation_by_class.get(cid)
            if verdict == "violated" and status == cc.CLOSED and op not in {"reopen", "replace"}:
                raise CensusError("closed violated class must reopen or replace")
            if verdict == "satisfied" and status in cc.UNPROVEN_STATUSES:
                if mechanized:
                    raise CensusError("mechanized open class cannot be model-closed")
                if op != "close":
                    raise CensusError("open satisfied class must close")
            if verdict == "violated" and op in {"reclassify", "replace"}:
                record = next(r for r in obj["class_records"] if r.get("class_id") == cid)
                replacement_severity = record.get("severity")
                if replacement_severity not in rank:
                    raise CensusError("invalid class severity")
                if rank[replacement_severity] < rank[prior_severity]:
                    raise CensusError("violated class cannot be downgraded")
    if class_mechanized is not None:
        register_from_records(obj["class_records"], mechanized=class_mechanized)
    return obj


def register_from_records(records: Sequence[dict[str, Any]], *, mechanized: bool) -> cc.Register:
    new: list[cc.NewClass] = []
    transitions: list[cc.Transition] = []
    for row in records:
        if not isinstance(row, dict):
            raise CensusError("class record must be an object")
        op = row.get("op")
        if op == "new":
            allowed = (
                {"op", "invariant", "severity", "pattern", "pathspec"}
                if mechanized else {"op", "invariant", "severity", "procedure"}
            )
            _exact(row, allowed, "new class record")
            if row.get("severity") not in cc.SEVERITIES:
                raise CensusError("invalid class severity")
            new.append(cc.NewClass(
                invariant=_bounded(row.get("invariant"), 1000, "class invariant"),
                severity=row.get("severity"),
                pattern=_bounded(row.get("pattern"), 2000, "pattern") if mechanized else None,
                pathspec=_bounded(row.get("pathspec"), 1000, "pathspec") if mechanized else None,
                procedure=None if mechanized else _bounded(row.get("procedure"), 2000, "procedure"),
            ))
        elif op in {"close", "reopen", "reclassify", "replace"}:
            if op in {"close", "reopen"}:
                _exact(row, {"op", "class_id"}, "class transition record")
            elif op == "reclassify":
                _exact(row, {"op", "class_id", "severity"}, "class transition record")
            else:
                allowed = (
                    {"op", "class_id", "invariant", "severity", "pattern", "pathspec"}
                    if mechanized else {"op", "class_id", "invariant", "severity", "procedure"}
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
                    if op == "replace" and mechanized else None
                ),
                pathspec=(
                    _bounded(row.get("pathspec"), 1000, "pathspec")
                    if op == "replace" and mechanized else None
                ),
                procedure=(
                    _bounded(row.get("procedure"), 2000, "procedure")
                    if op == "replace" and not mechanized else None
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
    for item in settlement.get("debt", []):
        if item["id"] in old:
            raise CensusError(f"new debt reuses durable id {item['id']!r}")
        row = dict(item)
        row["source_ids"] = [
            source["source_id"] for source in settlement.get("source_dispositions", [])
            if source["governing_id"] == item["finding_id"]
        ]
        row["first_round"] = round_no; row["last_round"] = round_no
        old[row["id"]] = row
    active = [d for d in old.values() if d.get("status") == "open" and d.get("severity") in BLOCKING]
    next_phase = "correction" if active else ("clear" if phase == "census" else "final" if phase == "correction" else "clear")
    out = dict(state)
    out.update(phase=next_phase, snapshot_digest=snapshot, debt=list(old.values()), last_round=round_no)
    out.pop("format_debt", None)
    return out


def trailer(state: dict[str, Any]) -> str:
    debt = [d for d in state.get("debt", []) if d.get("status") == "open" and d.get("severity") in BLOCKING]
    phase = state.get("phase", "census")
    lines = [f"STRUCTURAL-PHASE: {phase}", f"STRUCTURAL-DEBT: {len(debt)} blocking open"]
    if state.get("format_debt"):
        lines.append(f"STRUCTURAL-ERROR: {state['format_debt']}")
        lines.append("CONVERGENCE: BLOCKED — staged format debt remains open.")
    elif phase == "final":
        lines.append("FINAL-REGRESSION: required")
        lines.append("CONVERGENCE: BLOCKED — cold final regression is required.")
    elif phase == "clear" and not debt:
        lines.append("CONVERGENCE: NOT-BLOCKED — staged structural debt is clear.")
    else:
        lines.append("CONVERGENCE: BLOCKED — staged structural debt remains open.")
    return "\n".join(lines)


def render_review(settlement: dict[str, Any]) -> str:
    """Restore the stable human response while JSON remains in Review.raw/audit state."""
    findings = settlement.get("findings", [])

    def rows(items: list[dict[str, Any]]) -> str:
        if not items:
            return "Nothing notable."
        return "\n".join(
            f"- [{f['severity']}] {f['summary']} ({', '.join(f['evidence'])})"
            for f in items
        )

    improvements = [f"- [{f['severity']}] {f['remedy']}" for f in findings]
    return "\n\n".join((
        "## What works\n\nNothing notable.",
        "## What doesn't work\n\n" + rows(findings),
        "## Risks\n\nNothing notable.",
        "## Gaps\n\nNothing notable.",
        "## Improvements\n\n" + ("\n".join(improvements) if improvements else "Nothing notable."),
    ))


def resolve_anchors(value: Any, *, root: Any, plan_lines: int | None = None) -> None:
    """Resolve every evidence array in a parsed staged object against the snapshot."""
    from pathlib import Path
    base = Path(root).resolve()
    for row in _walk_dicts(value):
        evidence = row.get("evidence")
        if not isinstance(evidence, list):
            continue
        for anchor in evidence:
            path, sep, raw_line = anchor.rpartition(":")
            if not sep or not raw_line.isdigit() or int(raw_line) < 1:
                raise CensusError(f"unresolvable evidence anchor {anchor!r}")
            line = int(raw_line)
            if path == "plan":
                if plan_lines is None or line > plan_lines:
                    raise CensusError(f"unresolvable plan anchor {anchor!r}")
                continue
            relative = Path(path)
            if relative.is_absolute() or ".." in relative.parts:
                raise CensusError(f"unresolvable repository anchor {anchor!r}")
            target = base / relative
            try:
                count = sum(1 for _ in target.open("r", encoding="utf-8", errors="replace"))
            except (OSError, ValueError) as exc:
                raise CensusError(f"unresolvable repository anchor {anchor!r}") from exc
            if line > count:
                raise CensusError(f"out-of-range repository anchor {anchor!r}")


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _object(text: str, marker: str, cap: int) -> dict[str, Any]:
    if len(text) > cap:
        raise CensusError(f"reply exceeds {cap} characters")
    stripped = text.strip()
    if text.count(marker) != 1 or not stripped.startswith(marker):
        raise CensusError(f"reply must begin with exactly one {marker!r} marker")
    raw = stripped[len(marker):].strip()
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
    if (
        not isinstance(value, str) or not value.strip() or len(value) > cap
        or "\n" in value or "\r" in value
    ):
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
