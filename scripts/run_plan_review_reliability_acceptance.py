#!/usr/bin/env python3
"""Retain one real-provider public critique_plan round for issues 81-83."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import class_closure as cc
from paranoia_local import engines, handlers, plan_claims as pc, review_census as rc
from paranoia_local import staged_protocol as sp


ARTIFACT = ROOT / "docs/plan_review_reliability_acceptance_2026-08-30.json"
LINEAGE = "issues-81-83-real-plan-acceptance"
SOURCES = (
    "AGENTS.md", "README.md", "docs/tool-reference.md",
    "src/paranoia_local/handlers.py", "src/paranoia_local/plan_claims.py",
    "src/paranoia_local/prompts.py", "src/paranoia_local/review_census.py",
    "src/paranoia_local/staged_protocol.py",
    "tests/test_plan_claims.py", "tests/test_prompts.py",
    "tests/test_review_census.py", "tests/test_staged_protocol.py",
    "scripts/run_plan_review_reliability_acceptance.py",
)
VALIDATION_SOURCES = ("scripts/run_plan_review_reliability_acceptance.py",)
PLAN = """# Plan-review reliability acceptance

## Scope

Exercise the current public `critique_plan` handler against this repository snapshot. The run is
an acceptance probe only: it does not authorize repository edits or claim that a single review
proves future provider behavior.

## Acceptance

The handler must complete a real Codex provider round, persist its claim and structural state,
render the same durable trailer recorded in its audit log, and retain every provider attempt with
its role, outcome, requested timeout, duration, return code, and bounded channel digests.
"""
STAKES = (
    "One trusted operator and OS; plan and repository bytes are untrusted data; no hostile local "
    "race or repository execution; one small acceptance plan and ordinary provider latency; false "
    "clearance or missing durable diagnostics is high impact; recoverable blocking is acceptable; "
    "exclude multi-tenancy, corrupted-state recovery, and hostile local processes."
)


def _run(*args: str) -> str:
    return subprocess.run(
        list(args), cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode("utf-8", "surrogatepass"))


def _deterministic_checks(root: Path = ROOT) -> dict:
    first = cc.TrackedClass(
        "class-a", "first invariant", cc.MAJOR, 1, cc.OPEN, procedure="inspect",
    )
    second = cc.TrackedClass(
        "class-b", "second invariant", cc.MAJOR, 2, cc.OPEN, procedure="inspect",
    )
    control = rc.normalize_correction_control({
        "last_round":7,
        "correction_control":{"version":1, "classes":{"class-a":{
            "reset_round":6, "reopen_count":2, "last_session_ref":"session-a",
        }}},
    }, [first, second])
    decision = {
        "role":"census",
        "governing_findings":[{
            "id":"G1", "severity":"MAJOR", "summary":"co-asserting defect",
            "evidence":["plan:3"], "remedy":"repair every site",
            "source_ids":["domain:F1", "execution:F2"],
            "classification":{"kind":"one_off", "reason":"acceptance fixture"},
        }],
        "debt_outcomes":[], "class_actions":[],
    }
    materialized = sp.materialize_decision_value(
        decision, mode=cc.PLAN_MODE, role="census",
        source_ids=["domain:F1", "execution:F2"],
        source_severities={"domain:F1":"MAJOR", "execution:F2":"MAJOR"},
        source_evidence={
            "domain:F1":["plan:1", "plan:2"],
            "execution:F2":["plan:2", "plan:3"],
        },
    )

    runtime = Path(tempfile.mkdtemp(prefix="paranoia-predecessor-preflight-"))
    state_root = runtime / "state"
    log_root = runtime / "logs"
    old_default = cc.default_state_root
    old_profile = engines.require_evidence_profile
    old_git_profile = handlers.inert_git.require_supported_version
    cc.default_state_root = lambda: state_root
    engines.require_evidence_profile = lambda engine: None
    handlers.inert_git.require_supported_version = lambda: None
    try:
        claim_state = pc.empty_state()
        claim_state.update(
            rounds=1, plan_snapshot="# Plan\n", plan_digest="old",
            claims={
                "old-refuted":{
                    "claim_id":"old-refuted", "kind":"fact", "scope":"external",
                    "anchor":"removed wording", "proposition":"old proposition",
                    "verdict":"unverified", "replacement":None,
                    "rationale":"stale old-writer remediation", "evidence":[],
                },
                "old-unverified":{
                    "claim_id":"old-unverified", "kind":"behavior", "scope":"external",
                    "anchor":"changed wording", "proposition":"another old proposition",
                    "verdict":"unverified", "replacement":None,
                    "rationale":"another stale remediation", "evidence":[],
                },
            },
            debt=pc.AuditError(
                "indexed binding passage is not in captured text", failure_phase="binding",
            ).debt(1),
        )
        review_state = rc.normalize_state(None, stakes="s", snapshot="old")
        review_state.update(
            phase="correction", last_round=1,
            debt=[{
                "id":"D1", "finding_id":"F1", "status":"open",
                "severity":cc.MAJOR, "summary":"historic occurrence",
                "evidence":[], "remedy":"repair it", "source_ids":[],
                "class_ids":["class-a"], "first_round":1, "last_round":1,
            }],
            correction_control={"version":1, "classes":{"class-a":{}}},
        )
        cc.save_lineage(state_root, cc.Lineage(
            "predecessor-preflight-acceptance", mode=cc.PLAN_MODE, rounds=1,
            classes={first.class_id:first}, review_state=review_state,
            claim_state=claim_state,
        ))
        result = handlers.critique_plan({
            "repo_path":str(root), "plan_text":"# Plan\n",
            "lineage":"predecessor-preflight-acceptance", "round":2, "stakes":"s",
        }, engine=engines.CodexEngine(), log_dir=log_root, now=lambda: "PREFLIGHT")
        audit = json.loads(next(log_root.glob("*.json")).read_text(encoding="utf-8"))
    finally:
        cc.default_state_root = old_default
        engines.require_evidence_profile = old_profile
        handlers.inert_git.require_supported_version = old_git_profile
    if (
        "CLAIM-REGISTER: AUDIT-FAILED — 2 retained historical claim rows" not in result
        or "predecessor claim rows are non-adjudicated history" not in result
        or "last accepted inventory" in result
        or "old-writer remediation" in result
        or "another stale remediation" in result
        or audit.get("attempt_ledger") != []
        or audit.get("claim_last_accepted_counts") is not None
        or audit.get("claim_nonadjudicated_count") != 2
    ):
        raise ValueError("public predecessor preflight is not non-adjudicated and zero-call")
    return {
        "correction_control":control,
        "evidence_union":materialized["findings"][0]["evidence"],
        "debt_evidence_union":materialized["debt"][0]["evidence"],
        "predecessor_preflight":{
            "result_sha256":_sha_text(result),
            "rendered_trailer":audit["rendered_trailer"],
            "claim_audit_failed":audit["claim_audit_failed"],
            "claim_last_accepted_counts":audit["claim_last_accepted_counts"],
            "claim_nonadjudicated_count":audit["claim_nonadjudicated_count"],
            "provider_attempts":len(audit["attempt_ledger"]),
        },
    }


def validate_artifact(value: dict, root: Path = ROOT) -> None:
    expected = {
        "acceptance_kind", "version", "date", "source_revision", "source_sha256",
        "provider", "plan", "stakes", "result_text", "result_sha256", "audit",
        "durable_lineage", "assertions", "validation",
    }
    if set(value) != expected:
        raise ValueError("acceptance fields are not closed and exact")
    if (
        value["acceptance_kind"] != "plan-review-reliability-real-provider-v1"
        or value["version"] != 2
    ):
        raise ValueError("wrong acceptance kind")
    revision = value["source_revision"]
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("source revision is not a full commit")
    if set(value["source_sha256"]) != set(SOURCES):
        raise ValueError("source inventory is not exact")
    for relative, digest in value["source_sha256"].items():
        committed = subprocess.run(
            ["git", "show", f"{revision}:{relative}"], cwd=root, check=True,
            stdout=subprocess.PIPE,
        ).stdout
        if _sha_bytes(committed) != digest:
            raise ValueError(f"source binding mismatch for {relative}")
        if relative not in VALIDATION_SOURCES and (root / relative).read_bytes() != committed:
            raise ValueError(f"current production source differs from real-route snapshot: {relative}")
    validation = value["validation"]
    if set(validation) != {"revision", "source_sha256", "checks"}:
        raise ValueError("validation binding is not closed")
    validation_revision = validation["revision"]
    if not isinstance(validation_revision, str) or len(validation_revision) != 40:
        raise ValueError("validation revision is not a full commit")
    if set(validation["source_sha256"]) != set(VALIDATION_SOURCES):
        raise ValueError("validation source inventory is not exact")
    for relative, digest in validation["source_sha256"].items():
        committed = subprocess.run(
            ["git", "show", f"{validation_revision}:{relative}"], cwd=root,
            check=True, stdout=subprocess.PIPE,
        ).stdout
        if _sha_bytes(committed) != digest or (root / relative).read_bytes() != committed:
            raise ValueError(f"validation source binding mismatch for {relative}")
    if validation["checks"] != _deterministic_checks(root):
        raise ValueError("deterministic lifecycle checks differ from the retained acceptance")
    if value["plan"] != PLAN or value["stakes"] != STAKES:
        raise ValueError("acceptance input changed")
    if value["result_sha256"] != _sha_text(value["result_text"]):
        raise ValueError("result digest mismatch")
    audit = value["audit"]
    if audit.get("error") is not False or audit.get("returncode") != 0:
        raise ValueError("public handler did not complete")
    attempts = audit.get("attempt_ledger")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("attempt ledger is absent")
    roles = [row.get("role") for row in attempts]
    if "claim-discovery" not in roles or not any(
        role in {"census-domain", "census-behaviour", "census-integrity"}
        for role in roles
    ):
        raise ValueError("real claim and structural routes were not both exercised")
    for row in attempts:
        if row.get("outcome") not in {"completed", "validation-invalid"}:
            raise ValueError("acceptance contains an execution failure")
        if type(row.get("requested_timeout_sec")) is not int:
            raise ValueError("attempt timeout telemetry is absent")
        if type(row.get("duration_ms")) is not int or row["duration_ms"] < 0:
            raise ValueError("attempt duration telemetry is absent")
        if row.get("returncode") is None:
            raise ValueError("attempt return code is absent")
        for channel in ("raw", "failure_detail", "stderr"):
            if not isinstance(row.get(f"{channel}_sha256"), str):
                raise ValueError(f"attempt {channel} digest is absent")
    trailer = audit.get("rendered_trailer")
    if not isinstance(trailer, str) or not value["result_text"].endswith(trailer):
        raise ValueError("public result and durable trailer differ")
    lineage = value["durable_lineage"]
    if lineage.get("lineage_id") != LINEAGE or lineage.get("mode") != cc.PLAN_MODE:
        raise ValueError("durable lineage identity is wrong")
    if lineage.get("claim_state") != audit.get("durable_claim_state"):
        raise ValueError("audit and durable claim state differ")
    if value["assertions"] != [
        "The public critique_plan handler completed through the real Codex provider route.",
        "The durable lineage, rendered trailer, and audit attempt ledger were retained exactly.",
        "This probe does not claim that every future provider response will validate or converge.",
    ]:
        raise ValueError("acceptance claims changed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--output", type=Path, default=ARTIFACT)
    parser.add_argument("--augment-existing", action="store_true")
    args = parser.parse_args()
    revision = _run("git", "rev-parse", "HEAD")
    if args.augment_existing:
        value = json.loads(args.output.read_text(encoding="utf-8"))
        value["version"] = 2
        value["validation"] = {
            "revision":revision,
            "source_sha256":{
                relative:_sha_bytes((ROOT / relative).read_bytes())
                for relative in VALIDATION_SOURCES
            },
            "checks":_deterministic_checks(ROOT),
        }
        validate_artifact(value, ROOT)
        args.output.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"augmented {args.output} without a provider call")
        return 0
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", *SOURCES], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout
    if dirty:
        raise RuntimeError("commit every acceptance-bound source before generation")
    runtime = Path(tempfile.mkdtemp(prefix="paranoia-plan-reliability-acceptance-"))
    state_root = runtime / "state"
    log_root = runtime / "logs"
    cc.default_state_root = lambda: state_root
    engine = engines.CodexEngine()
    engine.binary = args.codex
    result = handlers.critique_plan({
        "repo_path":str(ROOT), "plan_text":PLAN, "lineage":LINEAGE,
        "round":1, "stakes":STAKES,
    }, engine=engine, log_dir=log_root, now=lambda: "20260830TACCEPTANCE")
    logs = list(log_root.glob("*.json"))
    if len(logs) != 1:
        raise RuntimeError("public handler did not emit exactly one audit")
    audit = json.loads(logs[0].read_text(encoding="utf-8"))
    durable = {
        "lineage_id":LINEAGE,
        **cc._to_json(cc.load_lineage(
            state_root, LINEAGE, stamp="reload", mode=cc.PLAN_MODE,
        )),
    }
    audit["durable_claim_state"] = durable["claim_state"]
    value = {
        "acceptance_kind":"plan-review-reliability-real-provider-v1",
        "version":2, "date":"2026-08-30", "source_revision":revision,
        "source_sha256":{
            relative:_sha_bytes((ROOT / relative).read_bytes()) for relative in SOURCES
        },
        "provider":{
            "engine":"codex", "executable":args.codex,
            "cli_version":_run(args.codex, "--version"),
            "model":engine.default_model, "effort":"high", "web_search":True,
        },
        "plan":PLAN, "stakes":STAKES, "result_text":result,
        "result_sha256":_sha_text(result), "audit":audit,
        "durable_lineage":durable,
        "validation":{
            "revision":revision,
            "source_sha256":{
                relative:_sha_bytes((ROOT / relative).read_bytes())
                for relative in VALIDATION_SOURCES
            },
            "checks":_deterministic_checks(ROOT),
        },
        "assertions":[
            "The public critique_plan handler completed through the real Codex provider route.",
            "The durable lineage, rendered trailer, and audit attempt ledger were retained exactly.",
            "This probe does not claim that every future provider response will validate or converge.",
        ],
    }
    validate_artifact(value, ROOT)
    args.output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} with {len(audit['attempt_ledger'])} provider attempt(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
