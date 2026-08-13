"""Executable model contract for staged structural review.

Provider structured output and local validation use the same closed, role-specific
schemas.  The model supplies semantic decisions once; this module validates their
graph and materializes the existing durable settlement shape.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from jsonschema import Draft202012Validator

from . import class_closure as cc
from .external_sources import numbered_lines

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
MAX_SUMMARY_CHARS = 2_000
MAX_ANCHOR_CHARS = 512
MAX_ISSUES = 24
MAX_ISSUE_CHARS = 8_000
MAX_LANE_FINDINGS = 100
MAX_ACTIVE_CLASSES = 100
MAX_CENSUS_SOURCES = len(LANES[cc.PLAN_MODE]) * MAX_LANE_FINDINGS
# One source normally produces one governing finding.  Fan-out may additionally
# produce one distinct existing-class finding for every active class.
MAX_CENSUS_FINDINGS = MAX_CENSUS_SOURCES + MAX_ACTIVE_CLASSES
# The real Protocol v2 lifecycle peaked at 3,265 lane characters and 3,140
# decision characters (2026-08-13 acceptance run).  These role-specific caps
# retain more than two orders of magnitude of headroom while bounding JSON
# decoding and Draft 2020-12 traversal before either begins.
MAX_LANE_RESPONSE_CHARS = 240_000
MAX_DECISION_RESPONSE_CHARS = 1_000_000
MAX_CONSOLIDATION_CONTEXT_CHARS = 200_000


class ProtocolError(ValueError):
    """A structured staged response cannot be safely materialized."""


@dataclass(frozen=True)
class ArtifactView:
    """One coordinate source for displayed plan lines and anchor bounds."""

    original: str
    lines: tuple[str, ...]
    rendered: str

    @classmethod
    def from_text(cls, text: str) -> "ArtifactView":
        lines = tuple(text.splitlines())
        return cls(original=text, lines=lines, rendered=numbered_lines(lines))

    @property
    def line_count(self) -> int:
        return len(self.lines)


def _string(max_length: int, *, enum: Sequence[str] | None = None,
            const: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "string", "minLength": 1, "maxLength": max_length,
        "pattern": r"^[^\r\n]*\S[^\r\n]*$",
    }
    if enum is not None:
        value["enum"] = list(enum)
    if const is not None:
        value["const"] = const
    return value


def _array(items: dict[str, Any], *, maximum: int, minimum: int = 0,
           unique: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "array", "items": items, "minItems": minimum, "maxItems": maximum,
    }
    if unique:
        value["uniqueItems"] = True
    return value


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "properties": properties, "required": list(properties),
    }


def _root(value: dict[str, Any]) -> dict[str, Any]:
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", **value}


def _anchor() -> dict[str, Any]:
    return {
        **_string(MAX_ANCHOR_CHARS),
        "pattern": r"^(?:plan|repository/.+):[1-9][0-9]*(?:-[1-9][0-9]*)?$",
    }


def _pathspec() -> dict[str, Any]:
    value = _string(1_000)
    # A leading colon invokes Git pathspec magic (including exclusions) rather
    # than naming the literal branch-review scope the model is allowed to own.
    value["pattern"] = r"^[^:\r\n][^\r\n]*$"
    return value


def _evidence() -> dict[str, Any]:
    return _array(_anchor(), maximum=100, minimum=1, unique=True)


def _coverage() -> dict[str, Any]:
    return _object({
        "id": _string(80, enum=CHECKLIST),
        "status": _string(32, enum=("covered", "finding", "not_applicable")),
        "summary": _string(MAX_SUMMARY_CHARS),
        "evidence": _evidence(),
        "finding_ids": _array(_string(120), maximum=100, unique=True),
    })


def _finding(*, mode: str, census: bool) -> dict[str, Any]:
    properties = {
        "id": _string(120),
        "severity": _string(32, enum=cc.SEVERITIES),
        "summary": _string(MAX_SUMMARY_CHARS),
        "evidence": _evidence(),
        "remedy": _string(MAX_SUMMARY_CHARS),
    }
    if census:
        properties["source_ids"] = _array(
            _string(240), maximum=MAX_CENSUS_SOURCES, minimum=1, unique=True,
        )
    properties["classification"] = _classification(mode)
    return _object(properties)


def _lane_finding() -> dict[str, Any]:
    return _object({
        "id": _string(120),
        "severity": _string(32, enum=cc.SEVERITIES),
        "summary": _string(MAX_SUMMARY_CHARS),
        "evidence": _evidence(),
        "remedy": _string(MAX_SUMMARY_CHARS),
    })


def _definition(mode: str) -> dict[str, Any]:
    common = {
        "invariant": _string(1_000),
        "severity": _string(32, enum=cc.SEVERITIES),
    }
    procedure = _object({**common, "procedure": _string(2_000)})
    if mode == cc.PLAN_MODE:
        return procedure
    pattern = _object({
        **common, "pattern": _string(2_000), "pathspec": _pathspec(),
    })
    return {"anyOf": [procedure, pattern]}


def _classification(mode: str = cc.PLAN_MODE) -> dict[str, Any]:
    return {"anyOf": [
        _object({
            "kind": _string(32, const="one_off"),
            "reason": _string(MAX_SUMMARY_CHARS),
        }),
        _object({
            "kind": _string(32, const="new_class"),
            "definition": _definition(mode),
        }),
        _object({
            "kind": _string(32, const="existing_class"),
            "class_id": _string(120),
        }),
    ]}


def _lane_assessment() -> dict[str, Any]:
    return {"anyOf": [
        _object({
            "class_id": _string(120),
            "verdict": _string(32, const="satisfied"),
            "evidence": _evidence(),
            "finding_id": {"type": "null"},
        }),
        _object({
            "class_id": _string(120),
            "verdict": _string(32, const="violated"),
            "evidence": _evidence(),
            "finding_id": _string(120),
        }),
    ]}


def _class_outcome() -> dict[str, Any]:
    basis = {"anyOf": [
        _object({
            "kind": _string(32, const="new_finding"),
            "finding_id": _string(120),
        }),
        _object({
            "kind": _string(32, const="carried_debt"),
            "debt_id": _string(120),
        }),
    ]}
    return {"anyOf": [
        _object({
            "class_id": _string(120),
            "verdict": _string(32, const="satisfied"),
            "evidence": _evidence(),
        }),
        _object({
            "class_id": _string(120),
            "verdict": _string(32, const="violated"),
            "evidence": _evidence(),
            "basis": basis,
        }),
    ]}


def _debt_outcome() -> dict[str, Any]:
    return {"anyOf": [
        _object({
            "debt_id": _string(120),
            "status": _string(16, const="closed"),
            "evidence": _evidence(),
        }),
        _object({
            "debt_id": _string(120),
            "status": _string(16, const="open"),
            "evidence": _evidence(),
            "reason": _string(MAX_SUMMARY_CHARS),
        }),
    ]}


def _class_action(mode: str) -> dict[str, Any]:
    return {"anyOf": [
        _object({
            "kind": _string(32, const="close"), "class_id": _string(120),
        }),
        _object({
            "kind": _string(32, const="reopen"), "class_id": _string(120),
        }),
        _object({
            "kind": _string(32, const="reclassify"), "class_id": _string(120),
            "severity": _string(32, enum=cc.SEVERITIES),
        }),
        _object({
            "kind": _string(32, const="replace"), "class_id": _string(120),
            "definition": _definition(mode),
        }),
    ]}


def lane_schema(mode: str, lane: str) -> dict[str, Any]:
    if lane not in LANES.get(mode, ()):
        raise ValueError(f"invalid staged lane {lane!r} for {mode!r}")
    return _root(_object({
        "lane": _string(32, const=lane),
        "coverage": _array(_coverage(), maximum=len(CHECKLIST), minimum=len(CHECKLIST)),
        "findings": _array(_lane_finding(), maximum=MAX_LANE_FINDINGS),
        "class_assessments": _array(_lane_assessment(), maximum=MAX_ACTIVE_CLASSES),
    }))


def decision_schema(mode: str, role: str) -> dict[str, Any]:
    if mode not in LANES:
        raise ValueError(f"invalid staged mode {mode!r}")
    if role not in {"census", "correction", "final"}:
        raise ValueError(f"invalid staged role {role!r}")
    properties = {
        "role": _string(32, const=role),
        "governing_findings": _array(
            _finding(mode=mode, census=role == "census"),
            maximum=MAX_CENSUS_FINDINGS if role == "census" else MAX_LANE_FINDINGS,
        ),
        "debt_outcomes": _array(_debt_outcome(), maximum=500),
        "class_outcomes": _array(_class_outcome(), maximum=MAX_ACTIVE_CLASSES),
        "class_actions": _array(_class_action(mode), maximum=MAX_ACTIVE_CLASSES),
    }
    if role == "final":
        properties["coverage"] = _array(
            _coverage(), maximum=len(CHECKLIST), minimum=len(CHECKLIST),
        )
    return _root(_object(properties))


def canonical_schema(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def provider_schema(schema: Any) -> Any:
    """Remove provider-unsupported metadata/uniqueness from the full local contract.

    Both vendors receive this projection; complete local validation still makes
    duplicates fail closed through the same-session correction path.
    """

    if isinstance(schema, dict):
        return {
            key: provider_schema(value)
            for key, value in schema.items() if key not in {"uniqueItems", "$schema"}
        }
    if isinstance(schema, list):
        return [provider_schema(value) for value in schema]
    return schema


def _pointer(parts: Iterable[Any]) -> str:
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped) if escaped else "/"


def _schema_issues(value: Any, schema: dict[str, Any]) -> list[str]:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    issues: list[str] = []
    for error in errors[:MAX_ISSUES]:
        path = list(error.absolute_path)
        if error.validator == "required":
            match = re.search(r"'([^']+)' is a required property", error.message)
            if match:
                path.append(match.group(1))
        issues.append(f"{_pointer(path)}: {error.message}")
    if len(errors) > MAX_ISSUES:
        issues.append(f"/: {len(errors) - MAX_ISSUES} additional schema errors omitted")
    return issues


def _unicode_issues(value: Any, parts: tuple[Any, ...] = ()) -> list[str]:
    """Reject Unicode scalar violations before any later UTF-8 boundary."""
    issues: list[str] = []
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            issues.append(f"{_pointer(parts)}: string contains an unpaired surrogate")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_unicode_issues(child, (*parts, index)))
    elif isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and any(
                0xD800 <= ord(char) <= 0xDFFF for char in key
            ):
                issues.append(
                    f"{_pointer(parts)}: property name contains an unpaired surrogate"
                )
                continue
            issues.extend(_unicode_issues(child, (*parts, key)))
    return issues


def decode(text: str, schema: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    if len(text) > max_chars:
        raise ProtocolError(
            f"/: response is {len(text)} characters; maximum is {max_chars}"
        )
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"/: invalid JSON at line {exc.lineno} column {exc.colno}") from exc
    issues = _schema_issues(value, schema) + _unicode_issues(value)
    if issues:
        ordered = sorted(dict.fromkeys(issues))
        if len(ordered) > MAX_ISSUES:
            ordered = ordered[:MAX_ISSUES] + [
                f"/: {len(ordered) - MAX_ISSUES} additional validation errors omitted"
            ]
        message = "\n".join(ordered)
        raise ProtocolError(message[:MAX_ISSUE_CHARS])
    assert isinstance(value, dict)
    return value


def _raise_semantic_issues(issues: Sequence[str]) -> None:
    if not issues:
        return
    ordered = sorted(dict.fromkeys(issues))
    shown = list(ordered[:MAX_ISSUES])
    if len(ordered) > MAX_ISSUES:
        shown.append(f"/: {len(ordered) - MAX_ISSUES} additional semantic errors omitted")
    raise ProtocolError("\n".join(shown)[:MAX_ISSUE_CHARS])


def _unique(
    rows: Sequence[dict[str, Any]], key: str, label: str,
    issues: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        value = row[key]
        if value in result:
            message = f"/{label}/{index}/{key}: duplicate value {value!r}"
            if issues is None:
                raise ProtocolError(message)
            issues.append(message)
            continue
        result[value] = row
    return result


def _validate_coverage(
    coverage: Sequence[dict[str, Any]], findings: dict[str, dict[str, Any]],
    issues: list[str] | None = None,
) -> None:
    found: list[str] = []
    got = [row["id"] for row in coverage]
    if set(got) != set(CHECKLIST) or len(got) != len(set(got)):
        found.append("/coverage: every checklist id must occur exactly once")
    referenced: set[str] = set()
    for index, row in enumerate(coverage):
        links = row["finding_ids"]
        if any(fid not in findings for fid in links):
            found.append(f"/coverage/{index}/finding_ids: unknown finding id")
        if (row["status"] == "finding") != bool(links):
            found.append(
                f"/coverage/{index}: finding status and finding_ids must agree"
            )
        referenced.update(links)
    if referenced != set(findings):
        found.append("/coverage: every finding must be bound to coverage")
    if issues is None:
        _raise_semantic_issues(found)
    else:
        issues.extend(found)


def parse_lane(text: str, *, mode: str, lane: str,
               class_ids: Sequence[str] = ()) -> dict[str, Any]:
    value = decode(text, lane_schema(mode, lane), max_chars=MAX_LANE_RESPONSE_CHARS)
    issues: list[str] = []
    findings = _unique(value["findings"], "id", "findings", issues)
    _validate_coverage(value["coverage"], findings, issues)
    assessments = _unique(
        value["class_assessments"], "class_id", "class_assessments", issues,
    )
    expected = set(class_ids) if lane == "integrity" else set()
    if set(assessments) != expected:
        issues.append(
            "/class_assessments: must assess every required active class exactly once"
        )
    assessment_pointers = {
        row["class_id"]: f"/class_assessments/{index}"
        for index, row in reversed(list(enumerate(value["class_assessments"])))
    }
    for cid, row in assessments.items():
        if row["verdict"] == "violated" and row["finding_id"] not in findings:
            issues.append(
                f"{assessment_pointers[cid]}/finding_id: must name a lane finding"
            )
    _raise_semantic_issues(issues)
    return value


def decode_decision(text: str, *, mode: str, role: str) -> dict[str, Any]:
    """Decode and structurally validate a decision before semantic layers run."""
    return decode(
        text, decision_schema(mode, role), max_chars=MAX_DECISION_RESPONSE_CHARS,
    )


def _rank(severity: str) -> int:
    return {cc.OUT_OF_SCOPE: 0, cc.MINOR: 1, cc.MAJOR: 2,
            cc.BLOCKER: 3, cc.FATAL: 4}[severity]


def _fresh_debt_ids(count: int, reserved: set[str]) -> list[str]:
    result: list[str] = []
    candidate = 1
    while len(result) < count:
        value = f"D{candidate}"
        candidate += 1
        if value in reserved:
            continue
        reserved.add(value)
        result.append(value)
    return result


def class_records_from_actions(
    actions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project explicit semantic class actions to canonical register records."""
    records: list[dict[str, Any]] = []
    for action in actions:
        kind = action["kind"]
        if kind in {"close", "reopen"}:
            records.append({"op": kind, "class_id": action["class_id"]})
        elif kind == "reclassify":
            records.append({
                "op": kind, "class_id": action["class_id"],
                "severity": action["severity"],
            })
        else:
            records.append({
                "op": "replace", "class_id": action["class_id"],
                **action["definition"],
            })
    return records


def class_record_candidates(
    value: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract every schema-valid model-owned class operation before graph validation.

    This view lets the canonical engine report independent definition/cap faults even
    when another semantic relationship prevents full materialization.
    """
    records: list[dict[str, Any]] = []
    pointers: list[str] = []
    for index, finding in enumerate(value["governing_findings"]):
        classification = finding["classification"]
        if classification["kind"] != "new_class":
            continue
        records.append({"op": "new", **classification["definition"]})
        pointers.append(
            f"/governing_findings/{index}/classification/definition"
        )
    records.extend(class_records_from_actions(value["class_actions"]))
    pointers.extend(
        f"/class_actions/{index}" for index in range(len(value["class_actions"]))
    )
    return records, pointers


def materialize_decision_value(
    value: dict[str, Any], *, mode: str, role: str,
    source_ids: Sequence[str] = (), source_severities: dict[str, str] | None = None,
    assessment_verdicts: dict[str, str] | None = None,
    assessment_findings: dict[str, str | None] | None = None,
    active_classes: Sequence[dict[str, Any]] = (),
    durable_debt: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Validate a decoded semantic decision and project it to durable V1 shape."""
    issues: list[str] = []
    findings = value["governing_findings"]
    by_finding = _unique(findings, "id", "governing_findings", issues)
    if role == "final":
        _validate_coverage(value["coverage"], by_finding, issues)
    classes = {row["class_id"]: row for row in active_classes}
    if len(classes) != len(active_classes):
        issues.append("/active_classes: duplicate class_id")
    debt_by_id = {
        row["id"]: row for row in durable_debt
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    open_debt = {key: row for key, row in debt_by_id.items() if row.get("status") == "open"}
    historic_finding_ids = {
        row.get("finding_id") for row in debt_by_id.values()
        if isinstance(row.get("finding_id"), str)
    }
    reused = sorted(set(by_finding) & historic_finding_ids)
    if reused:
        issues.append(
            f"/governing_findings: new findings reuse durable identities {reused}"
        )

    source_rows: list[dict[str, Any]] = []
    governing_by_source: dict[str, list[str]] = {}
    if role == "census":
        expected_sources = set(source_ids)
        for finding_index, finding in enumerate(findings):
            finding_pointer = f"/governing_findings/{finding_index}"
            for source in finding["source_ids"]:
                if source not in expected_sources:
                    issues.append(
                        f"{finding_pointer}/source_ids: unknown source {source!r}"
                    )
                    continue
                source_rows.append({"source_id": source, "governing_id": finding["id"]})
                governing_by_source.setdefault(source, []).append(finding["id"])
                severity = (source_severities or {}).get(source)
                if severity and _rank(finding["severity"]) < _rank(severity):
                    issues.append(
                        f"{finding_pointer}/severity: cannot downgrade {source}"
                    )
        if set(governing_by_source) != expected_sources:
            missing = sorted(expected_sources - set(governing_by_source))
            issues.append(
                f"/governing_findings: every source must be mapped; missing {missing}"
            )

    class_records: list[dict[str, Any]] = []
    class_record_pointers: list[str] = []
    finding_class: dict[str, str | None] = {}
    existing_findings: dict[str, str] = {}
    for finding_index, finding in enumerate(findings):
        classification = finding["classification"]
        kind = classification["kind"]
        if kind == "one_off":
            finding_class[finding["id"]] = None
        elif kind == "new_class":
            index = len(class_records)
            class_records.append({"op": "new", **classification["definition"]})
            class_record_pointers.append(
                f"/governing_findings/{finding_index}/classification/definition"
            )
            finding_class[finding["id"]] = f"record:{index}"
        else:
            cid = classification["class_id"]
            if cid not in classes:
                issues.append(
                    f"/governing_findings/{finding_index}/classification/class_id: "
                    f"unknown active class {cid!r}"
                )
                finding_class[finding["id"]] = None
                continue
            if cid in existing_findings:
                issues.append(
                    f"/governing_findings: multiple findings classify to active class {cid!r}"
                )
            else:
                existing_findings[cid] = finding["id"]
            finding_class[finding["id"]] = cid

    debt_outcome_pointers = {
        row["debt_id"]: f"/debt_outcomes/{index}"
        for index, row in reversed(list(enumerate(value["debt_outcomes"])))
    }
    debt_outcomes = _unique(
        value["debt_outcomes"], "debt_id", "debt_outcomes", issues,
    )
    if set(debt_outcomes) != set(open_debt):
        missing = sorted(set(open_debt) - set(debt_outcomes))
        unknown = sorted(set(debt_outcomes) - set(open_debt))
        issues.append(
            f"/debt_outcomes: must update every supplied open debt exactly once; "
            f"missing={missing}, unknown={unknown}"
        )
    debt_updates = [
        {"id": row["debt_id"], **{key: item for key, item in row.items() if key != "debt_id"}}
        for row in value["debt_outcomes"]
    ]

    outcome_pointers = {
        row["class_id"]: f"/class_outcomes/{index}"
        for index, row in reversed(list(enumerate(value["class_outcomes"])))
    }
    outcomes = _unique(
        value["class_outcomes"], "class_id", "class_outcomes", issues,
    )
    expected_classes = (
        set(assessment_verdicts or {}) if role == "census"
        else set(classes) if role == "final"
        else {
            cid for debt in open_debt.values() for cid in debt.get("class_ids", [])
            if cid in classes
        } | set(existing_findings)
    )
    if set(outcomes) != expected_classes:
        issues.append(
            f"/class_outcomes: expected exactly {sorted(expected_classes)}, "
            f"got {sorted(outcomes)}"
        )

    assessment_rows: list[dict[str, Any]] = []
    materialized_assessments: list[dict[str, Any]] = []
    violated: set[str] = set()
    target_by_class: dict[str, str | None] = {}
    for cid, outcome in outcomes.items():
        outcome_pointer = outcome_pointers[cid]
        expected_verdict = (assessment_verdicts or {}).get(cid)
        if role == "census" and expected_verdict is not None and (
            outcome["verdict"] != expected_verdict
        ):
            issues.append(
                f"{outcome_pointer}/verdict: must preserve integrity-lane verdict"
            )
        target: str | None = None
        if outcome["verdict"] == "violated":
            violated.add(cid)
            basis = outcome["basis"]
            if basis["kind"] == "new_finding":
                target = basis["finding_id"]
                finding = by_finding.get(target)
                if finding is None or finding_class.get(target) != cid:
                    issues.append(
                        f"{outcome_pointer}/basis: finding must classify to this class"
                    )
                if role == "census" and finding is not None:
                    cited = (assessment_findings or {}).get(cid)
                    if cited not in finding["source_ids"]:
                        issues.append(
                            f"{outcome_pointer}/basis: must follow cited lane finding {cited!r}"
                        )
            else:
                if role == "census":
                    issues.append(
                        f"{outcome_pointer}/basis: census violations require a new finding"
                    )
                debt_id = basis["debt_id"]
                debt = open_debt.get(debt_id)
                if debt is None or cid not in debt.get("class_ids", []):
                    issues.append(
                        f"{outcome_pointer}/basis/debt_id: debt must already bind this class"
                    )
                outcome_row = debt_outcomes.get(debt_id)
                if outcome_row is not None and outcome_row["status"] != "open":
                    issues.append(
                        f"{outcome_pointer}/basis/debt_id: carried debt must remain open"
                    )
                if debt is not None:
                    target = debt["finding_id"]
        target_by_class[cid] = target
        assessment_rows.append({"assessment_id": cid, "governing_id": target})
        materialized_assessments.append({
            "class_id": cid, "verdict": outcome["verdict"],
            "evidence": list(outcome["evidence"]), "finding_id": target,
        })

    if set(existing_findings) != {
        cid for cid, target in target_by_class.items() if target in set(existing_findings.values())
    }:
        issues.append(
            "/governing_findings: every existing-class finding needs one matching violated outcome"
        )

    for source, targets in governing_by_source.items():
        if len(targets) == 1:
            continue
        cited_classes = {
            cid for cid, cited in (assessment_findings or {}).items() if cited == source
        }
        target_classes = {
            finding_class[target] for target in targets
            if isinstance(finding_class.get(target), str)
            and not str(finding_class[target]).startswith("record:")
        }
        if len(target_classes) != len(targets) or target_classes != cited_classes:
            issues.append(
                f"/governing_findings: source fan-out for {source!r} requires distinct "
                "matching violated existing classes"
            )

    for debt_id, debt in open_debt.items():
        debt_outcome = debt_outcomes.get(debt_id)
        if debt_outcome is None or debt_outcome["status"] != "open":
            continue
        bound = [item for item in debt.get("class_ids", []) if item in classes]
        if bound and not any(
            cid in outcomes and outcomes[cid]["verdict"] == "violated"
            for cid in bound
        ):
            issues.append(
                f"{debt_outcome_pointers[debt_id]}: open class-bound debt needs a violated class"
            )

    action_pointers = {
        row["class_id"]: f"/class_actions/{index}"
        for index, row in reversed(list(enumerate(value["class_actions"])))
    }
    actions = _unique(
        value["class_actions"], "class_id", "class_actions", issues,
    )
    for cid, action in actions.items():
        action_pointer = action_pointers[cid]
        if cid not in classes:
            issues.append(f"{action_pointer}/class_id: unknown active class")
            continue
        status = classes[cid]["status"]
        if (
            action["kind"] == "close" and cid in outcomes
            and outcomes[cid]["verdict"] != "satisfied"
        ):
            issues.append(f"{action_pointer}: close requires satisfied outcome")
        if action["kind"] == "reopen" and status != cc.CLOSED:
            issues.append(f"{action_pointer}: reopen requires closed class")
        if (
            action["kind"] == "reopen" and cid in outcomes
            and outcomes[cid]["verdict"] != "violated"
        ):
            issues.append(f"{action_pointer}: reopen requires violated outcome")
        if action["kind"] in {"reclassify", "replace"}:
            severity = (
                action["severity"] if action["kind"] == "reclassify"
                else action["definition"]["severity"]
            )
            if _rank(severity) < _rank(classes[cid]["severity"]):
                issues.append(f"{action_pointer}: cannot downgrade active class")
        if (
            action["kind"] == "replace" and classes[cid]["mechanized"]
            and "pattern" not in action["definition"]
        ):
            issues.append(
                f"{action_pointer}/definition: mechanized class replacement "
                "requires pattern and pathspec"
            )

    for cid, outcome in outcomes.items():
        outcome_pointer = outcome_pointers[cid]
        cls = classes.get(cid)
        if cls is None:
            continue
        action = actions.get(cid)
        if outcome["verdict"] == "satisfied" and cls["status"] in cc.UNPROVEN_STATUSES:
            if cls["mechanized"]:
                issues.append(
                    f"{outcome_pointer}: mechanized open class cannot be model-closed"
                )
            if action is None:
                actions[cid] = {"kind": "close", "class_id": cid}
            elif action["kind"] not in {"close", "reclassify", "replace"}:
                issues.append(
                    f"{action_pointers.get(cid, outcome_pointer)}: "
                    "open satisfied class must close"
                )
        if outcome["verdict"] == "violated" and cls["status"] == cc.CLOSED:
            allowed = {"replace"} if cls["mechanized"] else {"reopen", "replace"}
            if action is None or action["kind"] not in allowed:
                issues.append(
                    f"{action_pointers.get(cid, outcome_pointer)}: "
                    f"closed violated class requires {sorted(allowed)}"
                )

    _raise_semantic_issues(issues)

    class_records.extend(class_records_from_actions(list(actions.values())))
    for action in actions.values():
        class_record_pointers.append(
            action_pointers.get(
                action["class_id"], outcome_pointers.get(action["class_id"], "/class_actions"),
            )
        )

    debt_bearing = [
        finding for finding in findings
        if finding["severity"] in BLOCKING
        or (
            isinstance(finding_class.get(finding["id"]), str)
            and not str(finding_class[finding["id"]]).startswith("record:")
            and finding_class[finding["id"]] in violated
        )
    ]
    fresh_ids = _fresh_debt_ids(len(debt_bearing), set(debt_by_id))
    fresh_debt: list[dict[str, Any]] = []
    for debt_id, finding in zip(fresh_ids, debt_bearing, strict=True):
        fresh_debt.append({
            "id": debt_id, "finding_id": finding["id"], "status": "open",
            "severity": finding["severity"], "summary": finding["summary"],
            "evidence": list(finding["evidence"]), "remedy": finding["remedy"],
        })

    result: dict[str, Any] = {
        "role": role,
        "source_dispositions": source_rows,
        "assessment_dispositions": assessment_rows,
        "findings": [
            {key: finding[key] for key in ("id", "severity", "summary", "evidence", "remedy")}
            for finding in findings
        ],
        "debt": fresh_debt,
        "debt_updates": debt_updates,
        "class_dispositions": [
            (
                {"finding_id": finding["id"], **finding["classification"]}
                if finding["classification"]["kind"] != "new_class"
                else {
                    "finding_id": finding["id"], "kind": "new_class",
                    "record_index": int(str(finding_class[finding["id"]]).split(":", 1)[1]),
                }
            )
            for finding in findings
        ],
        "class_records": class_records,
        "class_assessments": materialized_assessments,
        "_finding_class_refs": finding_class,
        "_class_record_pointers": class_record_pointers,
    }
    if role == "final":
        result["coverage"] = value["coverage"]
    return result


def materialize_decision(
    text: str, *, mode: str, role: str,
    source_ids: Sequence[str] = (), source_severities: dict[str, str] | None = None,
    assessment_verdicts: dict[str, str] | None = None,
    assessment_findings: dict[str, str | None] | None = None,
    active_classes: Sequence[dict[str, Any]] = (),
    durable_debt: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Decode one semantic decision and project it to the durable V1 shape."""
    value = decode_decision(text, mode=mode, role=role)
    return materialize_decision_value(
        value, mode=mode, role=role, source_ids=source_ids,
        source_severities=source_severities,
        assessment_verdicts=assessment_verdicts,
        assessment_findings=assessment_findings,
        active_classes=active_classes, durable_debt=durable_debt,
    )
