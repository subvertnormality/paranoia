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
        "pattern": r"^[^\r\n]+$",
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
            _string(240), maximum=100, minimum=1, unique=True,
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
        **common, "pattern": _string(2_000), "pathspec": _string(1_000),
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
        "findings": _array(_lane_finding(), maximum=100),
        "class_assessments": _array(_lane_assessment(), maximum=100),
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
            maximum=100,
        ),
        "debt_outcomes": _array(_debt_outcome(), maximum=500),
        "class_outcomes": _array(_class_outcome(), maximum=100),
        "class_actions": _array(_class_action(mode), maximum=100),
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


def decode(text: str, schema: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"/: invalid JSON at line {exc.lineno} column {exc.colno}") from exc
    issues = _schema_issues(value, schema)
    if issues:
        message = "\n".join(issues)
        raise ProtocolError(message[:MAX_ISSUE_CHARS])
    assert isinstance(value, dict)
    return value


def _unique(rows: Sequence[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise ProtocolError(f"/{label}: duplicate {key} {value!r}")
        result[value] = row
    return result


def _validate_coverage(
    coverage: Sequence[dict[str, Any]], findings: dict[str, dict[str, Any]],
) -> None:
    got = [row["id"] for row in coverage]
    if set(got) != set(CHECKLIST) or len(got) != len(set(got)):
        raise ProtocolError("/coverage: every checklist id must occur exactly once")
    referenced: set[str] = set()
    for index, row in enumerate(coverage):
        links = row["finding_ids"]
        if any(fid not in findings for fid in links):
            raise ProtocolError(f"/coverage/{index}/finding_ids: unknown finding id")
        if (row["status"] == "finding") != bool(links):
            raise ProtocolError(
                f"/coverage/{index}: finding status and finding_ids must agree"
            )
        referenced.update(links)
    if referenced != set(findings):
        raise ProtocolError("/coverage: every finding must be bound to coverage")


def parse_lane(text: str, *, mode: str, lane: str,
               class_ids: Sequence[str] = ()) -> dict[str, Any]:
    value = decode(text, lane_schema(mode, lane))
    findings = _unique(value["findings"], "id", "findings")
    _validate_coverage(value["coverage"], findings)
    assessments = _unique(value["class_assessments"], "class_id", "class_assessments")
    expected = set(class_ids) if lane == "integrity" else set()
    if set(assessments) != expected:
        raise ProtocolError(
            "/class_assessments: must assess every required active class exactly once"
        )
    for cid, row in assessments.items():
        if row["verdict"] == "violated" and row["finding_id"] not in findings:
            raise ProtocolError(
                f"/class_assessments/{cid}/finding_id: must name a lane finding"
            )
    return value


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


def materialize_decision(
    text: str, *, mode: str, role: str,
    source_ids: Sequence[str] = (), source_severities: dict[str, str] | None = None,
    assessment_verdicts: dict[str, str] | None = None,
    assessment_findings: dict[str, str | None] | None = None,
    active_classes: Sequence[dict[str, Any]] = (),
    durable_debt: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Validate one semantic decision and project it to the durable V1 shape."""

    value = decode(text, decision_schema(mode, role))
    findings = value["governing_findings"]
    by_finding = _unique(findings, "id", "governing_findings")
    if role == "final":
        _validate_coverage(value["coverage"], by_finding)
    classes = {row["class_id"]: row for row in active_classes}
    if len(classes) != len(active_classes):
        raise ProtocolError("/active_classes: duplicate class_id")
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
        raise ProtocolError(
            f"/governing_findings: new findings reuse durable identities {reused}"
        )

    source_rows: list[dict[str, Any]] = []
    governing_by_source: dict[str, list[str]] = {}
    if role == "census":
        expected_sources = set(source_ids)
        for finding in findings:
            for source in finding["source_ids"]:
                if source not in expected_sources:
                    raise ProtocolError(
                        f"/governing_findings/{finding['id']}/source_ids: unknown source {source!r}"
                    )
                source_rows.append({"source_id": source, "governing_id": finding["id"]})
                governing_by_source.setdefault(source, []).append(finding["id"])
                severity = (source_severities or {}).get(source)
                if severity and _rank(finding["severity"]) < _rank(severity):
                    raise ProtocolError(
                        f"/governing_findings/{finding['id']}/severity: cannot downgrade {source}"
                    )
        if set(governing_by_source) != expected_sources:
            missing = sorted(expected_sources - set(governing_by_source))
            raise ProtocolError(
                f"/governing_findings: every source must be mapped; missing {missing}"
            )

    class_records: list[dict[str, Any]] = []
    finding_class: dict[str, str | None] = {}
    existing_findings: dict[str, str] = {}
    for finding in findings:
        classification = finding["classification"]
        kind = classification["kind"]
        if kind == "one_off":
            finding_class[finding["id"]] = None
        elif kind == "new_class":
            index = len(class_records)
            class_records.append({"op": "new", **classification["definition"]})
            finding_class[finding["id"]] = f"record:{index}"
        else:
            cid = classification["class_id"]
            if cid not in classes:
                raise ProtocolError(
                    f"/governing_findings/{finding['id']}/classification/class_id: "
                    f"unknown active class {cid!r}"
                )
            if cid in existing_findings:
                raise ProtocolError(
                    f"/governing_findings: multiple findings classify to active class {cid!r}"
                )
            existing_findings[cid] = finding["id"]
            finding_class[finding["id"]] = cid

    debt_outcomes = _unique(value["debt_outcomes"], "debt_id", "debt_outcomes")
    if set(debt_outcomes) != set(open_debt):
        missing = sorted(set(open_debt) - set(debt_outcomes))
        unknown = sorted(set(debt_outcomes) - set(open_debt))
        raise ProtocolError(
            f"/debt_outcomes: must update every supplied open debt exactly once; "
            f"missing={missing}, unknown={unknown}"
        )
    debt_updates = [
        {"id": row["debt_id"], **{key: item for key, item in row.items() if key != "debt_id"}}
        for row in value["debt_outcomes"]
    ]

    outcomes = _unique(value["class_outcomes"], "class_id", "class_outcomes")
    expected_classes = (
        set(assessment_verdicts or {}) if role == "census"
        else set(classes) if role == "final"
        else {
            cid for debt in open_debt.values() for cid in debt.get("class_ids", [])
            if cid in classes
        } | set(existing_findings)
    )
    if set(outcomes) != expected_classes:
        raise ProtocolError(
            f"/class_outcomes: expected exactly {sorted(expected_classes)}, "
            f"got {sorted(outcomes)}"
        )

    assessment_rows: list[dict[str, Any]] = []
    materialized_assessments: list[dict[str, Any]] = []
    violated: set[str] = set()
    target_by_class: dict[str, str | None] = {}
    for cid, outcome in outcomes.items():
        if role == "census" and outcome["verdict"] != (assessment_verdicts or {})[cid]:
            raise ProtocolError(
                f"/class_outcomes/{cid}/verdict: must preserve integrity-lane verdict"
            )
        target: str | None = None
        if outcome["verdict"] == "violated":
            violated.add(cid)
            basis = outcome["basis"]
            if basis["kind"] == "new_finding":
                target = basis["finding_id"]
                finding = by_finding.get(target)
                if finding is None or finding_class.get(target) != cid:
                    raise ProtocolError(
                        f"/class_outcomes/{cid}/basis: finding must classify to this class"
                    )
                if role == "census":
                    cited = (assessment_findings or {}).get(cid)
                    if cited not in finding["source_ids"]:
                        raise ProtocolError(
                            f"/class_outcomes/{cid}/basis: must follow cited lane finding {cited!r}"
                        )
            else:
                if role == "census":
                    raise ProtocolError(
                        f"/class_outcomes/{cid}/basis: census violations require a new finding"
                    )
                debt_id = basis["debt_id"]
                debt = open_debt.get(debt_id)
                if debt is None or cid not in debt.get("class_ids", []):
                    raise ProtocolError(
                        f"/class_outcomes/{cid}/basis/debt_id: debt must already bind this class"
                    )
                if debt_outcomes[debt_id]["status"] != "open":
                    raise ProtocolError(
                        f"/class_outcomes/{cid}/basis/debt_id: carried debt must remain open"
                    )
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
        raise ProtocolError(
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
            raise ProtocolError(
                f"/governing_findings: source fan-out for {source!r} requires distinct "
                "matching violated existing classes"
            )

    for debt_id, debt in open_debt.items():
        if debt_outcomes[debt_id]["status"] != "open":
            continue
        bound = [item for item in debt.get("class_ids", []) if item in classes]
        if bound and not any(
            cid in outcomes and outcomes[cid]["verdict"] == "violated"
            for cid in bound
        ):
            raise ProtocolError(
                f"/debt_outcomes/{debt_id}: open class-bound debt needs a violated class"
            )

    actions = _unique(value["class_actions"], "class_id", "class_actions")
    for cid, action in actions.items():
        if cid not in classes:
            raise ProtocolError(f"/class_actions/{cid}: unknown active class")
        status = classes[cid]["status"]
        if action["kind"] == "close" and (
            cid not in outcomes or outcomes[cid]["verdict"] != "satisfied"
        ):
            raise ProtocolError(f"/class_actions/{cid}: close requires satisfied outcome")
        if action["kind"] == "reopen" and status != cc.CLOSED:
            raise ProtocolError(f"/class_actions/{cid}: reopen requires closed class")
        if action["kind"] == "reopen" and (
            cid not in outcomes or outcomes[cid]["verdict"] != "violated"
        ):
            raise ProtocolError(f"/class_actions/{cid}: reopen requires violated outcome")
        if action["kind"] in {"reclassify", "replace"}:
            severity = (
                action["severity"] if action["kind"] == "reclassify"
                else action["definition"]["severity"]
            )
            if _rank(severity) < _rank(classes[cid]["severity"]):
                raise ProtocolError(f"/class_actions/{cid}: cannot downgrade active class")

    for cid, outcome in outcomes.items():
        cls = classes[cid]
        action = actions.get(cid)
        if outcome["verdict"] == "satisfied" and cls["status"] in cc.UNPROVEN_STATUSES:
            if cls["mechanized"]:
                raise ProtocolError(
                    f"/class_outcomes/{cid}: mechanized open class cannot be model-closed"
                )
            if action is None:
                actions[cid] = {"kind": "close", "class_id": cid}
            elif action["kind"] != "close":
                raise ProtocolError(
                    f"/class_actions/{cid}: open satisfied class must close"
                )
        if outcome["verdict"] == "violated" and cls["status"] == cc.CLOSED:
            allowed = {"replace"} if cls["mechanized"] else {"reopen", "replace"}
            if action is None or action["kind"] not in allowed:
                raise ProtocolError(
                    f"/class_actions/{cid}: closed violated class requires {sorted(allowed)}"
                )

    for action in actions.values():
        kind = action["kind"]
        if kind in {"close", "reopen"}:
            class_records.append({"op": kind, "class_id": action["class_id"]})
        elif kind == "reclassify":
            class_records.append({
                "op": kind, "class_id": action["class_id"],
                "severity": action["severity"],
            })
        else:
            class_records.append({
                "op": "replace", "class_id": action["class_id"],
                **action["definition"],
            })

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
    }
    if role == "final":
        result["coverage"] = value["coverage"]
    return result
