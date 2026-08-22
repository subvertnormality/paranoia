#!/usr/bin/env python3
"""Retain and bind the issue-58 public-handler acceptance run."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from paranoia_local import class_closure as cc
from paranoia_local import handlers


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "claim_discovery_timeout_acceptance_2026-08-22.json"
BASE_REVISION = "c5219e5c3a779018c66429ebb84137f2ec6f71ee"
PLAN_REVISION = "c17c58e40dec7e660ec39f6d2a95e9f1d5ac1e7a"
PLAN_REPO_PATH = "dataset/certification/A1-PIT-SYMBOL-RESOLUTION_plan_contract.md"
PLAN_SHA256 = "706953595c48d12a0e421266b77bdf9c18cd1db2fd93b3ac7a1724b472a0b1f0"
LINEAGE_ID = "issue-58-public-acceptance-bound"
STAKES = (
    "Trusted single operator and OS; the historical plan, repository, and fetched "
    "pages are untrusted data; public HTTP(S) is the network boundary; no hostile "
    "local race, repository-selected execution, compromised OS, or multi-tenancy; "
    "false claim clearance and evidence misbinding are high impact; recoverable "
    "blocking is acceptable."
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8", "surrogateescape"))


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True,
    ).stdout


def _source_hashes(source_revision: str) -> dict[str, str]:
    names = _git("diff", "--name-only", BASE_REVISION, source_revision).decode().splitlines()
    return {
        name: _sha256_bytes(_git("show", f"{source_revision}:{name}"))
        for name in names
    }


def _diff_metrics(source_revision: str) -> dict[str, Any]:
    rows = []
    additions = deletions = 0
    for line in _git("diff", "--numstat", BASE_REVISION, source_revision).decode().splitlines():
        added, removed, path = line.split("\t", 2)
        row = {"path": path, "additions": int(added), "deletions": int(removed)}
        rows.append(row)
        additions += row["additions"]
        deletions += row["deletions"]
    return {
        "base_revision": BASE_REVISION,
        "files": rows,
        "file_count": len(rows),
        "additions": additions,
        "deletions": deletions,
    }


def _module_lines(source_revision: str) -> dict[str, int]:
    paths = [
        "AGENTS.md", "README.md", "docs/claim_verification.md",
        "src/paranoia_local/handlers.py", "tests/test_plan_claims.py",
    ]
    return {
        path: len(_git("show", f"{source_revision}:{path}").decode(
            "utf-8", "surrogateescape"
        ).splitlines())
        for path in paths
    }


def _result_text(audit: dict[str, Any], state_root: Path) -> str:
    lineage = cc.load_lineage(
        state_root, LINEAGE_ID, stamp="acceptance-replay", mode=cc.PLAN_MODE,
    )
    register_status = str(audit["register_status"])
    minted = [
        token.strip()
        for token in register_status.partition(" — NEW ")[2].split(", NEW ")
        if token.strip()
    ]
    staged_attempts = [
        row for row in audit["attempt_ledger"]
        if not str(row.get("role", "")).startswith("claim-")
    ]
    trailer = handlers._staged_success_trailer(
        lineage=lineage,
        state=lineage.review_state,
        mode=cc.PLAN_MODE,
        register_status=register_status,
        minted=minted,
        attempts=staged_attempts,
        claims_enabled=True,
    )
    session = audit.get("session_ref")
    footer = (
        f"\n\n---\n_paranoia-local · engine=codex · session_ref=`{session}` — "
        "to dispute a finding, call `rebut` with this session_ref and your "
        "counter-evidence._"
    )
    return f"{audit['text']}{footer}\n\n{trailer}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--lineage", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--invocation", type=Path, required=True)
    args = parser.parse_args()

    audit_bytes = args.audit.read_bytes()
    lineage_bytes = args.lineage.read_bytes()
    plan_bytes = args.plan.read_bytes()
    invocation_bytes = args.invocation.read_bytes()
    audit = json.loads(audit_bytes)
    lineage = json.loads(lineage_bytes)
    plan_text = plan_bytes.decode("utf-8", "surrogateescape")
    invocation = json.loads(invocation_bytes)
    if _sha256_bytes(plan_bytes) != PLAN_SHA256:
        raise SystemExit("the supplied plan is not the issue-58 historical input")
    if audit.get("lineage") != LINEAGE_ID or audit.get("round") != 1:
        raise SystemExit("the supplied audit is not the issue-58 public round")
    result_text = _result_text(audit, args.lineage.parents[1])
    if invocation.get("result_text") != result_text:
        raise SystemExit("recorded public result does not match deterministic state replay")
    source_revision = invocation.get("source_revision_before")
    if (
        not isinstance(source_revision, str)
        or invocation.get("source_revision_after") != source_revision
        or invocation.get("source_status_before")
        or invocation.get("source_status_after")
    ):
        raise SystemExit("acceptance invocation was not bound to one clean source revision")
    executable = invocation.get("effective_executable")
    state_root = invocation.get("effective_state_root")
    if (
        not isinstance(executable, str)
        or Path(executable).resolve() != Path(invocation.get("executable", "")).resolve()
        or not isinstance(state_root, str)
        or Path(state_root).resolve() != args.lineage.parents[1].resolve()
    ):
        raise SystemExit("acceptance invocation did not use its recorded executable and state root")
    if any(
        not isinstance(row.get("requested_timeout_sec"), int)
        or not isinstance(row.get("duration_ms"), int)
        or row["duration_ms"] < 0
        or not isinstance(row.get("returncode"), int)
        or any(
            not isinstance(row.get(f"{channel}_sha256"), str)
            or len(row[f"{channel}_sha256"]) != 64
            or not isinstance(row.get(f"{channel}_excerpt"), str)
            for channel in ("raw", "failure_detail", "stderr")
        )
        for row in audit["attempt_ledger"]
    ):
        raise SystemExit("production attempt ledger lacks required execution telemetry")
    role_timeouts = {
        row["role"]: row["requested_timeout_sec"]
        for row in audit["attempt_ledger"]
        if str(row.get("role", "")).startswith("claim-")
    }
    record = {
        "schema_version": 1,
        "accepted_at": audit["timestamp"],
        "claim": (
            "The public critique_plan handler completed claim discovery, binding, and "
            "cold attestation for the exact historical issue-58 plan after the claim "
            "phase exceeded 300 seconds; it persisted the resulting claim state and "
            "continued into structural review without a claim execution timeout."
        ),
        "non_claims": [
            "This run does not claim that the historical plan converged; its retained combined verdict is BLOCKED.",
            "This run does not establish a universal latency bound for every provider, plan, or network response.",
            "The recorded elapsed value is the handler-measured claim phase, not an estimate of total wall-clock runtime.",
        ],
        "source": {
            "revision": source_revision,
            "clean_before_and_after": True,
            "hashes": _source_hashes(source_revision),
            "diff": _diff_metrics(source_revision),
            "module_lines": _module_lines(source_revision),
        },
        "input": {
            "repository_revision": PLAN_REVISION,
            "path": PLAN_REPO_PATH,
            "sha256": PLAN_SHA256,
            "bytes": len(plan_bytes),
            "lines": len(plan_text.splitlines()),
            "text": plan_text,
        },
        "invocation": invocation | {
            "public_handler": "paranoia_local.handlers.critique_plan",
            "claim_role_timeouts_seconds": role_timeouts,
        },
        "observed": {
            "claim_duration_ms": audit["claim_duration_ms"],
            "claim_model_calls": audit["claim_model_calls"],
            "claim_status": audit["claim_status"],
            "claim_counts": audit["claim_counts"],
            "ordered_attempt_roles": [row["role"] for row in audit["attempt_ledger"]],
            "result_sha256": _sha256_text(result_text),
            "result_text": result_text,
        },
        "production_audit_sha256": _sha256_bytes(audit_bytes),
        "production_audit": audit,
        "durable_lineage_sha256": _sha256_bytes(lineage_bytes),
        "durable_lineage": lineage,
        "invocation_record_sha256": _sha256_bytes(invocation_bytes),
    }
    OUTPUT.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
