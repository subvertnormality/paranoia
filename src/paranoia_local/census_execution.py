"""Validated census execution results; no provider or settlement policy.

The handler supplies a callback that owns prompts, provider admission and validation.
This module joins all lanes and preserves their ordered diagnostics. The handler
continues to own cache authority and the atomic canonical state transition.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from . import review_census as rc, telemetry


@dataclass(frozen=True)
class LaneResult:
    lane: str
    manifest: dict[str, Any]
    attempts: list[rc.Attempt]
    rejected_payloads: list[dict[str, Any]]
    member_coverage: dict[str, list[str]]


def namespace_lane(
    lane: str, manifest: dict[str, Any], attempts: list[rc.Attempt],
    rejected_payloads: list[dict[str, Any]], member_coverage: dict[str, list[str]],
) -> LaneResult:
    """Give validated response-local finding IDs their existing lane namespace."""
    renamed = {finding["id"]: f"{lane}:{finding['id']}" for finding in manifest["findings"]}
    for finding in manifest["findings"]:
        finding["id"] = renamed[finding["id"]]
    for coverage in manifest["coverage"]:
        coverage["finding_ids"] = [renamed[fid] for fid in coverage["finding_ids"]]
    for assessment in manifest["class_assessments"]:
        if assessment["finding_id"] is not None:
            assessment["finding_id"] = renamed[assessment["finding_id"]]
    return LaneResult(lane, manifest, attempts, rejected_payloads, member_coverage)


@dataclass(frozen=True)
class CensusResult:
    manifests: list[dict[str, Any]]
    attempts: list[rc.Attempt]
    rejected_payloads: list[dict[str, Any]]
    member_coverage: dict[str, list[str]]


def _raise_failures(
    lanes: Sequence[str], rows: list[LaneResult],
    errors: list[tuple[str, rc.CensusError]],
) -> None:
    """Keep every sibling's diagnostics on the existing authoritative failure."""
    errors.sort(key=lambda row: lanes.index(row[0]))
    attempts = [attempt for row in rows for attempt in row.attempts]
    attempts.extend(
        attempt for _, error in errors for attempt in getattr(error, "attempts", [])
    )
    attempts.sort(key=lambda item: item.sequence or 0)
    rejected = [
        (lanes.index(name), position, payload)
        for name, error in errors
        for position, payload in enumerate(getattr(error, "rejected_payloads", []))
    ]
    rejected.extend(
        (lanes.index(row.lane), position, payload)
        for row in rows for position, payload in enumerate(row.rejected_payloads)
    )
    rejected.sort(key=lambda row: (
        row[2].get("sequence") is None, row[2].get("sequence") or 0, row[0], row[1],
    ))
    error = errors[0][1]
    error.attempts = attempts
    error.rejected_payloads = [payload for _, _, payload in rejected]
    error.manifests = [row.manifest for row in rows]
    raise error


def collect(lanes: Sequence[str], run_lane: Callable[[str], LaneResult]) -> CensusResult:
    """Join every admitted lane before returning or raising, in canonical lane order."""
    rows: list[LaneResult] = []
    errors: list[tuple[str, rc.CensusError]] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending = {telemetry.submit(pool, run_lane, lane): lane for lane in lanes}
        for future in as_completed(pending):
            try:
                rows.append(future.result())
            except rc.CensusError as error:
                errors.append((pending[future], error))
    rows.sort(key=lambda row: lanes.index(row.lane))
    if errors:
        _raise_failures(lanes, rows, errors)
    return CensusResult(
        [row.manifest for row in rows],
        [attempt for row in rows for attempt in row.attempts],
        [payload for row in rows for payload in row.rejected_payloads],
        next(row.member_coverage for row in rows if row.lane == "integrity"),
    )


@dataclass(frozen=True)
class CensusSources:
    """One projection of validated lane observations into settlement inputs."""
    source_ids: list[str]
    source_severities: dict[str, str]
    source_evidence: dict[str, list[str]]
    assessment_ids: list[str]
    assessment_verdicts: dict[str, str]
    assessment_findings: dict[str, str | None]
    assessment_evidence: dict[str, list[str]]

    @classmethod
    def capture(cls, manifests: Sequence[dict[str, Any]]) -> CensusSources:
        findings = [finding for manifest in manifests for finding in manifest["findings"]]
        assessments = [
            assessment for manifest in manifests
            for assessment in manifest["class_assessments"]
        ]
        return cls(
            [row["id"] for row in findings],
            {row["id"]: row["severity"] for row in findings},
            {row["id"]: list(row["evidence"]) for row in findings},
            [row["class_id"] for row in assessments],
            {row["class_id"]: row["verdict"] for row in assessments},
            {row["class_id"]: row["finding_id"] for row in assessments},
            {row["class_id"]: list(row["evidence"]) for row in assessments},
        )

    def arguments(self) -> dict[str, Any]:
        return {
            "source_ids": self.source_ids, "source_severities": self.source_severities,
            "source_evidence": self.source_evidence, "assessment_ids": self.assessment_ids,
            "assessment_verdicts": self.assessment_verdicts,
            "assessment_findings": self.assessment_findings,
            "assessment_evidence": self.assessment_evidence,
        }
