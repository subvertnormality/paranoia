"""Executable model contract for staged structural review.

Provider structured output and local validation use the same closed, role-specific
schemas.  The model supplies semantic decisions once; this module validates their
graph and materializes the existing durable settlement shape.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
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
MAX_RATIONALE_CHARS = 500
MAX_ISSUES = 24
MAX_ISSUE_CHARS = 8_000
MAX_LANE_FINDINGS = 100
MAX_ACTIVE_CLASSES = cc.MAX_ACTIVE_CLASSES
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


def citation_instructions(mode: str, *, plan_contract: bool = False) -> str:
    """Return the shared model-facing evidence object contract."""
    if mode == cc.PLAN_MODE:
        alternatives = (
            '`plan:<line-or-range>` or `repository/<path>:<line-or-range>`'
        )
    elif mode == cc.BRANCH_MODE:
        alternatives = (
            '`plan:<line-or-range>` or `repository/<path>:<line-or-range>`'
            if plan_contract else '`repository/<path>:<line-or-range>`'
        )
    else:
        raise ValueError(f"invalid staged mode {mode!r}")
    return (
        "Every evidence array item is exactly a closed "
        '`{"anchor":"<citation>","rationale":"why these lines support this row"}` '
        f"object, where `<citation>` is {alternatives}. Put only the bare citation "
        "in `anchor`; put all explanation in `rationale`; and use one object per "
        "citation, never join citations."
    )


def class_decision_instructions(
    mode: str, role: str, *, active_classes: Sequence[dict[str, Any]],
    outcome_class_ids: Sequence[str] = (),
    correction_gates: Sequence[dict[str, Any]] = (),
    prior_concessions: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Render the keyed surface and canonical action rules beside the schema."""
    if mode not in {cc.PLAN_MODE, cc.BRANCH_MODE}:
        raise ValueError(f"invalid staged mode {mode!r}")
    outcome_ids = set(outcome_class_ids)
    gated_ids = {
        row.get("class_id") for row in correction_gates
        if isinstance(row, dict) and isinstance(row.get("class_id"), str)
    }
    actions: dict[str, dict[str, Any]] = {}
    for cls in active_classes:
        class_id = cls["class_id"]
        severity = cls["severity"]
        lifecycle: list[str] = []
        if not cls.get("mechanized", False):
            lifecycle = ["close"]
            if cls.get("status") == cc.CLOSED:
                lifecycle.append("reopen")
        actions[class_id] = {
            "status":cls.get("status"),
            "severity":severity,
            "mechanized":bool(cls.get("mechanized", False)),
            "required_outcome":class_id in outcome_ids,
            "lifecycle":lifecycle,
            "reclassify_severities":list(cc.SEVERITIES[:cc.SEVERITIES.index(severity) + 1]),
            "replacement_forms":(
                ["mechanized-pattern"] if cls.get("mechanized", False)
                else ["procedure"] if mode == cc.PLAN_MODE
                else ["procedure", "mechanized-pattern"]
            ),
        }
    authority = {
        "census":"server derives outcomes from integrity assessments",
        "correction":(
            "author outcomes for debt-bound classes; a fresh finding for a debt-bound "
            "class uses its exact new_finding basis, while a distinct non-debt-bound "
            "fresh finding supplies assessment_evidence and the server derives violation"
        ),
        "final":"author one outcome for every active class",
    }[role]
    gate_guidance = ""
    if role == "correction" and gated_ids:
        gate_guidance = (
            " Correction-gated class IDs are exactly: "
            f"{json.dumps(sorted(gated_ids), ensure_ascii=False, separators=(',', ':'))}. "
            "Each listed class must become nonblocking: a violated gated class needs a "
            "valid replacement, while satisfied open unmechanized state closes by "
            "derivation; retaining a blocking severity does not satisfy the gate."
        )
    concession_ids = list((prior_concessions or {}).keys())
    concession_guidance = (
        " concession_challenges is a closed object keyed by exactly these durable "
        f"concession class IDs: {json.dumps(concession_ids, ensure_ascii=False)}. "
        "Every key is required. Use null unless this response newly targets that class "
        "with an existing-class finding, reopen, or replacement. A targeted class must "
        "instead supply the exact projected debt_id plus a bounded reason and new "
        "repository/plan evidence that contradicts or invalidates the concession."
    )
    permitted_outcome_ids = (
        [row["class_id"] for row in active_classes]
        if role == "correction" else list(outcome_class_ids)
    )
    return (
        "class_outcomes is a closed object permitting exactly these class IDs: "
        f"{json.dumps(permitted_outcome_ids, ensure_ascii=False)}. Every permitted key is "
        "required by the provider schema; use null for a semantically optional outcome "
        "that you are not authoring. Non-null outcomes are required exactly for these "
        f"class IDs: {json.dumps(list(outcome_class_ids), ensure_ascii=False)}. "
        "class_actions is a closed object with one independent-action slot per active "
        "class. Every listed key is required; use null when no "
        "independent action is needed. The exact current decision surface is: "
        f"{json.dumps(actions, ensure_ascii=False, separators=(',', ':'))}. "
        f"Outcome authority for this role: {authority}. "
        "Every close requires an authored satisfied outcome with evidence. When an authoritative "
        "outcome exists, reopen requires violated; other outcome-free standalone lifecycle "
        "actions remain legal only as listed. "
        "Reclassify and replace may retain or strengthen severity but never downgrade. "
        "Replacement preserves a mechanized class; use only a listed replacement form. "
        f"{gate_guidance}{concession_guidance} Never put class_id inside "
        "an outcome or action value."
    )


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


def _object(
    properties: dict[str, Any], *, required: Sequence[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "properties": properties,
        "required": list(properties) if required is None else list(required),
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


def _citation() -> dict[str, Any]:
    return _object({
        "anchor": _anchor(),
        "rationale": _string(MAX_RATIONALE_CHARS),
    })


def _evidence(*, canonical: bool = False) -> dict[str, Any]:
    # Wire uniqueness is intentionally deferred: identical objects must reach
    # canonical validation so duplicate anchors can join the aggregate retry
    # diagnostic. Canonical anchor strings remain unique and load-bearing.
    return _array(
        _anchor() if canonical else _citation(),
        maximum=100, minimum=1, unique=canonical,
    )


def _coverage(*, canonical: bool = False) -> dict[str, Any]:
    return _object({
        "id": _string(80, enum=CHECKLIST),
        "status": _string(32, enum=("covered", "finding", "not_applicable")),
        "summary": _string(MAX_SUMMARY_CHARS),
        "evidence": _evidence(canonical=canonical),
        "finding_ids": _array(_string(120), maximum=100, unique=True),
    })


def _finding(
    *, mode: str, role: str,
    active_classes: Sequence[dict[str, Any]] | None = None,
    outcome_class_ids: Sequence[str] = (), canonical: bool = False,
) -> dict[str, Any]:
    properties = {
        "id": _string(120),
        "severity": _string(32, enum=cc.SEVERITIES),
        "summary": _string(MAX_SUMMARY_CHARS),
        "evidence": _evidence(canonical=canonical),
        "remedy": _string(MAX_SUMMARY_CHARS),
    }
    if role == "census":
        properties["source_ids"] = _array(
            _string(240), maximum=MAX_CENSUS_SOURCES, minimum=1, unique=True,
        )
    properties["classification"] = _classification(
        mode, role=role, active_classes=active_classes,
        outcome_class_ids=outcome_class_ids, canonical=canonical,
    )
    return _object(properties)


def _lane_finding(*, canonical: bool = False) -> dict[str, Any]:
    return _object({
        "id": _string(120),
        "severity": _string(32, enum=cc.SEVERITIES),
        "summary": _string(MAX_SUMMARY_CHARS),
        "evidence": _evidence(canonical=canonical),
        "remedy": _string(MAX_SUMMARY_CHARS),
    })


def _definition(mode: str, *, mechanized: bool | None = None) -> dict[str, Any]:
    common = {
        "invariant": _string(1_000),
        "severity": _string(32, enum=cc.SEVERITIES),
    }
    procedure = _object({**common, "procedure": _string(2_000)})
    if mode == cc.PLAN_MODE or mechanized is False:
        return procedure
    pattern = _object({
        **common, "pattern": _string(2_000), "pathspec": _pathspec(),
    })
    return pattern if mechanized is True else {"anyOf": [procedure, pattern]}


def _classification(
    mode: str = cc.PLAN_MODE, *, role: str | None = None,
    active_classes: Sequence[dict[str, Any]] | None = None,
    outcome_class_ids: Sequence[str] = (), canonical: bool = False,
) -> dict[str, Any]:
    alternatives = [
        _object({
            "kind": _string(32, const="one_off"),
            "reason": _string(MAX_SUMMARY_CHARS),
        }),
        _object({
            "kind": _string(32, const="new_class"),
            "definition": _definition(mode),
        }),
    ]
    outcome_ids = set(outcome_class_ids)
    if active_classes is not None:
        grouped: list[tuple[list[str], bool]] = []
        active_ids = [cls["class_id"] for cls in active_classes]
        if role == "correction":
            grouped.extend((
                ([cid for cid in active_ids if cid in outcome_ids], False),
                ([cid for cid in active_ids if cid not in outcome_ids], True),
            ))
        else:
            grouped.append((active_ids, False))
        for class_ids, needs_assessment in grouped:
            if not class_ids:
                continue
            properties = {
                "kind": _string(32, const="existing_class"),
                "class_id": _string(120, enum=class_ids),
            }
            if needs_assessment:
                properties["assessment_evidence"] = _evidence(canonical=canonical)
            alternatives.append(_object(properties))
    else:
        alternatives.append(_object({
            "kind": _string(32, const="existing_class"),
            "class_id": _string(120),
        }))
    return {"anyOf": alternatives}


def _lane_assessment(*, canonical: bool = False) -> dict[str, Any]:
    return {"anyOf": [
        _object({
            "class_id": _string(120),
            "verdict": _string(32, const="satisfied"),
            "evidence": _evidence(canonical=canonical),
            "finding_id": {"type": "null"},
        }),
        _object({
            "class_id": _string(120),
            "verdict": _string(32, const="violated"),
            "evidence": _evidence(canonical=canonical),
            "finding_id": _string(120),
        }),
    ]}


def _class_outcome(*, canonical: bool = False) -> dict[str, Any]:
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
            "evidence": _evidence(canonical=canonical),
        }),
        _object({
            "class_id": _string(120),
            "verdict": _string(32, const="violated"),
            "evidence": _evidence(canonical=canonical),
            "basis": basis,
        }),
    ]}


def _class_outcome_body(*, canonical: bool = False) -> dict[str, Any]:
    value = deepcopy(_class_outcome(canonical=canonical))
    for alternative in value["anyOf"]:
        alternative["properties"].pop("class_id")
        alternative["required"].remove("class_id")
    return value


def _debt_outcome(*, canonical: bool = False) -> dict[str, Any]:
    return {"anyOf": [
        _object({
            "debt_id": _string(120),
            "status": _string(16, const="closed"),
            "evidence": _evidence(canonical=canonical),
        }),
        _object({
            "debt_id": _string(120),
            "status": _string(16, const="open"),
            "evidence": _evidence(canonical=canonical),
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


def _class_action_body(mode: str, cls: dict[str, Any]) -> dict[str, Any]:
    alternatives: list[dict[str, Any]] = []
    if not cls.get("mechanized", False):
        alternatives.extend([
            _object({"kind": _string(32, const="close")}),
            _object({"kind": _string(32, const="reopen")}),
        ])
    alternatives.extend([
        _object({
            "kind": _string(32, const="reclassify"),
            "severity": _string(32, enum=cc.SEVERITIES),
        }),
        _object({
            "kind": _string(32, const="replace"),
            "definition": _definition(
                mode, mechanized=True if cls.get("mechanized", False) else None,
            ),
        }),
    ])
    return {"anyOf": alternatives}


def _concession_challenge(*, debt_id: str, canonical: bool = False) -> dict[str, Any]:
    evidence = _array(
        _anchor() if canonical else _citation(),
        maximum=20, minimum=1, unique=canonical,
    )
    return {"anyOf":[
        {"type":"null"},
        _object({
            "debt_id": _string(120, const=debt_id),
            "reason": _string(4_000),
            "evidence": evidence,
        }),
    ]}


def _canonical_concession_challenge() -> dict[str, Any]:
    return _object({
        "class_id": _string(120),
        "challenge": {"anyOf":[
            {"type":"null"},
            _object({
                "debt_id": _string(120),
                "reason": _string(4_000),
                "evidence": _array(
                    _anchor(), maximum=20, minimum=1, unique=True,
                ),
            }),
        ]},
    })


def lane_schema(mode: str, lane: str, *, canonical: bool = False) -> dict[str, Any]:
    if lane not in LANES.get(mode, ()):
        raise ValueError(f"invalid staged lane {lane!r} for {mode!r}")
    return _root(_object({
        "lane": _string(32, const=lane),
        "coverage": _array(
            _coverage(canonical=canonical),
            maximum=len(CHECKLIST), minimum=len(CHECKLIST),
        ),
        "findings": _array(
            _lane_finding(canonical=canonical), maximum=MAX_LANE_FINDINGS,
        ),
        "class_assessments": _array(
            _lane_assessment(canonical=canonical), maximum=MAX_ACTIVE_CLASSES,
        ),
    }))


def decision_schema(
    mode: str, role: str, *, canonical: bool = False,
    active_classes: Sequence[dict[str, Any]] | None = None,
    outcome_class_ids: Sequence[str] = (),
    prior_concessions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if mode not in LANES:
        raise ValueError(f"invalid staged mode {mode!r}")
    if role not in {"census", "correction", "final"}:
        raise ValueError(f"invalid staged role {role!r}")
    properties = {
        "role": _string(32, const=role),
        "governing_findings": _array(
            _finding(
                mode=mode, role=role, active_classes=active_classes,
                outcome_class_ids=outcome_class_ids, canonical=canonical,
            ),
            maximum=MAX_CENSUS_FINDINGS if role == "census" else MAX_LANE_FINDINGS,
        ),
        "debt_outcomes": _array(
            _debt_outcome(canonical=canonical), maximum=500,
        ),
    }
    definitions: dict[str, Any] = {}
    concessions = prior_concessions or {}
    if canonical:
        properties["concession_challenges"] = _array(
            _canonical_concession_challenge(), maximum=MAX_ACTIVE_CLASSES,
        )
    else:
        properties["concession_challenges"] = _object({
            cid:_concession_challenge(debt_id=row["debt_id"])
            for cid, row in concessions.items()
        })
    if role != "census":
        if canonical:
            properties["class_outcomes"] = _array(
                _class_outcome(canonical=True), maximum=MAX_ACTIVE_CLASSES,
            )
        else:
            outcome_ids = list(outcome_class_ids)
            permitted_outcome_ids = list(dict.fromkeys([
                *outcome_ids,
                *(
                    cls["class_id"] for cls in (active_classes or ())
                    if role == "correction"
                ),
            ]))
            definitions["class_outcome"] = _class_outcome_body()
            properties["class_outcomes"] = _object(
                {
                    cid:(
                        {"$ref":"#/$defs/class_outcome"}
                        if cid in outcome_ids
                        else {"anyOf":[
                            {"type":"null"},
                            {"$ref":"#/$defs/class_outcome"},
                        ]}
                    )
                    for cid in permitted_outcome_ids
                },
                required=outcome_ids,
            )
    if canonical:
        properties["class_actions"] = _array(
            _class_action(mode), maximum=MAX_ACTIVE_CLASSES,
        )
    else:
        if active_classes:
            definitions["manual_class_action"] = {"anyOf":[
                {"type":"null"},
                _class_action_body(mode, {"mechanized":False}),
            ]}
            definitions["mechanized_class_action"] = {"anyOf":[
                {"type":"null"},
                _class_action_body(mode, {"mechanized":True}),
            ]}
        properties["class_actions"] = _object(
            {
                cls["class_id"]:{
                    "$ref":(
                        "#/$defs/mechanized_class_action"
                        if cls.get("mechanized", False)
                        else "#/$defs/manual_class_action"
                    ),
                }
                for cls in (active_classes or ())
            },
        )
    if role == "final":
        properties["coverage"] = _array(
            _coverage(canonical=canonical),
            maximum=len(CHECKLIST), minimum=len(CHECKLIST),
        )
    schema = _root(_object(properties))
    if definitions:
        schema["$defs"] = definitions
    return schema


def canonical_schema(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def provider_schema(schema: Any) -> Any:
    """Remove provider-unsupported metadata/uniqueness from the full local contract.

    Both vendors receive this projection; complete local validation still makes
    duplicates fail closed through the same-session correction path.
    """

    if isinstance(schema, dict):
        projected = {
            key: provider_schema(value)
            for key, value in schema.items() if key not in {"uniqueItems", "$schema"}
        }
        properties = projected.get("properties")
        if projected.get("type") == "object" and isinstance(properties, dict):
            projected["required"] = list(properties)
        return projected
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


class _ObjectPairs(list[tuple[str, Any]]):
    """Distinguish JSON objects from arrays until duplicate keys are checked."""


def _pairs_to_value(
    value: Any, parts: tuple[Any, ...] = (),
) -> tuple[Any, list[str]]:
    issues: list[str] = []
    if isinstance(value, _ObjectPairs):
        result: dict[str, Any] = {}
        for key, child in value:
            if key in result:
                issues.append(f"{_pointer((*parts, key))}: duplicate JSON object key")
                continue
            converted, child_issues = _pairs_to_value(child, (*parts, key))
            result[key] = converted
            issues.extend(child_issues)
        return result, issues
    if isinstance(value, list):
        result_list: list[Any] = []
        for index, child in enumerate(value):
            converted, child_issues = _pairs_to_value(child, (*parts, index))
            result_list.append(converted)
            issues.extend(child_issues)
        return result_list, issues
    return value, issues


def decode(text: str, schema: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    if len(text) > max_chars:
        raise ProtocolError(
            f"/: response is {len(text)} characters; maximum is {max_chars}"
        )
    try:
        pairs = json.loads(text, object_pairs_hook=_ObjectPairs)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"/: invalid JSON at line {exc.lineno} column {exc.colno}") from exc
    value, duplicate_issues = _pairs_to_value(pairs)
    if duplicate_issues:
        _raise_semantic_issues(duplicate_issues)
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


def project_citations(value: dict[str, Any]) -> dict[str, Any]:
    """Project a wire-valid response to exact canonical anchor strings."""
    projected = deepcopy(value)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key in {"evidence", "assessment_evidence"}:
                    node[key] = [citation["anchor"] for citation in child]
                else:
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(projected)
    return projected


def expected_outcome_class_ids(
    role: str, *, active_classes: Sequence[dict[str, Any]] = (),
    durable_debt: Sequence[dict[str, Any]] = (),
) -> list[str]:
    """Return model-owned outcome keys in stable active-class order."""
    if role == "census":
        return []
    active_ids = [row["class_id"] for row in active_classes]
    if role == "final":
        return active_ids
    bound = {
        cid
        for debt in durable_debt
        if debt.get("status") == "open"
        for cid in debt.get("class_ids", [])
    }
    return [cid for cid in active_ids if cid in bound]


def project_decision_wire(value: dict[str, Any]) -> dict[str, Any]:
    """Project keyed fresh decision maps to the canonical array representation."""
    projected = project_citations(value)
    for label in ("class_outcomes", "class_actions"):
        rows = projected.get(label)
        if not isinstance(rows, dict):
            continue
        projected[label] = [
            {"class_id": class_id, **body}
            for class_id, body in rows.items()
            if body is not None
        ]
    challenges = projected.get("concession_challenges")
    if isinstance(challenges, dict):
        projected["concession_challenges"] = [
            {"class_id":class_id, "challenge":body}
            for class_id, body in challenges.items()
        ]
    return projected


def _pointer_token(value: str) -> str:
    """Escape one object key for use as an RFC 6901 JSON Pointer token."""
    return value.replace("~", "~0").replace("/", "~1")


def _wire_class_pointers(value: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Retain provider-facing keyed locations across canonical projection."""
    result: dict[str, dict[str, str]] = {}
    for label in ("class_outcomes", "class_actions", "concession_challenges"):
        rows = value.get(label)
        if isinstance(rows, dict):
            result[label] = {
                class_id: f"/{label}/{_pointer_token(class_id)}"
                for class_id in rows
            }
    return result


def _class_row_pointers(
    value: dict[str, Any], label: str,
) -> dict[str, str]:
    """Return provider keyed pointers, falling back only for canonical callers."""
    keyed = value.get("_wire_class_pointers", {}).get(label, {})
    return {
        row["class_id"]: keyed.get(row["class_id"], f"/{label}/{index}")
        for index, row in reversed(list(enumerate(value.get(label, []))))
    }


def _class_slot_pointer(value: dict[str, Any], label: str, class_id: str) -> str:
    """Locate a required keyed slot even when its canonical projection is absent."""
    keyed = value.get("_wire_class_pointers", {}).get(label, {})
    return keyed.get(class_id, f"/{label}")


def _remap_class_schema_issues(
    value: dict[str, Any], issues: Sequence[str],
) -> list[str]:
    """Translate canonical array-row issues back to fresh provider wire keys."""
    replacements: list[tuple[str, str]] = []
    for label in ("class_outcomes", "class_actions", "concession_challenges"):
        keyed = value.get("_wire_class_pointers", {}).get(label, {})
        for index, row in enumerate(value.get(label, [])):
            pointer = keyed.get(row["class_id"])
            if pointer is not None:
                replacements.append((f"/{label}/{index}", pointer))
    remapped: list[str] = []
    for issue in issues:
        for canonical, wire in replacements:
            if issue == canonical or issue.startswith((canonical + "/", canonical + ":")):
                issue = wire + issue[len(canonical):]
                break
        remapped.append(issue)
    return remapped


def _canonical_class_projection_issues(value: dict[str, Any]) -> list[str]:
    """Name lossy wire-to-canonical citation collisions at their keyed slot."""
    pointers = _class_row_pointers(value, "class_outcomes")
    issues: list[str] = []
    for row in value.get("class_outcomes", []):
        evidence = row.get("evidence", [])
        if len(evidence) != len(set(evidence)):
            issues.append(
                f"{pointers[row['class_id']]}/evidence: projected anchors must be unique"
            )
    return issues


def decode_lane_with_issues(
    text: str, *, mode: str, lane: str,
) -> tuple[dict[str, Any], list[str]]:
    """Decode the closed wire shape and retain canonical issues for fan-in."""
    wire = decode(text, lane_schema(mode, lane), max_chars=MAX_LANE_RESPONSE_CHARS)
    canonical = project_citations(wire)
    return canonical, _schema_issues(
        canonical, lane_schema(mode, lane, canonical=True),
    )


def decode_lane(text: str, *, mode: str, lane: str) -> dict[str, Any]:
    """Decode a lane response before independent semantic/anchor validation."""
    value, issues = decode_lane_with_issues(text, mode=mode, lane=lane)
    _raise_semantic_issues(issues)
    return value


def decode_canonical_lane(text: str, *, mode: str, lane: str) -> dict[str, Any]:
    """Validate a server-owned canonical lane manifest, never a provider reply."""
    return decode(
        text, lane_schema(mode, lane, canonical=True),
        max_chars=MAX_LANE_RESPONSE_CHARS,
    )


def validate_lane_value(value: dict[str, Any], *, lane: str,
                        class_ids: Sequence[str] = (),
                        active_classes: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    """Validate lane-owned relationships on an already schema-valid object."""
    issues: list[str] = []
    findings = _unique(value["findings"], "id", "findings", issues)
    _validate_coverage(value["coverage"], findings, issues)
    assessments = _unique(
        value["class_assessments"], "class_id", "class_assessments", issues,
    )
    classes = {row["class_id"]: row for row in active_classes}
    if len(classes) != len(active_classes):
        issues.append("/class_assessments: active class metadata has duplicate class_id")
    expected = (
        set(classes) if active_classes else set(class_ids)
    ) if lane == "integrity" else set()
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
        cls = classes.get(cid)
        if (
            row["verdict"] == "satisfied" and cls is not None
            and cls.get("mechanized") is True
            and cls.get("status") in cc.UNPROVEN_STATUSES
        ):
            issues.append(
                f"{assessment_pointers[cid]}/verdict: satisfied cannot close an "
                "unproven mechanized class"
            )
    _raise_semantic_issues(issues)
    return value


def parse_lane(text: str, *, mode: str, lane: str,
               class_ids: Sequence[str] = (),
               active_classes: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    value = decode_lane(text, mode=mode, lane=lane)
    return validate_lane_value(
        value, lane=lane, class_ids=class_ids, active_classes=active_classes,
    )


def decode_decision_with_issues(
    text: str, *, mode: str, role: str,
    active_classes: Sequence[dict[str, Any]] | None = None,
    durable_debt: Sequence[dict[str, Any]] = (),
    prior_concessions: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Decode the decision wire shape and retain canonical issues for fan-in."""
    outcome_ids = expected_outcome_class_ids(
        role, active_classes=active_classes or (), durable_debt=durable_debt,
    )
    wire = decode(
        text,
        decision_schema(
            mode, role, active_classes=active_classes,
            outcome_class_ids=outcome_ids,
            prior_concessions=prior_concessions,
        ),
        max_chars=MAX_DECISION_RESPONSE_CHARS,
    )
    wire_pointers = _wire_class_pointers(wire)
    canonical = project_decision_wire(wire)
    issues = _schema_issues(
        canonical,
        decision_schema(
            mode, role, canonical=True, active_classes=active_classes,
            outcome_class_ids=outcome_ids,
            prior_concessions=prior_concessions,
        ),
    )
    canonical["_wire_class_pointers"] = wire_pointers
    issues = _remap_class_schema_issues(canonical, issues)
    issues.extend(_canonical_class_projection_issues(canonical))
    return canonical, issues


def decode_decision(
    text: str, *, mode: str, role: str,
    active_classes: Sequence[dict[str, Any]] | None = None,
    durable_debt: Sequence[dict[str, Any]] = (),
    prior_concessions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Decode and structurally validate a decision before semantic layers run."""
    value, issues = decode_decision_with_issues(
        text, mode=mode, role=role, active_classes=active_classes,
        durable_debt=durable_debt,
        prior_concessions=prior_concessions,
    )
    _raise_semantic_issues(issues)
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


def _rekey_finding_collisions(
    value: dict[str, Any], historic_ids: set[str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Make response-local finding labels safe for durable materialization."""
    finding_ids = [row["id"] for row in value["governing_findings"]]
    reserved = set(finding_ids) | historic_ids
    renamed: dict[str, str] = {}
    candidate = 1
    for finding_id in finding_ids:
        if finding_id not in historic_ids:
            continue
        while f"F{candidate}" in reserved:
            candidate += 1
        replacement = f"F{candidate}"
        candidate += 1
        reserved.add(replacement)
        renamed[finding_id] = replacement
    if not renamed:
        return value, {}

    rewritten = deepcopy(value)
    for finding in rewritten["governing_findings"]:
        finding["id"] = renamed.get(finding["id"], finding["id"])
    for outcome in rewritten.get("class_outcomes", []):
        basis = outcome.get("basis")
        if basis and basis["kind"] == "new_finding":
            basis["finding_id"] = renamed.get(
                basis["finding_id"], basis["finding_id"],
            )
    for coverage in rewritten.get("coverage", []):
        coverage["finding_ids"] = [
            renamed.get(finding_id, finding_id)
            for finding_id in coverage["finding_ids"]
        ]
    return rewritten, renamed


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
    action_pointers = _class_row_pointers(value, "class_actions")
    pointers.extend(
        action_pointers[action["class_id"]] for action in value["class_actions"]
    )
    return records, pointers


def materialize_decision_value(
    value: dict[str, Any], *, mode: str, role: str,
    source_ids: Sequence[str] = (), source_severities: dict[str, str] | None = None,
    source_evidence: dict[str, Sequence[str]] | None = None,
    assessment_verdicts: dict[str, str] | None = None,
    assessment_findings: dict[str, str | None] | None = None,
    assessment_evidence: dict[str, Sequence[str]] | None = None,
    active_classes: Sequence[dict[str, Any]] = (),
    durable_debt: Sequence[dict[str, Any]] = (),
    prior_concessions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate a decoded semantic decision and project it to durable V1 shape."""
    value = deepcopy(value)
    # Historical canonical acceptance rows predate the fresh wire field. Fresh
    # provider replies remain closed and require the keyed object in decision_schema.
    if not prior_concessions:
        value.setdefault("concession_challenges", [])
    issues: list[str] = []
    findings = value["governing_findings"]
    by_finding = _unique(findings, "id", "governing_findings", issues)
    if role == "final":
        _validate_coverage(value["coverage"], by_finding, issues)
    early_outcome_pointers = _class_row_pointers(value, "class_outcomes")
    for outcome in value.get("class_outcomes", []):
        basis = outcome.get("basis")
        if (
            basis and basis["kind"] == "new_finding"
            and basis["finding_id"] not in by_finding
        ):
            issues.append(
                f"{early_outcome_pointers[outcome['class_id']]}/basis/finding_id: "
                "must name a governing finding"
            )
    classes = {row["class_id"]: row for row in active_classes}
    if len(classes) != len(active_classes):
        issues.append("/active_classes: duplicate class_id")
    concessions = prior_concessions or {}
    challenge_pointers = _class_row_pointers(value, "concession_challenges")
    challenges = _unique(
        value["concession_challenges"], "class_id", "concession_challenges", issues,
    )
    if set(challenges) != set(concessions):
        issues.append(
            f"/concession_challenges: expected exactly {sorted(concessions)}, "
            f"got {sorted(challenges)}"
        )
    debt_by_id = {
        row["id"]: row for row in durable_debt
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    open_debt = {key: row for key, row in debt_by_id.items() if row.get("status") == "open"}
    historic_finding_ids = {
        row.get("finding_id") for row in debt_by_id.values()
        if isinstance(row.get("finding_id"), str)
    }
    value, finding_id_renames = _rekey_finding_collisions(
        value, historic_finding_ids,
    )
    findings = value["governing_findings"]
    by_finding = _unique(findings, "id", "governing_findings", issues)

    source_rows: list[dict[str, Any]] = []
    governing_by_source: dict[str, list[str]] = {}
    if role == "census":
        expected_sources = set(source_ids)
        for finding_index, finding in enumerate(findings):
            finding_pointer = f"/governing_findings/{finding_index}"
            allowed_evidence: set[str] = set()
            for source in finding["source_ids"]:
                if source not in expected_sources:
                    issues.append(
                        f"{finding_pointer}/source_ids: unknown source {source!r}"
                    )
                    continue
                source_rows.append({"source_id": source, "governing_id": finding["id"]})
                governing_by_source.setdefault(source, []).append(finding["id"])
                allowed_evidence.update((source_evidence or {}).get(source, ()))
                severity = (source_severities or {}).get(source)
                if severity and _rank(finding["severity"]) < _rank(severity):
                    issues.append(
                        f"{finding_pointer}/severity: cannot downgrade {source}"
                    )
            foreign_evidence = sorted(set(finding["evidence"]) - allowed_evidence)
            if source_evidence is not None and foreign_evidence:
                issues.append(
                    f"{finding_pointer}/evidence: citations must come from mapped "
                    f"source evidence; foreign={foreign_evidence}"
                )
            if source_evidence is not None:
                finding["evidence"] = list(dict.fromkeys(
                    anchor
                    for source in finding["source_ids"]
                    for anchor in source_evidence.get(source, ())
                ))
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
            if role == "census":
                expected_verdict = (assessment_verdicts or {}).get(cid)
                cited_source = (assessment_findings or {}).get(cid)
                if expected_verdict != "violated":
                    issues.append(
                        f"/governing_findings/{finding_index}/classification/class_id: "
                        f"cannot target active class {cid!r}; its integrity assessment "
                        f"verdict is {expected_verdict!r}, so reclassify this finding"
                    )
                elif cited_source not in finding.get("source_ids", []):
                    issues.append(
                        f"/governing_findings/{finding_index}/source_ids: existing class "
                        f"{cid!r} requires its cited violated integrity source "
                        f"{cited_source!r}"
                    )
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

    if role == "census":
        outcomes: dict[str, dict[str, Any]] = {}
        outcome_pointers: dict[str, str] = {}
        for cid, verdict in (assessment_verdicts or {}).items():
            evidence = list((assessment_evidence or {}).get(cid, ()))
            outcome: dict[str, Any] = {
                "class_id": cid, "verdict": verdict, "evidence": evidence,
            }
            if verdict == "violated":
                cited = (assessment_findings or {}).get(cid)
                matches = [
                    finding_id for finding_id in governing_by_source.get(cited or "", [])
                    if finding_class.get(finding_id) == cid
                ]
                if len(matches) != 1:
                    issues.append(
                        f"/governing_findings: violated class {cid!r} requires exactly "
                        f"one governing finding for cited source {cited!r}; got {matches}"
                    )
                if len(matches) == 1:
                    outcome["basis"] = {
                        "kind": "new_finding", "finding_id": matches[0],
                    }
                    outcome_pointers[cid] = next(
                        f"/governing_findings/{index}"
                        for index, finding in enumerate(findings)
                        if finding["id"] == matches[0]
                    )
            outcomes[cid] = outcome
    else:
        outcome_pointers = _class_row_pointers(value, "class_outcomes")
        outcomes = _unique(
            value["class_outcomes"], "class_id", "class_outcomes", issues,
        )
        authored_classes = (
            set(classes) if role == "final"
            else {
                cid for debt in open_debt.values() for cid in debt.get("class_ids", [])
                if cid in classes
            }
        )
        optional_authored_classes = set(outcomes) - authored_classes
        missing_authored_classes = authored_classes - set(outcomes)
        unknown_authored_classes = set(outcomes) - set(classes)
        if missing_authored_classes or unknown_authored_classes:
            issues.append(
                "/class_outcomes: must include every required class and only active "
                f"optional classes; missing={sorted(missing_authored_classes)}, "
                f"unknown={sorted(unknown_authored_classes)}"
            )
        if role == "correction":
            finding_indexes = {
                finding["id"]: index for index, finding in enumerate(findings)
            }
            for cid, finding_id in existing_findings.items():
                finding_index = finding_indexes[finding_id]
                classification = findings[finding_index]["classification"]
                pointer = f"/governing_findings/{finding_index}/classification"
                if cid not in authored_classes:
                    if cid in optional_authored_classes:
                        issues.append(
                            f"{outcome_pointers.get(cid, '/class_outcomes')}: a fresh "
                            "non-debt-bound existing-class finding derives its outcome "
                            "from classification.assessment_evidence; omit the optional "
                            "authored outcome"
                        )
                    evidence = classification.get("assessment_evidence")
                    if not isinstance(evidence, list):
                        issues.append(
                            f"{pointer}/assessment_evidence: required for a new "
                            "non-debt-bound class occurrence"
                        )
                        continue
                    finding_evidence = findings[finding_index]["evidence"]
                    missing = [
                        anchor for anchor in evidence
                        if anchor not in finding_evidence
                    ]
                    if missing:
                        issues.append(
                            f"{pointer.rsplit('/', 1)[0]}/evidence: fresh aggregate "
                            f"finding for class {cid!r} must include every "
                            "current-occurrence anchor authored in "
                            f"{pointer}/assessment_evidence; missing {missing}"
                        )
                    outcomes[cid] = {
                        "class_id": cid, "verdict": "violated",
                        "evidence": list(evidence),
                        "basis": {"kind":"new_finding", "finding_id":finding_id},
                    }
                    outcome_pointers[cid] = pointer
                    continue
                outcome = outcomes.get(cid)
                basis = outcome.get("basis") if outcome else None
                if (
                    outcome is None or outcome.get("verdict") != "violated"
                    or basis != {"kind":"new_finding", "finding_id":finding_id}
                ):
                    issues.append(
                        f"{outcome_pointers.get(cid, '/class_outcomes')}: a fresh "
                        f"existing-class finding requires violated new_finding basis "
                        f"naming {finding_id!r}"
                    )
                else:
                    finding_evidence = findings[finding_index]["evidence"]
                    missing = [
                        anchor for anchor in outcome["evidence"]
                        if anchor not in finding_evidence
                    ]
                    if missing:
                        issues.append(
                            f"{pointer.rsplit('/', 1)[0]}/evidence: fresh aggregate "
                            f"finding for class {cid!r} must include every "
                            "current-occurrence anchor authored in "
                            f"{outcome_pointers.get(cid, '/class_outcomes')}/evidence; "
                            f"missing {missing}"
                        )
                for debt_id, debt in open_debt.items():
                    if cid not in debt.get("class_ids", []):
                        continue
                    debt_outcome = debt_outcomes.get(debt_id)
                    if debt_outcome is not None and debt_outcome["status"] != "closed":
                        issues.append(
                            f"{debt_outcome_pointers[debt_id]}/status: a fresh aggregate "
                            f"finding for class {cid!r} must close its prior open debt "
                            f"{debt_id!r}; include every still-reachable predecessor "
                            "occurrence in the aggregate finding"
                        )
        expected_model_classes = (
            authored_classes | set(existing_findings) | optional_authored_classes
        )
        if set(outcomes) != expected_model_classes:
            issues.append(
                f"/class_outcomes: expected exactly {sorted(expected_model_classes)}, "
                f"got {sorted(outcomes)}"
            )

    assessment_rows: list[dict[str, Any]] = []
    materialized_assessments: list[dict[str, Any]] = []
    violated: set[str] = set()
    target_by_class: dict[str, str | None] = {}
    for cid, outcome in outcomes.items():
        outcome_pointer = outcome_pointers.get(cid, "/class_actions")
        target: str | None = None
        if outcome["verdict"] == "violated":
            violated.add(cid)
            basis = outcome.get("basis")
            if basis is None:
                target_by_class[cid] = None
                assessment_rows.append({"assessment_id": cid, "governing_id": None})
                materialized_assessments.append({
                    "class_id": cid, "verdict": outcome["verdict"],
                    "evidence": list(outcome["evidence"]), "finding_id": None,
                })
                continue
            if basis["kind"] == "new_finding":
                target = basis["finding_id"]
                finding = by_finding.get(target)
                if finding is None or finding_class.get(target) != cid:
                    issues.append(
                        f"{outcome_pointer}/basis: finding must classify to this class"
                    )
            else:
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

    if role == "correction":
        for cid in classes:
            retained = [
                debt_id for debt_id, debt in open_debt.items()
                if cid in debt.get("class_ids", [])
                and debt_outcomes.get(debt_id, {}).get("status") == "open"
            ]
            prospective = len(retained) + (1 if cid in existing_findings else 0)
            if prospective > 1:
                pointers = [debt_outcome_pointers[item] for item in retained]
                issues.append(
                    f"/debt_outcomes: correction would retain {prospective} open debts "
                    f"for active class {cid!r}; keep at most one aggregate blocker "
                    f"(retained pointers={pointers})"
                )

    action_pointers = _class_row_pointers(value, "class_actions")
    actions = _unique(
        value["class_actions"], "class_id", "class_actions", issues,
    )
    challenge_targets = set(existing_findings) | {
        cid for cid, action in actions.items()
        if action.get("kind") in {"reopen", "replace"}
    }
    for cid, row in challenges.items():
        pointer = challenge_pointers.get(cid, "/concession_challenges")
        challenge = row["challenge"]
        targeted = cid in challenge_targets
        if targeted and challenge is None:
            issues.append(
                f"{pointer}: newly targeting a conceded class requires an "
                "evidence-backed concession challenge"
            )
            continue
        if not targeted and challenge is not None:
            issues.append(
                f"{pointer}: challenge must be null when this response does not "
                "newly target the conceded class"
            )
            continue
        if challenge is not None:
            expected_debt = concessions.get(cid, {}).get("debt_id")
            if challenge.get("debt_id") != expected_debt:
                issues.append(f"{pointer}/challenge/debt_id: must name {expected_debt!r}")
    derived_actions: list[tuple[dict[str, Any], str]] = []
    for cid, action in actions.items():
        action_pointer = action_pointers[cid]
        if cid not in classes:
            issues.append(f"{action_pointer}/class_id: unknown active class")
            continue
        status = classes[cid]["status"]
        if action["kind"] == "close" and (
            cid not in outcomes or outcomes[cid]["verdict"] != "satisfied"
        ):
            issues.append(
                f"{action_pointer}: close requires an authored satisfied class outcome "
                "with evidence"
            )
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
        outcome_pointer = outcome_pointers.get(cid, "/class_actions")
        cls = classes.get(cid)
        if cls is None:
            continue
        action = actions.get(cid)
        if outcome["verdict"] == "satisfied" and cls["status"] in cc.UNPROVEN_STATUSES:
            if cls["mechanized"]:
                issues.append(
                    f"{outcome_pointer}: mechanized open class cannot be model-closed"
                )
            if action is None or action["kind"] == "reclassify":
                derived_actions.append((
                    {"kind": "close", "class_id": cid}, outcome_pointer,
                ))
            elif action["kind"] not in {"close", "replace"}:
                issues.append(
                    f"{action_pointers.get(cid, outcome_pointer)}: "
                    "open satisfied class must close"
                )
        if outcome["verdict"] == "violated" and cls["status"] == cc.CLOSED:
            if cls["mechanized"]:
                allowed = {"replace"}
            else:
                allowed = {"reopen", "reclassify", "replace"}
                if action is None or action["kind"] == "reclassify":
                    derived_actions.append((
                        {"kind": "reopen", "class_id": cid}, outcome_pointer,
                    ))
            if cls["mechanized"] and (action is None or action["kind"] not in allowed):
                repair_pointer = (
                    _class_slot_pointer(value, "class_actions", cid)
                    if action is None else action_pointers[cid]
                )
                issues.append(
                    f"{repair_pointer}: "
                    f"closed violated class requires {sorted(allowed)}"
                )
            elif not cls["mechanized"] and action is not None and action["kind"] not in allowed:
                issues.append(
                    f"{action_pointers[cid]}: closed violated class requires "
                    "reopen, reclassify with derived reopen, or replace"
                )

    _raise_semantic_issues(issues)

    class_records.extend(class_records_from_actions(list(actions.values())))
    for action in actions.values():
        class_record_pointers.append(
            action_pointers.get(
                action["class_id"], outcome_pointers.get(action["class_id"], "/class_actions"),
            )
        )
    for action, pointer in derived_actions:
        class_records.extend(class_records_from_actions([action]))
        class_record_pointers.append(pointer)

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
                {
                    "finding_id": finding["id"], "kind":"new_class",
                    "record_index": int(str(finding_class[finding["id"]]).split(":", 1)[1]),
                }
                if finding["classification"]["kind"] == "new_class"
                else {
                    "finding_id":finding["id"],
                    **{
                        key:finding["classification"][key]
                        for key in ("kind", "reason", "class_id")
                        if key in finding["classification"]
                    },
                }
            )
            for finding in findings
        ],
        "class_records": class_records,
        "class_assessments": materialized_assessments,
        "_finding_class_refs": finding_class,
        "_class_record_pointers": class_record_pointers,
        "concession_challenges": deepcopy(value["concession_challenges"]),
    }
    if role == "final":
        result["coverage"] = value["coverage"]
    if finding_id_renames:
        result["_finding_id_renames"] = finding_id_renames
    return result


def materialize_decision(
    text: str, *, mode: str, role: str,
    source_ids: Sequence[str] = (), source_severities: dict[str, str] | None = None,
    source_evidence: dict[str, Sequence[str]] | None = None,
    assessment_verdicts: dict[str, str] | None = None,
    assessment_findings: dict[str, str | None] | None = None,
    assessment_evidence: dict[str, Sequence[str]] | None = None,
    active_classes: Sequence[dict[str, Any]] = (),
    durable_debt: Sequence[dict[str, Any]] = (),
    prior_concessions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Decode one semantic decision and project it to the durable V1 shape."""
    value = decode_decision(
        text, mode=mode, role=role, active_classes=active_classes,
        durable_debt=durable_debt,
        prior_concessions=prior_concessions,
    )
    return materialize_decision_value(
        value, mode=mode, role=role, source_ids=source_ids,
        source_severities=source_severities,
        source_evidence=source_evidence,
        assessment_verdicts=assessment_verdicts,
        assessment_findings=assessment_findings,
        assessment_evidence=assessment_evidence,
        active_classes=active_classes, durable_debt=durable_debt,
        prior_concessions=prior_concessions,
    )
