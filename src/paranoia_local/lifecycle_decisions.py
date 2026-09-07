"""Pure class lifecycle decisions after semantic outcome binding.

No wire decoding, provider calls, canonical register application or persistence.
The caller keeps diagnostic ordering and applies the canonical engine after all
independent checks pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import class_closure as cc


@dataclass(frozen=True)
class ClassState:
    """The existing class facts needed by a lifecycle decision."""
    class_id: str
    status: str
    severity: str
    mechanized: bool

    @classmethod
    def capture(cls, row: dict[str, Any]) -> ClassState:
        return cls(row["class_id"], row["status"], row["severity"], row["mechanized"])


@dataclass(frozen=True)
class LifecycleDecision:
    """Derived actions with their authored pointers; independent diagnostic rows."""
    actions: tuple[tuple[dict[str, Any], str], ...]
    issues: tuple[str, ...]


def _rank(severity: str) -> int:
    return {cc.OUT_OF_SCOPE: 0, cc.MINOR: 1, cc.MAJOR: 2,
            cc.BLOCKER: 3, cc.FATAL: 4}[severity]


def concession_issues(
    challenge: dict[str, Any] | None, *, targeted: bool,
    expected_debt: str | None, pointer: str,
) -> tuple[str, ...]:
    issues: list[str] = []
    if targeted and challenge is None:
        issues.append(
            f"{pointer}: newly targeting a conceded class requires an "
            "evidence-backed concession challenge"
        )
        return tuple(issues)
    if not targeted and challenge is not None:
        issues.append(
            f"{pointer}: challenge must be null when this response does not "
            "newly target the conceded class"
        )
        return tuple(issues)
    if challenge is not None:
        if challenge.get("debt_id") != expected_debt:
            issues.append(f"{pointer}/challenge/debt_id: must name {expected_debt!r}")
    return tuple(issues)


def action_issues(
    cls: ClassState, action: dict[str, Any], outcome: dict[str, Any] | None,
    action_pointer: str,
) -> tuple[str, ...]:
    issues: list[str] = []
    status = cls.status
    if action["kind"] == "close" and (
        outcome is None or outcome["verdict"] != "satisfied"
    ):
        issues.append(
            f"{action_pointer}: close requires an authored satisfied class outcome "
            "with evidence"
        )
    if action["kind"] == "reopen" and status != cc.CLOSED:
        issues.append(f"{action_pointer}: reopen requires closed class")
    if (
        action["kind"] == "reopen" and outcome is not None
        and outcome["verdict"] != "violated"
    ):
        issues.append(f"{action_pointer}: reopen requires violated outcome")
    if action["kind"] in {"reclassify", "replace"}:
        severity = (
            action["severity"] if action["kind"] == "reclassify"
            else action["definition"]["severity"]
        )
        if _rank(severity) < _rank(cls.severity):
            issues.append(f"{action_pointer}: cannot downgrade active class")
    if (
        action["kind"] == "replace" and cls.mechanized
        and "pattern" not in action["definition"]
    ):
        issues.append(
            f"{action_pointer}/definition: mechanized class replacement "
            "requires pattern and pathspec"
        )
    return tuple(issues)


def derive(
    cls: ClassState, outcome: dict[str, Any], action: dict[str, Any] | None,
    *, outcome_pointer: str, action_pointer: str | None, missing_action_pointer: str,
) -> LifecycleDecision:
    cid = cls.class_id
    issues: list[str] = []
    derived_actions: list[tuple[dict[str, Any], str]] = []
    if outcome["verdict"] == "satisfied" and cls.status in cc.UNPROVEN_STATUSES:
        if cls.mechanized:
            issues.append(
                f"{outcome_pointer}: mechanized open class cannot be model-closed"
            )
        if action is None or action["kind"] == "reclassify":
            derived_actions.append((
                {"kind": "close", "class_id": cid}, outcome_pointer,
            ))
        elif action["kind"] not in {"close", "replace"}:
            issues.append(
                f"{action_pointer or outcome_pointer}: "
                "open satisfied class must close"
            )
    if outcome["verdict"] == "violated" and cls.status == cc.CLOSED:
        if cls.mechanized:
            allowed = {"replace"}
        else:
            allowed = {"reopen", "reclassify", "replace"}
            if action is None or action["kind"] == "reclassify":
                derived_actions.append((
                    {"kind": "reopen", "class_id": cid}, outcome_pointer,
                ))
        if cls.mechanized and (action is None or action["kind"] not in allowed):
            repair_pointer = (
                missing_action_pointer
                if action is None else action_pointer
            )
            issues.append(
                f"{repair_pointer}: "
                f"closed violated class requires {sorted(allowed)}"
            )
        elif not cls.mechanized and action is not None and action["kind"] not in allowed:
            issues.append(
                f"{action_pointer}: closed violated class requires "
                "reopen, reclassify with derived reopen, or replace"
            )
    return LifecycleDecision(tuple(derived_actions), tuple(issues))
