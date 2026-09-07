"""Deterministic materializer/canonical-settlement differential corpus."""
from __future__ import annotations

from copy import deepcopy
from itertools import product
from paranoia_local import class_closure as cc, staged_protocol as sp
from tests.test_staged_protocol import (
    active_class, decision, finding, coverage, durable_debt, prior_concession,
    durable_projection,
)


def cases():
    statuses = (cc.OPEN, cc.CLOSED, cc.OVER_BROAD, cc.UNCHECKED)
    kinds = (None, "close", "reopen", "raise", "lower", "manual", "pattern")
    for mode, role, mechanized, status, verdict, kind, challenge in product(
        (cc.PLAN_MODE, cc.BRANCH_MODE), ("census", "correction", "final"),
        (False, True), statuses, (None, "satisfied", "violated"), kinds,
        ("absent", "null", "bound"),
    ):
        cls = active_class(status=status, mechanized=mechanized)
        anchor = "plan:1" if mode == cc.PLAN_MODE else "repository/app.py:1"
        action = None
        if kind in {"close", "reopen"}:
            action = {"kind": kind, "class_id": cls["class_id"]}
        elif kind in {"raise", "lower"}:
            action = {"kind": "reclassify", "class_id": cls["class_id"],
                      "severity": "BLOCKER" if kind == "raise" else "MINOR"}
        elif kind in {"manual", "pattern"}:
            definition = {"invariant": "replacement invariant", "severity": "MAJOR"}
            definition.update({"pattern": "BAD", "pathspec": "*.py"} if kind == "pattern"
                              else {"procedure": "inspect the replacement",
                                    "members": ["reviewed-path"]})
            action = {"kind": "replace", "class_id": cls["class_id"], "definition": definition}
        findings = []
        if verdict == "violated":
            row = finding(classification={"kind": "existing_class", "class_id": cls["class_id"]},
                          source_ids=["source"] if role == "census" else None)
            row["evidence"] = [anchor]
            findings = [row]
        value = decision(role, governing_findings=findings,
                         class_actions=[action] if action else [])
        if role == "final":
            value["coverage"] = coverage(*["G1"] if findings else [])
        if role != "census" and verdict:
            outcome = {"class_id": cls["class_id"], "verdict": verdict, "evidence": [anchor]}
            if findings:
                outcome["basis"] = {"kind": "new_finding", "finding_id": "G1"}
            value["class_outcomes"] = [outcome]
        debt = [durable_debt()] if role == "correction" else []
        if debt:
            value["debt_outcomes"] = [{"debt_id": "D7", "status": "closed", "evidence": [anchor]}]
        concessions = prior_concession() if challenge != "absent" else {}
        if concessions:
            body = None if challenge == "null" else {
                "debt_id": "D7", "reason": "new occurrence", "evidence": [anchor],
            }
            value["concession_challenges"] = [{"class_id": cls["class_id"], "challenge": body}]
        value["_wire_class_pointers"] = {
            name: {cls["class_id"]: f"/{name}/{cls['class_id']}"}
            for name in ("class_actions", "class_outcomes", "concession_challenges")
        }
        arguments = {"mode": mode, "role": role, "active_classes": [cls],
                     "durable_debt": debt, "prior_concessions": concessions}
        if role == "census":
            arguments.update(source_ids=["source"] if findings else [],
                             source_severities={"source": "MAJOR"},
                             source_evidence={"source": [anchor]},
                             assessment_verdicts={cls["class_id"]: verdict} if verdict else {},
                             assessment_findings={cls["class_id"]: "source" if findings else None},
                             assessment_evidence={cls["class_id"]: [anchor]})
        key = "/".join(map(str, (mode, role, mechanized, status, verdict, kind, challenge)))
        yield key, value, arguments


def evaluate(value, arguments):
    original = deepcopy(value)
    try:
        parsed = sp.materialize_decision_value(value, **arguments)
        durable = durable_projection(
            parsed, active=arguments["active_classes"], prior_debt=arguments["durable_debt"],
            phase=arguments["role"], mode=arguments["mode"],
        )
        result = {"accepted": parsed, "durable": durable}
    except (sp.ProtocolError, cc.RegisterError, ValueError) as exc:
        result = {"rejected": type(exc).__name__, "message": str(exc)}
    assert value == original, "materialization mutated caller input"
    return result


def fingerprints():
    import hashlib
    import json
    rows = {}
    for key, value, arguments in cases():
        result = evaluate(value, arguments)
        raw = json.dumps(result, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        rows[key] = {"sha256": hashlib.sha256(raw.encode()).hexdigest(),
                     "outcome": "accepted" if "accepted" in result else "rejected"}
    return rows


if __name__ == "__main__":
    import json
    print(json.dumps(fingerprints(), sort_keys=True))

