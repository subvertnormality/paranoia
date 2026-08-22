#!/usr/bin/env python3
"""Run the issue-58 exact-plan acceptance through public ``critique_plan``."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from paranoia_local import class_closure as cc, engines
from paranoia_local.handlers import critique_plan


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


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--plan-repo", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_revision = _git(args.repo, "rev-parse", "HEAD")
    source_status_before = _git(args.repo, "status", "--porcelain")
    if source_status_before:
        raise SystemExit("acceptance source worktree must be clean")
    plan_revision = _git(args.plan_repo, "rev-parse", "HEAD")
    plan_path = args.plan_repo / PLAN_REPO_PATH
    plan_bytes = plan_path.read_bytes()
    if hashlib.sha256(plan_bytes).hexdigest() != PLAN_SHA256:
        raise SystemExit("the supplied plan is not the issue-58 historical input")
    version = subprocess.run(
        [str(args.codex), "--version"], check=True, capture_output=True, text=True,
    ).stdout.strip()

    if args.log_dir.exists() and any(args.log_dir.iterdir()):
        raise SystemExit("acceptance log directory must start empty")
    if args.state_root.exists() and any(args.state_root.iterdir()):
        raise SystemExit("acceptance state root must start empty")
    args.log_dir.mkdir(parents=True, exist_ok=True)
    args.state_root.mkdir(parents=True, exist_ok=True)
    effective_state_root = args.state_root.resolve()
    os.environ[cc.STATE_ROOT_ENV] = str(effective_state_root)
    if cc.default_state_root().resolve() != effective_state_root:
        raise SystemExit("public handler did not resolve the requested state root")
    engine = engines.CodexEngine()
    engine.binary = str(args.codex.resolve())
    discovery_argv = engine.for_role(engines.ROLE_DISCOVERY).build_argv(
        args.plan_repo, "gpt-5.6-sol", "high", True,
    )
    if Path(discovery_argv[0]).resolve() != args.codex.resolve():
        raise SystemExit("claim discovery did not resolve the requested executable")
    invocation = {
        "source_revision_before": source_revision,
        "source_status_before": source_status_before,
        "plan_revision": plan_revision,
        "plan_path": PLAN_REPO_PATH,
        "plan_sha256": PLAN_SHA256,
        "plan_bytes": len(plan_bytes),
        "plan_lines": len(plan_bytes.decode("utf-8", "surrogateescape").splitlines()),
        "execution_route": "external-cli",
        "executable": str(args.codex),
        "effective_executable": discovery_argv[0],
        "effective_state_root": str(effective_state_root),
        "cli_version_output": version,
        "model": "gpt-5.6-sol",
        "effort": "high",
        "web_search": True,
        "claim_verification": True,
        "class_closure": True,
        "lineage": LINEAGE_ID,
        "round": 1,
        "stakes": STAKES,
        "started_at": _utc_now(),
    }
    started = time.monotonic()
    result = critique_plan(
        {
            "repo_path": str(args.plan_repo),
            "plan_path": str(plan_path),
            "lineage": LINEAGE_ID,
            "round": 1,
            "stakes": STAKES,
            "claim_verification": True,
            "class_closure": True,
            "model": "gpt-5.6-sol",
            "effort": "high",
            "web_search": True,
        },
        engine=engine,
        log_dir=args.log_dir,
        on_progress=lambda message: print(message, flush=True),
    )
    invocation.update(
        finished_at=_utc_now(),
        elapsed_ms=int((time.monotonic() - started) * 1000),
        result_text=result,
        source_revision_after=_git(args.repo, "rev-parse", "HEAD"),
        source_status_after=_git(args.repo, "status", "--porcelain"),
    )
    if invocation["source_revision_after"] != source_revision or invocation["source_status_after"]:
        raise SystemExit("acceptance source changed during the public handler run")
    audits = sorted(args.log_dir.glob("*critique_plan*.json"))
    lineage_path = args.state_root / "lineages" / f"{LINEAGE_ID}.json"
    if len(audits) != 1 or not lineage_path.is_file():
        raise SystemExit("public handler did not produce one audit and one durable lineage")
    invocation["audit_path"] = str(audits[0])
    invocation["lineage_path"] = str(lineage_path)
    args.output.write_text(
        json.dumps(invocation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(result)


if __name__ == "__main__":
    main()
