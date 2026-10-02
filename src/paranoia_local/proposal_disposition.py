"""Bounded caller accounting; never reviewer evidence or settlement authority."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any

from jsonschema import Draft202012Validator

from .patch_proposals import MAX_TARGETS

STATUSES = ("applied", "partially-applied", "departed")
MAX_REASON_CHARS = 500
_AUDIT = {"type": "string", "minLength": 1, "maxLength": 255,
          "pattern": r"^[^/\\\x00-\x1f]+\.json$(?![\s\S])"}
_TARGET = {"type": "string", "minLength": 1, "maxLength": 200,
           "pattern": r"^[A-Za-z0-9:._-]+$(?![\s\S])"}
INPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["proposal_audit", "status", "departed_targets"],
    "properties": {
        "proposal_audit": _AUDIT,
        "status": {"type": "string", "enum": list(STATUSES)},
        "departed_targets": {
            "type": "object", "maxProperties": MAX_TARGETS,
            "propertyNames": _TARGET,
            "additionalProperties": {
                "type": "string", "minLength": 1, "maxLength": MAX_REASON_CHARS,
                "pattern": r"^(?=.*\S)[^\x00-\x1f\x7f\x85\u2028\u2029]+$(?![\s\S])",
            },
        },
    },
    "description": (
        "Account for the preceding proposal in this tracked lineage. Use the exact "
        "PROPOSAL-AUDIT-JSON basename. SHOULD use the diff after inspection/validation; "
        "give a one-line reason for every departed addressed target. Applied requires "
        "no reasons, departed all targets, partially-applied a nonempty proper subset. "
        "Optional: omission with a pending proposal reports none-recorded. Caller "
        "declaration only; never proof of repair or clearance."
    ),
}
CALLER_EXPECTATION = (
    "The executing agent SHOULD use the proposed diff as the repair starting point "
    "after inspecting and validating it. Before the next round in the same lineage, "
    "submit prior_proposal_disposition with its PROPOSAL-AUDIT-JSON basename, status "
    "and a reason for each departed target. The API is optional; an omitted disposition "
    "of a pending proposal reports none-recorded. Disposition is caller accounting, "
    "not proof of repair or clearance."
)


def validate_input(value: Any) -> dict[str, Any]:
    error = next(Draft202012Validator(INPUT_SCHEMA).iter_errors(value), None)
    if error is not None:
        raise ValueError("prior_proposal_disposition: " + error.message[:800])
    if any(not reason.strip() for reason in value["departed_targets"].values()):
        raise ValueError("prior_proposal_disposition reasons must not be blank")
    return deepcopy(value)


def validate_receipt(value: Any) -> dict[str, Any]:
    keys = {"version", "round", "structural_snapshot", "patch_sha256", "audit", "target_ids"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("invalid proposal receipt fields")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("invalid proposal receipt version")
    if type(value["round"]) is not int or value["round"] < 1:
        raise ValueError("invalid proposal receipt round")
    for key in ("structural_snapshot", "patch_sha256"):
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise ValueError("invalid proposal receipt digest")
    if not Draft202012Validator(_AUDIT).is_valid(value["audit"]):
        raise ValueError("invalid proposal audit basename")
    targets = value["target_ids"]
    if (not isinstance(targets, list) or not 1 <= len(targets) <= MAX_TARGETS
            or any(not Draft202012Validator(_TARGET).is_valid(t) for t in targets)
            or len(targets) != len(set(targets))):
        raise ValueError("invalid proposal receipt targets")
    return deepcopy(value)


def accounting(receipt: dict[str, Any] | None, last_round: Any,
               arguments: dict[str, Any]) -> dict[str, Any] | None:
    supplied = "prior_proposal_disposition" in arguments
    value = validate_input(arguments["prior_proposal_disposition"]) if supplied else None
    if receipt is not None:
        receipt = validate_receipt(receipt)
        if type(last_round) is not int or receipt["round"] > last_round:
            raise ValueError("proposal receipt is inconsistent with durable last_round")
    pending = receipt is not None and receipt["round"] == last_round
    if not pending:
        if supplied:
            raise ValueError("prior_proposal_disposition requires a pending proposal in this lineage")
        return None
    status, reasons = "none-recorded", {}
    if value is not None:
        if value["proposal_audit"] != receipt["audit"]:
            raise ValueError("prior_proposal_disposition names a different proposal audit")
        status, reasons = value["status"], value["departed_targets"]
        targets, departed = set(receipt["target_ids"]), set(reasons)
        if (not departed <= targets
                or status == "applied" and departed
                or status == "departed" and departed != targets
                or status == "partially-applied" and not departed < targets
                or status == "partially-applied" and not departed):
            raise ValueError("prior_proposal_disposition departed targets do not match its status/receipt")
    return {"receipt": receipt, "status": status, "departed_targets": reasons}


def render(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return "PROPOSAL-DISPOSITION: " + value["status"] + " " + json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    )
