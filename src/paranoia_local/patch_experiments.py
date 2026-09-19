"""Pure validation for reviewer-patch paired-experiment evidence.

The campaign runner records production-handler receipts and monotonic intervals.
This module validates and derives metrics; it does not dispatch providers, run
callers, mutate repositories, or infer missing observations.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Literal, Mapping, Sequence


class ExperimentError(ValueError):
    """The retained experiment evidence is incomplete or inconsistent."""


Owner = Literal["common", "baseline", "candidate"]

_ACTIVE_ROLES = frozenset({
    "caller", "tests", "correction", "final", "local-processing",
})
_REQUIRED_RECEIPT_KEYS = frozenset({
    "mode", "public_activations", "settled_state_sha256",
    "explicit_false_state_sha256", "rendered_trailer_sha256",
    "explicit_false_trailer_sha256", "review_audit", "proposal_audit",
    "reviewed_snapshot", "proposal_snapshot", "author_session_ref",
    "proposal_requested_session_ref", "proposal_attempt_count",
    "workspace_alive_during_proposal", "workspace_cleaned_after_return",
})


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExperimentError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ExperimentError(f"{label} must be a finite number")
    return result


def validate_handoff_receipt(value: Mapping[str, Any]) -> None:
    """Validate the exact seed-to-proposal custody receipt required by E2."""
    if set(value) != _REQUIRED_RECEIPT_KEYS:
        raise ExperimentError("handoff receipt fields are not closed and exact")
    if value["mode"] not in {"branch", "plan"}:
        raise ExperimentError("handoff mode must be branch or plan")
    if type(value["public_activations"]) is not int or value["public_activations"] != 1:
        raise ExperimentError("handoff must have exactly one public activation")
    attempts = value["proposal_attempt_count"]
    if type(attempts) is not int or attempts not in {1, 2}:
        raise ExperimentError("proposal attempt count must be one or two")
    for key in (
        "settled_state_sha256", "explicit_false_state_sha256",
        "rendered_trailer_sha256", "explicit_false_trailer_sha256",
        "review_audit", "proposal_audit", "reviewed_snapshot",
        "proposal_snapshot", "author_session_ref",
        "proposal_requested_session_ref",
    ):
        if not isinstance(value[key], str) or not value[key]:
            raise ExperimentError(f"{key} must be a nonempty string")
    if value["settled_state_sha256"] != value["explicit_false_state_sha256"]:
        raise ExperimentError("enabled and explicit-false settled state differ")
    if value["rendered_trailer_sha256"] != value["explicit_false_trailer_sha256"]:
        raise ExperimentError("enabled and explicit-false trailers differ")
    if value["review_audit"] == value["proposal_audit"]:
        raise ExperimentError("review and proposal audits must be distinct")
    if value["reviewed_snapshot"] != value["proposal_snapshot"]:
        raise ExperimentError("proposal snapshot does not match settled review")
    if value["author_session_ref"] != value["proposal_requested_session_ref"]:
        raise ExperimentError("proposal did not resume the selected lane owner")
    if value["workspace_alive_during_proposal"] is not True:
        raise ExperimentError("pinned workspace was not alive during proposal")
    if value["workspace_cleaned_after_return"] is not True:
        raise ExperimentError("pinned workspace cleanup was not observed after return")


@dataclass(frozen=True)
class Interval:
    owner: Owner
    role: str
    start: float
    end: float
    source_identity: str

    @classmethod
    def from_value(cls, value: Mapping[str, Any], index: int) -> "Interval":
        if set(value) != {"owner", "role", "start", "end", "source_identity"}:
            raise ExperimentError(f"interval {index} fields are not closed and exact")
        owner = value["owner"]
        role = value["role"]
        source = value["source_identity"]
        if owner not in {"common", "baseline", "candidate"}:
            raise ExperimentError(f"interval {index} has unknown owner")
        if not isinstance(role, str) or not role:
            raise ExperimentError(f"interval {index} role must be nonempty")
        if not isinstance(source, str) or not source:
            raise ExperimentError(f"interval {index} source identity must be nonempty")
        start = _number(value["start"], f"interval {index} start")
        end = _number(value["end"], f"interval {index} end")
        if end <= start:
            raise ExperimentError(f"interval {index} must have positive duration")
        return cls(owner, role, start, end, source)


@dataclass(frozen=True)
class PairTiming:
    seed_duration: float
    baseline_repair_duration: float
    candidate_repair_duration: float
    baseline_end_to_end_duration: float
    candidate_end_to_end_duration: float


def derive_pair_timing(
    rows: Sequence[Mapping[str, Any]], *, handler_start: float,
    settlement: float, cleanup: float,
) -> PairTiming:
    """Validate one E2 ledger and derive wait-free arm durations.

    All units are caller-chosen monotonic units and are preserved in the result.
    """
    start = _number(handler_start, "handler_start")
    settled = _number(settlement, "settlement")
    cleaned = _number(cleanup, "cleanup")
    if not start < settled < cleaned:
        raise ExperimentError("handler_start, settlement and cleanup are not ordered")
    intervals = [Interval.from_value(row, index) for index, row in enumerate(rows)]
    ordered = sorted(intervals, key=lambda row: (row.start, row.end, row.owner, row.role))
    for left, right in zip(ordered, ordered[1:]):
        if left.end > right.start:
            raise ExperimentError("experiment intervals overlap or are multiply owned")
    seeds = [row for row in intervals if row.role == "seed_review"]
    proposals = [row for row in intervals if row.role == "proposal"]
    if len(seeds) != 1 or seeds[0].owner != "common":
        raise ExperimentError("ledger requires one common seed_review interval")
    if seeds[0].start < start or seeds[0].end != settled:
        raise ExperimentError("seed_review is not bound to handler settlement")
    if len(proposals) != 1 or proposals[0].owner != "candidate":
        raise ExperimentError("ledger requires one candidate proposal interval")
    if proposals[0].start < settled or proposals[0].end > cleaned:
        raise ExperimentError("proposal is not inside the seed handler before cleanup")

    arm_rows = [
        row for row in intervals if row.role not in {"seed_review", "proposal"}
    ]
    for row in arm_rows:
        if row.owner not in {"baseline", "candidate"} or row.role not in _ACTIVE_ROLES:
            raise ExperimentError("active arm interval has inconsistent owner or role")
        if row.start < cleaned:
            raise ExperimentError("arm activity began before seed handler cleanup")
    if not any(row.owner == "baseline" for row in arm_rows):
        raise ExperimentError("baseline active intervals are missing")
    if not any(row.owner == "candidate" for row in arm_rows):
        raise ExperimentError("candidate active intervals are missing")

    seed_duration = seeds[0].end - seeds[0].start
    baseline = sum(
        row.end - row.start for row in arm_rows if row.owner == "baseline"
    )
    candidate = (proposals[0].end - proposals[0].start) + sum(
        row.end - row.start for row in arm_rows if row.owner == "candidate"
    )
    return PairTiming(
        seed_duration=seed_duration,
        baseline_repair_duration=baseline,
        candidate_repair_duration=candidate,
        baseline_end_to_end_duration=seed_duration + baseline,
        candidate_end_to_end_duration=seed_duration + candidate,
    )


def paired_ratios(pairs: Iterable[PairTiming]) -> tuple[tuple[float, float], ...]:
    """Return repair/end-to-end candidate:baseline ratios without hiding failures."""
    result = []
    for index, pair in enumerate(pairs):
        if pair.baseline_repair_duration <= 0 or pair.baseline_end_to_end_duration <= 0:
            raise ExperimentError(f"pair {index} has no comparable baseline duration")
        result.append((
            pair.candidate_repair_duration / pair.baseline_repair_duration,
            pair.candidate_end_to_end_duration / pair.baseline_end_to_end_duration,
        ))
    return tuple(result)
