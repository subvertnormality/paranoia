#!/usr/bin/env python3
"""Fail unless an arbitration acceptance summary is derived from its exact audit."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PRODUCTION_SOURCES = frozenset({
    "src/paranoia_local/arbitrate_handler.py",
    "src/paranoia_local/arbitration.py",
    "src/paranoia_local/arbitration_research.py",
    "src/paranoia_local/engines.py",
    "src/paranoia_local/evidence.py",
    "src/paranoia_local/external_sources.py",
    "src/paranoia_local/handlers.py",
    "src/paranoia_local/plan_claims.py",
    "src/paranoia_local/review_census.py",
})
ENGINES = frozenset({"codex", "claude"})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _invoked_count(attempts: list[dict]) -> int:
    values = [attempt.get("invoked") for attempt in attempts]
    if any(type(value) is not bool for value in values):
        raise ValueError("every invoked ledger value must be an exact boolean")
    return sum(values)


def validate(artifact_path: Path, repo: Path) -> None:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    primary = artifact["primary_path"]
    reconciliation = primary["audit_reconciliation"]
    audit_path = Path(primary["audit"])
    if not audit_path.is_file():
        raise ValueError(f"referenced audit does not exist: {audit_path}")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    preceding = primary["preceding_failed_closed_attempt"]
    preceding_path = Path(preceding["audit"])
    if not preceding_path.is_file():
        raise ValueError(f"referenced preceding audit does not exist: {preceding_path}")
    preceding_audit = json.loads(preceding_path.read_text(encoding="utf-8"))

    if _sha256(audit_path) != reconciliation["audit_sha256"]:
        raise ValueError("audit_sha256 does not match referenced audit")
    source_hashes = primary["production_source_sha256"]
    if set(source_hashes) != PRODUCTION_SOURCES:
        raise ValueError("production_source_sha256 does not name the complete source set")
    for relative, expected in source_hashes.items():
        if _sha256(repo / relative) != expected:
            raise ValueError(f"production hash mismatch: {relative}")

    research_rows = audit["research"]["runs"]
    research_engines = [row["engine"] for row in research_rows]
    if len(research_engines) != len(set(research_engines)) or set(research_engines) != ENGINES:
        raise ValueError("research runs must contain each engine exactly once")
    research_calls = {row["engine"]: _invoked_count(row["attempts"])
                      for row in research_rows}
    if any(row.get("calls") != research_calls[row["engine"]] for row in research_rows):
        raise ValueError("research run calls disagree with invoked attempt ledger")
    phase_roles = [item["role"] for item in audit["phase_attempts"]]
    if phase_roles not in (["cleaner", "attester"],
                            ["cleaner", "attester", "cleaner", "attester"]):
        raise ValueError("phase attempts must contain one or two ordered cleaner/attester pairs")
    framing_calls = {role: _invoked_count([item for item in audit["phase_attempts"]
                                          if item["role"] == role])
                     for role in ("cleaner", "attester")}
    decider_calls = {engine: 0 for engine in ENGINES}
    for round_record in audit["rounds"]:
        if set(round_record) != ENGINES:
            raise ValueError("every round must contain each decider exactly once")
        for engine, cast in round_record.items():
            decider_calls[engine] += _invoked_count(cast["attempts"])
    total_calls = sum(research_calls.values()) + sum(framing_calls.values()) + sum(decider_calls.values())
    packet_bytes = audit["research"]["packets"].encode("utf-8", errors="surrogatepass")
    computed_packet_digest = hashlib.sha256(packet_bytes).hexdigest()
    packets = json.loads(packet_bytes)
    packet_ids = [item["packet_id"] for item in packets]
    packet_urls = sorted({item["source"]["url"] for item in packets})
    decisive = {engine: audit["rounds"][-1][engine]["decisive"] for engine in ENGINES}

    expected_calls = primary["model_calls"]
    checks = {
        "research attempts": research_calls == expected_calls["research"],
        "cleaner attempts": framing_calls["cleaner"] == expected_calls["cleaner"],
        "attester attempts": framing_calls["attester"] == expected_calls["attester"],
        "decider attempts": decider_calls == expected_calls["deciders"],
        "total calls": total_calls == expected_calls["total"],
        "packet count": len(packets) == len(primary["captured_packets"]),
        "packet ids": packet_ids == primary["captured_packets"],
        "packet urls": packet_urls == primary["captured_urls"],
        "packet digest": computed_packet_digest == audit["research"]["digest"] == primary["research_digest"],
        "decisive evidence": decisive == primary["decisive_evidence"],
        "audit outcome": audit["outcome"] == primary["result"],
        "audit selection": audit["selected"] == primary["selected"],
        "audit snapshot": audit["snapshot"] == primary["snapshot"],
        "cleaning": audit["cleaning"] == primary["cleaning"],
        "round count": len(audit["rounds"]) == primary["rounds"],
        "refs moved": audit["refs_moved"] is primary["refs_moved"],
        "preceding audit digest": _sha256(preceding_path) == preceding["audit_sha256"],
        "preceding result": preceding_audit["outcome"] == preceding["result"],
        "preceding reason": preceding_audit["reason"] == preceding["reason"],
        "preceding cleaning": preceding_audit["cleaning"] == preceding["cleaning"],
        "preceding snapshot": preceding_audit["snapshot"] == preceding["snapshot"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("acceptance reconciliation failed: " + ", ".join(failed))

    expected_reconciliation = {
        "research_attempts": research_calls,
        "framing_attempts": sum(framing_calls.values()),
        "decider_attempts": sum(decider_calls.values()),
        "total_provider_calls": total_calls,
        "packet_count": len(packets),
    }
    for key, value in expected_reconciliation.items():
        if reconciliation[key] != value:
            raise ValueError(f"reconciliation field mismatch: {key}")
    for key in ("packet_digest_matches", "packet_ids_match", "production_hashes_match"):
        if reconciliation.get(key) is not True:
            raise ValueError(f"reconciliation field mismatch: {key}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_arbitration_acceptance.py ARTIFACT REPO")
    try:
        validate(Path(sys.argv[1]), Path(sys.argv[2]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
