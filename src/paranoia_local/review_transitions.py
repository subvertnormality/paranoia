"""Pure scheduling decisions; IO and canonical class settlement stay with their owners."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from . import staged_protocol as sp


@dataclass(frozen=True)
class PhaseDecision:
    phase: str
    final_engine: str | None
    reason: str


@dataclass(frozen=True)
class ReviewFacts:
    phase: str
    final_engine: str | None
    blocking_debt: bool
    blocking_classes: frozenset[str]
    unbound_classes: frozenset[str]
    unbound_marker: bool

    @classmethod
    def capture(cls, state: Mapping[str, Any], blocking_classes: Iterable[str]) -> ReviewFacts:
        """Capture only validated state; this is not a deserializer or migration."""
        blockers = frozenset(blocking_classes)
        open_debt = [row for row in state.get("debt", []) if row["status"] == "open"]
        bound = {cid for row in open_debt for cid in row.get("class_ids", [])}
        return cls(
            state["phase"], state.get("final_engine"),
            any(row["severity"] in sp.BLOCKING for row in open_debt),
            blockers, blockers - bound,
            bool(state.get("unbound_class_ids") or state.get("unbound_classes")),
        )


def incoming(facts: ReviewFacts) -> PhaseDecision:
    """Choose a role after authoritative normalization, never invent final ownership."""
    phase, owner = facts.phase, facts.final_engine
    if phase == "census" and facts.unbound_marker and facts.blocking_debt:
        return PhaseDecision("correction", None, "actionable-debt")
    if phase != "census" and facts.unbound_classes and not facts.blocking_debt:
        if phase == "final" and owner:
            return PhaseDecision("final", owner, "owned-class-closure")
        return PhaseDecision("census", None, "unowned-class-closure")
    return PhaseDecision(phase, owner if phase == "final" else None, "retained-phase")


def after_debt(
    *, phase: str, final_engine: str | None, engine: str, blocking_debt: bool,
) -> PhaseDecision:
    if blocking_debt:
        return PhaseDecision("correction", None, "blocking-findings")
    if phase == "correction":
        return PhaseDecision("final", engine, "correction-needs-cold-final")
    if phase == "final" and final_engine != engine:
        return PhaseDecision("final", final_engine, "foreign-final")
    return PhaseDecision("clear", None, "review-debt-clear")


def after_classes(
    facts: ReviewFacts, *, reviewed_phase: str, prior_owner: str | None, engine: str,
) -> PhaseDecision:
    """Reconcile canonical class results with finding results after a valid settlement."""
    if facts.blocking_debt:
        return PhaseDecision("correction", None, "blocking-findings")
    if facts.unbound_classes:
        if reviewed_phase == "correction":
            return PhaseDecision("final", engine, "class-only-cold-final")
        if reviewed_phase == "final" and prior_owner:
            return PhaseDecision("final", prior_owner, "class-only-final-still-open")
        return PhaseDecision("census", None, "class-closure-needs-census")
    if facts.blocking_classes:
        return PhaseDecision("correction", None, "class-bound-advisory-debt")
    return PhaseDecision(facts.phase, facts.final_engine, "settled-phase")
