#!/usr/bin/env python3
"""Exercise the persistent correction gate through public critique_plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import class_closure as cc
from paranoia_local import engines, handlers, orientation, review_census as rc

LINEAGE = "persistent-correction-gate-acceptance-20260823"
CLASS_ID = "gate-class"
PLAN = "# Change\n\nImplement the correction gate.\nTests must exercise its public handler."
STAKES = (
    "One trusted operator and OS; repository and plan bytes are untrusted data; no "
    "hostile local race or repository execution; one class and one claim-free plan; "
    "false clearance is high impact and recoverable blocking is acceptable."
)


def _run(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(
        list(args), cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _git_bytes(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, stdout=subprocess.PIPE,
    ).stdout


def _state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", default=os.environ.get("PARANOIA_ACCEPTANCE_CODEX", "codex"))
    parser.add_argument(
        "--output",
        default=str(ROOT / "docs/persistent_correction_gate_acceptance_2026-08-23.json"),
    )
    args = parser.parse_args()
    state_root = Path(tempfile.mkdtemp(prefix="paranoia-gate-state-"))
    log_root = Path(tempfile.mkdtemp(prefix="paranoia-gate-log-"))
    parent = orientation.resolve_head(ROOT)
    snapshot_commit = orientation.wrap_commit(
        ROOT, orientation.snapshot_tree(ROOT, parent), parent,
    )
    structural_snapshot = rc.digest(f"{PLAN}\0{snapshot_commit}")
    state = rc.normalize_state(None, stakes=STAKES, snapshot=structural_snapshot)
    state.update(phase="correction", last_round=6, debt=[{
        "id":"D1", "finding_id":"G1", "status":"open", "severity":"MAJOR",
        "summary":"the correction gate lacked public-handler acceptance",
        "reason":"acceptance was not yet exercised", "remedy":"exercise the handler",
        "evidence":["plan:4"], "source_ids":[], "class_ids":[CLASS_ID],
        "first_round":1, "last_round":6,
    }])
    state["correction_control"] = {"version":1, "classes":{CLASS_ID:{
        "reset_round":None, "reopen_count":0, "last_session_ref":None,
    }}}
    tracked = cc.TrackedClass(
        CLASS_ID, "The plan requires public-handler acceptance for the correction gate.",
        cc.MAJOR, 1, cc.OPEN, procedure="Inspect the plan acceptance obligation.",
    )
    cc.save_lineage(state_root, cc.Lineage(
        LINEAGE, rounds=6, classes={CLASS_ID:tracked},
        review_state=state, mode=cc.PLAN_MODE,
    ))
    state_path = cc.lineage_dir(state_root) / f"{LINEAGE}.json"
    before = _state(state_path)
    os.environ[cc.STATE_ROOT_ENV] = str(state_root)
    engine = engines.CodexEngine()
    engine.binary = args.codex
    started = time.monotonic()
    result = handlers.critique_plan({
        "repo_path":str(ROOT), "plan_text":PLAN, "lineage":LINEAGE,
        "round":7, "class_closure":True, "claim_verification":False,
        "model":"gpt-5.6-sol", "effort":"high", "web_search":False,
        "stakes":STAKES,
    }, engine=engine, log_dir=log_root)
    elapsed = time.monotonic() - started
    after = _state(state_path)
    audits = list(log_root.glob("*.json"))
    if len(audits) != 1:
        raise RuntimeError(f"expected one audit, got {len(audits)}")
    audit = _state(audits[0])
    gates = audit.get("correction_gates")
    expected_gate = [{
        "class_id":CLASS_ID, "reason":"persistence", "span":7,
        "reopen_count":0,
    }]
    if gates != expected_gate:
        raise RuntimeError(f"unexpected correction gates: {gates!r}")
    trailer = audit.get("rendered_trailer")
    if not isinstance(trailer, str) or not result.endswith(trailer):
        raise RuntimeError("audit trailer is not the exact returned trailer")
    attempts = audit.get("attempt_ledger")
    if not isinstance(attempts, list) or not 1 <= len(attempts) <= 2:
        raise RuntimeError("acceptance exceeded the correction plus one retry topology")
    durable = cc.load_lineage(state_root, LINEAGE, stamp="reload", mode=cc.PLAN_MODE)
    closed_or_replaced = (
        durable.classes[CLASS_ID].status in {cc.CLOSED, cc.SUPERSEDED}
    )
    terminal_gate_rejection = (
        durable.classes[CLASS_ID].status == cc.OPEN
        and "correction limit reached" in json.dumps(durable.review_state)
    )
    if not (closed_or_replaced or terminal_gate_rejection):
        raise RuntimeError("provider result was neither a disposition nor terminal gate rejection")
    revision = _run("git", "rev-parse", "HEAD")
    source_paths = [
        "src/paranoia_local/handlers.py", "src/paranoia_local/review_census.py",
        "src/paranoia_local/prompts.py", "scripts/run_persistent_correction_gate_acceptance.py",
    ]
    artifact = {
        "acceptance_kind":"persistent-correction-gate-public-plan-handler",
        "version":1, "date":"2026-08-23", "source_revision":revision,
        "source_sha256":{
            path:hashlib.sha256(_git_bytes("show", f"{revision}:{path}")).hexdigest()
            for path in source_paths
        },
        "provider":{
            "engine":"codex", "executable":args.codex,
            "cli_version":_run(args.codex, "--version"),
            "model":"gpt-5.6-sol", "effort":"high", "web_search":False,
        },
        "fixture":{
            "lineage":LINEAGE, "class_id":CLASS_ID, "round":7,
            "plan":PLAN, "plan_sha256":_sha(PLAN),
            "snapshot_commit":snapshot_commit,
            "structural_snapshot":structural_snapshot,
        },
        "before_lineage":before, "after_lineage":after,
        "audit":audit, "attempt_ledger":attempts,
        "provider_call_count":len(attempts), "elapsed_seconds":round(elapsed, 3),
        "result_text":result, "result_sha256":_sha(result),
        "rendered_trailer":trailer, "correction_gates":gates,
        "durable_reload":True,
        "outcome":"closed-or-replaced" if closed_or_replaced else "terminal-gate-rejection",
    }
    Path(args.output).write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} with {len(attempts)} provider call(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
