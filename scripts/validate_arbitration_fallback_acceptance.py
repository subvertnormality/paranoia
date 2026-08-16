#!/usr/bin/env python3
"""Validate the separately versioned original-fallback acceptance record."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from paranoia_local import arbitrate_handler as ah
from paranoia_local import arbitration as arb
from paranoia_local import engines


SOURCES = frozenset({
    "src/paranoia_local/arbitrate_handler.py",
    "src/paranoia_local/arbitration.py",
    "src/paranoia_local/prompts.py",
    "src/paranoia_local/server.py",
    "scripts/validate_arbitration_fallback_acceptance.py",
    "tests/test_arbitrate_handler.py",
    "tests/test_arbitration_fallback_acceptance.py",
})

SCOPE = {
    "proves": [
        "a reported destructive cleaner candidate was retained as rejected audit data",
        "a signed-in Codex attester authorized the complete canonical originals",
        "both signed-in decider prompts contained the complete canonical originals and no substituted cleaned field",
        "the recorded run reached an ordinary terminal arbitration result with CLEANING original-attested",
    ],
    "does_not_prove": [
        "that the current Claude cleaner will reproduce the historical destructive rewrite probabilistically",
        "that either decider's resolved citation semantically entails its constraint",
        "provider service identity beyond the recorded local CLI versions and configured model names",
    ],
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _evidence_path(repo: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("acceptance evidence path must be repository-relative")
    path = repo / value
    if not path.is_file():
        raise ValueError(f"acceptance evidence does not exist: {value}")
    return path


def _cleaned_digest_bound(cleaned: dict) -> bool:
    if set(cleaned) != {"decision", "context", "hints", "statements", "sha256"}:
        return False
    fields = {key: cleaned[key] for key in ("decision", "context", "hints", "statements")}
    encoded = json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return cleaned["sha256"] == hashlib.sha256(
        encoded.encode("utf-8", "surrogatepass")
    ).hexdigest()


def _effective_packet(audit: dict) -> ah.Packet:
    raw = audit["raw_input"]
    return ah.Packet(
        decision=raw["decision"], stakes=raw["stakes"], context=raw["context"],
        hints=list(raw["files"]), statements=dict(raw["options"]),
        cleaning="original-attested", attestation=audit["attestation"],
    )


def _attestation_bound(audit: dict) -> bool:
    raw, cleaned = audit["raw_input"], audit["cleaned"]
    expected = {
        "decision": (raw["decision"], cleaned["decision"]),
        **{
            option_id: (statement, cleaned["statements"][option_id])
            for option_id, statement in raw["options"].items()
        },
    }
    if raw["files"]:
        expected["hints"] = (
            ah._render_hints(raw["files"]), ah._render_hints(cleaned["hints"]),
        )
    try:
        attestation = ah.parse_attestation(audit["attestation"], expected)
    except (KeyError, arb.ArbitrationError):
        return False
    if (
        attestation.ok or not attestation.original_neutrality_pass
        or attestation.stakes_advocacy is not None
        or attestation.context_advocacy is not None
    ):
        return False
    attesters = [row for row in audit["phase_attempts"] if row.get("role") == "attester"]
    if len(attesters) != 1 or attesters[0].get("reply") != audit["attestation"]:
        return False
    expected_rejection = (
        f"fidelity changed: {attestation.changed}; detail: {attestation.fidelity_detail}; "
        f"neutrality: {'PASS' if attestation.neutrality_pass else 'FAIL ' + attestation.neutrality_note}"
    )
    return attesters[0].get("rejection") == expected_rejection


def _decider_prompts_bound(audit: dict) -> bool:
    if len(audit.get("rounds", [])) != 1 or set(audit["rounds"][0]) != {"codex", "claude"}:
        return False
    packet = _effective_packet(audit)
    for engine, cast in audit["rounds"][0].items():
        mapping = audit.get("label_maps", {}).get(engine)
        if not isinstance(mapping, dict) or set(mapping.values()) != set(packet.statements):
            return False
        presentation = arb.Presentation(
            engine=engine,
            items=tuple((label, packet.statements[option_id]) for label, option_id in mapping.items()),
            label_to_id=dict(mapping),
            id_to_label={option_id: label for label, option_id in mapping.items()},
            reversed_order=False,
        )
        expected_body = ah.render_decider_body(packet, presentation)
        attempts = cast.get("attempts", [])
        if len(attempts) != 1 or attempts[0].get("body") != expected_body:
            return False
        if cast.get("prompt") != expected_body:
            return False
    return True


def _timing_bound(record: dict, audit_sha256: str) -> bool:
    if set(record) != {
        "started_utc", "finished_utc", "monotonic_elapsed_seconds", "exit_status",
        "audit_sha256", "external_calls", "cleaner_source",
    }:
        return False
    try:
        started = datetime.fromisoformat(record["started_utc"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(record["finished_utc"].replace("Z", "+00:00"))
        elapsed = record["monotonic_elapsed_seconds"]
    except (KeyError, TypeError, ValueError):
        return False
    return (
        type(elapsed) in (int, float) and elapsed > 0
        and abs((finished - started).total_seconds() - elapsed) <= 1.0
        and record["exit_status"] == 0
        and record["audit_sha256"] == audit_sha256
        and record["external_calls"] == {"attester": 1, "codex_decider": 1, "claude_decider": 1}
        and record["cleaner_source"] == "deterministic-reported-candidate"
    )


def validate(artifact_path: Path, repo: Path) -> None:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if set(artifact) != {
        "acceptance_kind", "acceptance_scope", "audit", "timing", "providers",
        "source_sha256", "tests",
    }:
        raise ValueError("fallback acceptance top-level schema mismatch")
    if artifact["acceptance_kind"] != "arbitration-original-fallback-v2":
        raise ValueError("unsupported fallback acceptance kind")
    if artifact["acceptance_scope"] != SCOPE:
        raise ValueError("fallback acceptance claim scope mismatch")
    if set(artifact["source_sha256"]) != SOURCES:
        raise ValueError("fallback acceptance source set mismatch")
    for relative, digest in artifact["source_sha256"].items():
        if not _is_sha256(digest) or _sha256(repo / relative) != digest:
            raise ValueError(f"fallback acceptance source hash mismatch: {relative}")

    audit_meta = artifact["audit"]
    if set(audit_meta) != {"path", "sha256", "snapshot", "cleaning", "result"}:
        raise ValueError("fallback audit metadata schema mismatch")
    audit_path = _evidence_path(repo, audit_meta["path"])
    if _sha256(audit_path) != audit_meta["sha256"]:
        raise ValueError("fallback audit digest mismatch")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if not (
        audit_meta["cleaning"] == audit.get("cleaning") == "original-attested"
        and audit_meta["snapshot"] == audit.get("snapshot")
        and audit_meta["result"] == audit.get("outcome")
        and _cleaned_digest_bound(audit.get("cleaned", {}))
        and audit["cleaned"]["statements"] != audit["raw_input"]["options"]
        and _attestation_bound(audit)
        and _decider_prompts_bound(audit)
    ):
        raise ValueError("fallback audit does not prove exact original delivery")

    timing_meta = artifact["timing"]
    if set(timing_meta) != {"path", "sha256"}:
        raise ValueError("fallback timing metadata schema mismatch")
    timing_path = _evidence_path(repo, timing_meta["path"])
    if _sha256(timing_path) != timing_meta["sha256"]:
        raise ValueError("fallback timing digest mismatch")
    if not _timing_bound(json.loads(timing_path.read_text()), audit_meta["sha256"]):
        raise ValueError("fallback timing record mismatch")

    providers = artifact["providers"]
    if set(providers) != {"codex_cli", "claude_cli", "attester_model", "decider_models"}:
        raise ValueError("fallback provider metadata schema mismatch")
    if not all(isinstance(value, str) and value for value in (providers["codex_cli"], providers["claude_cli"])):
        raise ValueError("fallback provider versions are missing")
    if providers["attester_model"] != engines.ATTESTER_MODEL or providers["decider_models"] != {
        "codex": engines.CodexEngine().default_model,
        "claude": engines.ClaudeEngine().default_model,
    }:
        raise ValueError("fallback configured provider models mismatch")
    if artifact["tests"] != {"full_suite": "1077 passed", "exit_status": 0}:
        raise ValueError("fallback acceptance test record mismatch")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_arbitration_fallback_acceptance.py ARTIFACT REPO")
    validate(Path(sys.argv[1]), Path(sys.argv[2]).resolve())
    print("arbitration original-fallback acceptance: valid")


if __name__ == "__main__":
    main()
