#!/usr/bin/env python3
"""Fail unless an arbitration acceptance summary is derived from its exact audit."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
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


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _tracked_evidence(repo: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("legacy audit path must be repository-relative")
    root = repo.resolve()
    path = (root / relative).resolve()
    if path == root or root not in path.parents:
        raise ValueError("legacy audit path escapes repository")
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative],
        cwd=repo, capture_output=True,
    )
    if tracked.returncode or not path.is_file():
        raise ValueError(f"legacy audit is not tracked evidence: {relative}")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _invoked_count(attempts: list[dict]) -> int:
    values = [attempt.get("invoked") for attempt in attempts]
    if any(type(value) is not bool for value in values):
        raise ValueError("every invoked ledger value must be an exact boolean")
    return sum(values)


def validate(artifact_path: Path, repo: Path) -> None:
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if set(artifact) != {"delivery_metrics", "primary_path"}:
        raise ValueError("legacy acceptance top-level schema mismatch")
    if set(artifact["delivery_metrics"]) != {"production_diff", "largest_production_modules"}:
        raise ValueError("legacy delivery metrics schema mismatch")
    claimed_diff = artifact["delivery_metrics"]["production_diff"]
    diff_fields = {"files", "lines_added", "lines_removed", "net_lines"}
    if set(claimed_diff) != diff_fields or any(type(claimed_diff[key]) is not int for key in diff_fields):
        raise ValueError("legacy production diff schema mismatch")
    claimed_modules = artifact["delivery_metrics"]["largest_production_modules"]
    if (
        not isinstance(claimed_modules, list) or len(claimed_modules) != 6
        or any(
            not isinstance(row, dict) or set(row) != {"path", "lines"}
            or not isinstance(row["path"], str) or type(row["lines"]) is not int or row["lines"] < 0
            for row in claimed_modules
        )
    ):
        raise ValueError("legacy largest-module schema mismatch")
    primary = artifact["primary_path"]
    if set(primary) != {
        "cleaning", "result", "selected", "rounds", "snapshot", "source_commit",
        "production_source_sha256", "refs_moved", "model_calls", "captured_packets",
        "captured_urls", "research_digest", "decisive_evidence", "audit",
        "audit_reconciliation", "preceding_failed_closed_attempt",
    }:
        raise ValueError("legacy primary-path schema mismatch")
    string_fields = ("cleaning", "result", "selected", "snapshot", "research_digest", "audit")
    if any(not isinstance(primary[key], str) or not primary[key] for key in string_fields):
        raise ValueError("legacy primary-path value schema mismatch")
    if type(primary["refs_moved"]) is not bool:
        raise ValueError("legacy refs-moved schema mismatch")
    if not _is_sha256(primary["research_digest"]):
        raise ValueError("legacy packet digest schema mismatch")
    for key in ("captured_packets", "captured_urls"):
        if not isinstance(primary[key], list) or any(
            not isinstance(value, str) or not value for value in primary[key]
        ):
            raise ValueError(f"legacy {key.replace('_', '-')} schema mismatch")
    reconciliation = primary["audit_reconciliation"]
    calls = primary["model_calls"]
    if set(calls) != {"research", "deciders", "cleaner", "attester", "total"}:
        raise ValueError("legacy model-call schema mismatch")
    for group in ("research", "deciders"):
        if set(calls[group]) != ENGINES or any(
            type(calls[group][engine]) is not int or calls[group][engine] < 0
            for engine in ENGINES
        ):
            raise ValueError(f"legacy {group} call schema mismatch")
    if any(type(calls[key]) is not int or calls[key] < 0 for key in ("cleaner", "attester", "total")):
        raise ValueError("legacy model-call count schema mismatch")
    if type(primary["rounds"]) is not int or primary["rounds"] < 0:
        raise ValueError("legacy round count schema mismatch")
    if set(primary["decisive_evidence"]) != ENGINES or any(
        not isinstance(primary["decisive_evidence"][engine], str)
        or not primary["decisive_evidence"][engine] for engine in ENGINES
    ):
        raise ValueError("legacy decisive-evidence schema mismatch")
    if set(reconciliation) != {
        "audit_sha256", "research_attempts", "framing_attempts", "decider_attempts",
        "total_provider_calls", "packet_count", "packet_digest_matches",
        "packet_ids_match", "production_hashes_match",
    }:
        raise ValueError("legacy reconciliation schema mismatch")
    if set(reconciliation["research_attempts"]) != ENGINES or any(
        type(reconciliation["research_attempts"][engine]) is not int
        or reconciliation["research_attempts"][engine] < 0 for engine in ENGINES
    ):
        raise ValueError("legacy research reconciliation schema mismatch")
    if any(
        type(reconciliation[key]) is not int or reconciliation[key] < 0
        for key in ("framing_attempts", "decider_attempts", "total_provider_calls", "packet_count")
    ):
        raise ValueError("legacy reconciliation count schema mismatch")
    if not _is_sha256(reconciliation["audit_sha256"]) or any(
        type(reconciliation[key]) is not bool
        for key in ("packet_digest_matches", "packet_ids_match", "production_hashes_match")
    ):
        raise ValueError("legacy reconciliation value schema mismatch")
    audit_path = _tracked_evidence(repo, primary["audit"])
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    preceding = primary["preceding_failed_closed_attempt"]
    if set(preceding) != {"result", "reason", "cleaning", "snapshot", "audit", "audit_sha256"}:
        raise ValueError("legacy preceding-attempt schema mismatch")
    if any(
        not isinstance(preceding[key], str) or not preceding[key]
        for key in ("result", "reason", "cleaning", "snapshot", "audit")
    ) or not _is_sha256(preceding["audit_sha256"]):
        raise ValueError("legacy preceding-attempt value schema mismatch")
    preceding_path = _tracked_evidence(repo, preceding["audit"])
    preceding_audit = json.loads(preceding_path.read_text(encoding="utf-8"))

    audit_types = {
        "outcome": str, "selected": str, "snapshot": str, "cleaning": str,
        "refs_moved": bool,
    }
    if any(type(audit.get(key)) is not expected for key, expected in audit_types.items()):
        raise ValueError("legacy governing audit value schema mismatch")
    preceding_types = {"outcome": str, "reason": str, "snapshot": str, "cleaning": str}
    if any(
        type(preceding_audit.get(key)) is not expected
        for key, expected in preceding_types.items()
    ):
        raise ValueError("legacy preceding audit value schema mismatch")

    if _sha256(audit_path) != reconciliation["audit_sha256"]:
        raise ValueError("audit_sha256 does not match referenced audit")
    source_hashes = primary["production_source_sha256"]
    source_commit = primary["source_commit"]
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("legacy source commit schema mismatch")
    if set(source_hashes) != PRODUCTION_SOURCES or any(
        not _is_sha256(value) for value in source_hashes.values()
    ):
        raise ValueError("production_source_sha256 does not name the complete source set")
    for relative, expected in source_hashes.items():
        result = subprocess.run(
            ["git", "show", f"{source_commit}:{relative}"], cwd=repo, capture_output=True,
        )
        if result.returncode or hashlib.sha256(result.stdout).hexdigest() != expected:
            raise ValueError(f"historical production hash mismatch: {relative}")

    parent = subprocess.run(
        ["git", "rev-parse", f"{source_commit}^1"], cwd=repo, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--numstat", parent, source_commit, "--", *sorted(PRODUCTION_SOURCES)],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    added = sum(int(row.split("\t", 2)[0]) for row in diff)
    removed = sum(int(row.split("\t", 2)[1]) for row in diff)
    if artifact["delivery_metrics"]["production_diff"] != {
        "files": len(diff), "lines_added": added, "lines_removed": removed,
        "net_lines": added - removed,
    }:
        raise ValueError("legacy production diff metrics mismatch")
    paths = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", source_commit, "src/paranoia_local"],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    modules = []
    for path in paths:
        if path.endswith(".py"):
            body = subprocess.run(
                ["git", "show", f"{source_commit}:{path}"], cwd=repo, check=True,
                capture_output=True, text=True,
            ).stdout
            modules.append({"path": path, "lines": len(body.splitlines())})
    modules.sort(key=lambda row: (-row["lines"], row["path"]))
    if artifact["delivery_metrics"]["largest_production_modules"] != modules[:6]:
        raise ValueError("legacy largest production modules mismatch")

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
