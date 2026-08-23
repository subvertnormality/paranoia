#!/usr/bin/env python3
"""Exercise the persistent correction gate through public critique_plan."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
import re
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


def _fixture_lineage(structural_snapshot: str) -> cc.Lineage:
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
    return cc.Lineage(
        LINEAGE, rounds=6, classes={CLASS_ID:tracked},
        review_state=state, mode=cc.PLAN_MODE,
    )


def _replay_successful_lineage(before: dict, settlement: dict, audit: dict) -> dict:
    """Recompute the complete accepted plan transition from retained canonical rows."""
    lineage = cc._from_json(LINEAGE, deepcopy(before))
    state = deepcopy(lineage.review_state)
    prior_control = rc.normalize_correction_control(state, lineage.active())
    register = rc.register_from_records(settlement["class_records"], mechanized=False)
    minted = cc.apply_register(lineage, register, round_no=7)
    minted_by_record = rc.minted_record_ids(settlement["class_records"], minted)
    state = rc.settle_state(
        state, settlement, phase="correction",
        snapshot=before["review_state"]["snapshot_digest"], round_no=7,
    )
    replacements = {
        class_id: tracked.superseded_by
        for class_id, tracked in lineage.classes.items()
        if tracked.status == cc.SUPERSEDED and tracked.superseded_by
    }
    for debt in state.get("debt", []):
        debt.setdefault("class_ids", []).extend(
            minted_by_record[index] for index in debt.pop("class_record_indexes", [])
        )
        if debt.get("status") == "open":
            debt["class_ids"] = [
                replacements.get(class_id, class_id)
                for class_id in debt.get("class_ids", [])
            ]
        debt["class_ids"] = list(dict.fromkeys(debt["class_ids"]))
    mapped = {
        class_id for debt in state.get("debt", []) if debt.get("status") == "open"
        for class_id in debt.get("class_ids", [])
    }
    unbound = [row.class_id for row in lineage.blocking() if row.class_id not in mapped]
    blocking_debt = any(
        debt.get("status") == "open" and debt.get("severity") in rc.BLOCKING
        for debt in state.get("debt", [])
    )
    if unbound:
        state["phase"] = "correction" if blocking_debt else "census"
        state["unbound_class_ids"] = unbound
        state.pop("unbound_classes", None)
    elif lineage.blocking():
        state["phase"] = "correction"
    replacement_successors = [
        minted_by_record[index]
        for index, row in enumerate(settlement["class_records"])
        if row.get("op") == "replace"
    ]
    state["correction_control"] = rc.advance_correction_control(
        prior_control, after=lineage, round_no=7, phase="correction",
        session_ref=audit.get("session_ref"),
        replacement_successor_ids=replacement_successors,
    )
    lineage.review_state = state
    lineage.debt = None
    lineage.rounds += 1
    return cc._to_json(lineage)


def _preflight_matrix(root: Path) -> list[dict]:
    """Replay public strict-round refusal for both tracked seams with zero calls."""
    matrix_root = Path(tempfile.mkdtemp(prefix="paranoia-gate-preflight-"))
    previous = os.environ.get(cc.STATE_ROOT_ENV)
    os.environ[cc.STATE_ROOT_ENV] = str(matrix_root)
    forbidden_calls = {
        "snapshot_tree":0, "wrap_commit":0, "build_packet":0, "worktree_at":0,
        "census_cache":0,
    }
    originals = {
        "snapshot_tree":orientation.snapshot_tree,
        "wrap_commit":orientation.wrap_commit,
        "build_packet":orientation.build_packet,
        "worktree_at":handlers.worktree_at,
        "census_cache":handlers._cached_census_manifests,
    }

    def forbid(name: str):
        def blocked(*args, **kwargs):
            forbidden_calls[name] += 1
            raise AssertionError(f"strict-round preflight reached {name}")
        return blocked

    orientation.snapshot_tree = forbid("snapshot_tree")
    orientation.wrap_commit = forbid("wrap_commit")
    orientation.build_packet = forbid("build_packet")
    handlers.worktree_at = forbid("worktree_at")
    handlers._cached_census_manifests = forbid("census_cache")

    class NoCallEngine:
        name = "acceptance-no-call"
        default_model = "unused"

        def __init__(self) -> None:
            self.calls = 0

        def run(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("strict-round preflight admitted a provider call")

        resume = run

    rows: list[dict] = []
    try:
        for mode, caller_round in (
            (mode, caller_round)
            for mode in (cc.PLAN_MODE, cc.BRANCH_MODE)
            for caller_round in (6, 5)
        ):
            lineage_id = f"persistent-gate-{mode}-{caller_round}-strict-preflight"
            state = rc.normalize_state(None, stakes=STAKES, snapshot="preflight")
            state.update(phase="correction", last_round=6, debt=[])
            state["correction_control"] = {"version":1, "classes":{}}
            cc.save_lineage(matrix_root, cc.Lineage(
                lineage_id, rounds=6, mode=mode, review_state=state,
            ))
            path = cc.lineage_dir(matrix_root) / f"{lineage_id}.json"
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            engine = NoCallEngine()
            arguments = {
                "repo_path":str(root), "lineage":lineage_id, "round":caller_round,
                "class_closure":True, "stakes":STAKES,
            }
            if mode == cc.PLAN_MODE:
                arguments.update(plan_text=PLAN, claim_verification=False)
                invoke = handlers.critique_plan
            else:
                arguments.update(base_ref="main", head_ref="HEAD", converge=True)
                invoke = handlers.critique_branch
            row_logs = matrix_root / f"logs-{mode}-{caller_round}"
            result = invoke(arguments, engine=engine, log_dir=row_logs)
            audit_paths = list(row_logs.glob("*.json"))
            if len(audit_paths) != 1:
                raise AssertionError("strict-round preflight did not write one audit")
            audit = json.loads(audit_paths[0].read_text(encoding="utf-8"))
            trailer = audit.get("rendered_trailer")
            if not isinstance(trailer, str) or not result.endswith(trailer):
                raise AssertionError("strict-round audit trailer is not the rendered suffix")
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append({
                "mode":mode, "round":caller_round, "durable_last_round":6,
                "provider_calls":engine.calls,
                "state_sha256_before":before, "state_sha256_after":after,
                "pending_exists":(
                    cc.lineage_dir(matrix_root) / f"{lineage_id}.pending"
                ).exists(),
                "forbidden_work_calls":dict(forbidden_calls),
                "result_sha256":_sha(result), "rendered_trailer":trailer,
                "audit_error":audit.get("error"),
                "attempt_count":len(audit.get("attempt_ledger", [])),
                "correction_gates":audit.get("correction_gates"),
            })
    finally:
        if previous is None:
            os.environ.pop(cc.STATE_ROOT_ENV, None)
        else:
            os.environ[cc.STATE_ROOT_ENV] = previous
        orientation.snapshot_tree = originals["snapshot_tree"]
        orientation.wrap_commit = originals["wrap_commit"]
        orientation.build_packet = originals["build_packet"]
        handlers.worktree_at = originals["worktree_at"]
        handlers._cached_census_manifests = originals["census_cache"]
    return rows


def validate_artifact(artifact: dict, root: Path = ROOT) -> None:
    """Shared fail-closed builder/replay validator for the retained acceptance."""
    expected_keys = {
        "acceptance_kind", "version", "date", "source_revision", "source_sha256",
        "provider", "fixture", "before_lineage", "after_lineage", "audit",
        "attempt_ledger", "provider_call_count", "elapsed_seconds", "result_text",
        "result_sha256", "rendered_trailer", "correction_gates",
        "durable_reload_lineage",
        "outcome", "public_preflight_matrix",
    }
    if set(artifact) != expected_keys:
        raise ValueError("acceptance fields are not closed and exact")
    if artifact["acceptance_kind"] != "persistent-correction-gate-public-plan-handler":
        raise ValueError("wrong acceptance kind")
    surfaces = {
        "README.md": (
            "reset_round", "reopen_count", "last_session_ref", "CORRECTION-GATE",
            "correction_gates", "rendered_trailer", "validation-invalid terminal retry",
        ),
        "AGENTS.md": (
            "reset_round", "reopen_count", "last_session_ref",
            "exact validation-invalid terminal retry",
        ),
        "src/paranoia_local/server.py": (
            "all-or-none", "never closes debt", "Sessionless gate recovery",
            "never falls back to an earlier attempt",
        ),
    }
    for relative, required in surfaces.items():
        text = (root / relative).read_text(encoding="utf-8")
        missing = [token for token in required if token not in text]
        if missing:
            raise ValueError(f"{relative} omits public contract tokens {missing!r}")
    revision = artifact["source_revision"]
    expected_sources = {
        "src/paranoia_local/handlers.py", "src/paranoia_local/review_census.py",
        "src/paranoia_local/prompts.py", "scripts/run_persistent_correction_gate_acceptance.py",
        "src/paranoia_local/server.py", "README.md", "AGENTS.md",
        "tests/test_review_census.py", "tests/test_handlers.py",
        "tests/test_plan_class_closure.py", "tests/test_plan_claims.py",
    }
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("source revision is not a full commit")
    if set(artifact["source_sha256"]) != expected_sources:
        raise ValueError("source inventory is not exact")
    for relative, expected in artifact["source_sha256"].items():
        historical = subprocess.run(
            ["git", "show", f"{revision}:{relative}"], cwd=root, check=True,
            stdout=subprocess.PIPE,
        ).stdout
        if hashlib.sha256(historical).hexdigest() != expected:
            raise ValueError(f"historical source digest mismatch for {relative}")
        if (root / relative).read_bytes() != historical:
            raise ValueError(f"current source differs from acceptance for {relative}")
    provider = artifact["provider"]
    if not (
        set(provider) == {
            "engine", "executable", "cli_version", "model", "effort", "web_search",
        }
        and provider.get("engine") == "codex" and provider.get("executable") == "codex"
        and provider.get("model") == "gpt-5.6-sol"
        and provider.get("effort") == "high" and provider.get("web_search") is False
        and isinstance(provider.get("cli_version"), str)
        and re.fullmatch(
            r"codex-cli \d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?",
            provider["cli_version"],
        )
    ):
        raise ValueError("provider route is not the required real Codex route")
    fixture = artifact["fixture"]
    if set(fixture) != {
        "lineage", "class_id", "round", "plan", "plan_sha256",
        "snapshot_commit", "structural_snapshot",
    }:
        raise ValueError("fixture fields are not exact")
    if (
        fixture["lineage"] != LINEAGE or fixture["class_id"] != CLASS_ID
        or fixture["round"] != 7 or fixture["plan"] != PLAN
        or fixture["plan_sha256"] != _sha(PLAN)
        or fixture["structural_snapshot"]
        != rc.digest(f"{PLAN}\0{fixture['snapshot_commit']}")
    ):
        raise ValueError("fixture binding mismatch")
    snapshot_tree = _run("git", "rev-parse", f"{fixture['snapshot_commit']}^{{tree}}", cwd=root)
    source_tree = _run("git", "rev-parse", f"{revision}^{{tree}}", cwd=root)
    if snapshot_tree != source_tree:
        raise ValueError("reviewed snapshot tree differs from the source revision")
    expected_gate = [{
        "class_id":CLASS_ID, "reason":"persistence", "reopen_count":0, "span":7,
    }]
    audit = artifact["audit"]
    attempts = artifact["attempt_ledger"]
    if not (
        audit.get("tool") == "critique_plan" and audit.get("lineage") == LINEAGE
        and audit.get("round") == 7 and audit.get("claim_verification") is False
        and audit.get("model") == "gpt-5.6-sol"
        and audit.get("plan_digest") == _sha(PLAN)[:16]
    ):
        raise ValueError("public critique_plan audit binding mismatch")
    if artifact["correction_gates"] != expected_gate:
        raise ValueError("correction gate projection mismatch")
    if audit.get("correction_gates") != expected_gate:
        raise ValueError("audit gate projection mismatch")
    if audit.get("attempt_ledger") != attempts:
        raise ValueError("attempt ledger is not exact")
    if not isinstance(attempts, list) or not 1 <= len(attempts) <= 2:
        raise ValueError("provider call topology exceeded its bound")
    if artifact["provider_call_count"] != len(attempts):
        raise ValueError("provider call count mismatch")
    if any(
        row.get("engine") != "codex"
        or row.get("role") not in {"correction", "correction-validation-retry"}
        or type(row.get("returncode")) is not int
        or not row.get("raw_sha256") or not row.get("failure_detail_sha256")
        or not row.get("stderr_sha256")
        for row in attempts
    ):
        raise ValueError("attempt telemetry is incomplete or on the wrong route")
    result = artifact["result_text"]
    trailer = artifact["rendered_trailer"]
    if (
        not isinstance(result, str) or artifact["result_sha256"] != _sha(result)
        or not isinstance(trailer, str) or not result.endswith(trailer)
        or audit.get("rendered_trailer") != trailer
    ):
        raise ValueError("returned/audited trailer binding mismatch")
    before = artifact["before_lineage"]
    after = artifact["after_lineage"]
    if before != cc._to_json(_fixture_lineage(fixture["structural_snapshot"])):
        raise ValueError("recorded prebuilt lineage differs from the complete fixture")
    if artifact["durable_reload_lineage"] != after:
        raise ValueError("durable reload differs from the recorded post-review lineage")
    settlement = audit.get("staged_settlement")
    before_class = next(row for row in before["classes"] if row["class_id"] == CLASS_ID)
    after_class = next(row for row in after["classes"] if row["class_id"] == CLASS_ID)
    before_control = before["review_state"]["correction_control"]["classes"][CLASS_ID]
    if not (
        before["review_state"]["phase"] == "correction"
        and before["review_state"]["last_round"] == 6
        and before_class["status"] == cc.OPEN and before_class["first_round"] == 1
        and before_control == {
            "reset_round":None, "reopen_count":0, "last_session_ref":None,
        }
    ):
        raise ValueError("prebuilt lineage is not the exhausted fixture")
    disposed = after_class["status"] in {cc.CLOSED, cc.SUPERSEDED}
    terminal = (
        after_class["status"] == cc.OPEN
        and "correction limit reached" in json.dumps(after["review_state"])
    )
    expected_outcome = "closed-or-replaced" if disposed else "terminal-gate-rejection"
    if not (disposed or terminal) or artifact["outcome"] != expected_outcome:
        raise ValueError("durable outcome does not satisfy the gate acceptance")
    if disposed:
        if not isinstance(settlement, dict) or settlement.get("role") != "correction":
            raise ValueError("accepted response lacks a materialized correction settlement")
        if not any(
            row.get("class_id") == CLASS_ID and row.get("op") in {"close", "replace"}
            for row in settlement.get("class_records", [])
        ):
            raise ValueError("settlement did not explicitly dispose the gated class")
        if not any(
            row.get("id") == "D1" and row.get("status") == "closed"
            for row in settlement.get("debt_updates", [])
        ):
            raise ValueError("settlement did not close the gated class's debt")
        if after["review_state"].get("last_round") != 7:
            raise ValueError("successful settlement did not advance the durable label")
        if _replay_successful_lineage(before, settlement, audit) != after:
            raise ValueError("complete post-review lineage differs from canonical replay")
    else:
        if settlement is not None:
            raise ValueError("terminal rejection published an unapplied settlement")
        if after["review_state"].get("last_round") != 6:
            raise ValueError("terminal rejection advanced substantive round state")
    if after["review_state"].get("snapshot_digest") != fixture["structural_snapshot"]:
        raise ValueError("durable state is not bound to the reviewed snapshot")
    active_rows = [row for row in after["classes"] if row.get("status") != cc.SUPERSEDED]
    active = [cc.TrackedClass(
        class_id=row["class_id"], invariant=row["invariant"], severity=row["severity"],
        first_round=row["first_round"], status=row["status"],
        pattern=row.get("pattern"), pathspec=row.get("pathspec"),
        procedure=row.get("procedure"), superseded_by=row.get("superseded_by"),
        detail=row.get("detail"), matches=tuple(row.get("matches", ())),
    ) for row in active_rows]
    rc.normalize_correction_control(after["review_state"], active)
    matrix = artifact["public_preflight_matrix"]
    if matrix != _preflight_matrix(root):
        raise ValueError("public plan/branch strict-round preflight replay mismatch")
    if any(
        row["provider_calls"] != 0
        or row["state_sha256_before"] != row["state_sha256_after"]
        or row["pending_exists"] is not False
        or any(row["forbidden_work_calls"].values())
        or row["audit_error"] is not True
        or row["attempt_count"] != 0
        or row["correction_gates"] != []
        or f"greater than durable last_round 6; got {row['round']}" not in row["rendered_trailer"]
        for row in matrix
    ):
        raise ValueError("strict-round preflight did work or mutated durable state")


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
    cc.save_lineage(state_root, _fixture_lineage(structural_snapshot))
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
        "src/paranoia_local/server.py", "README.md", "AGENTS.md",
        "tests/test_review_census.py", "tests/test_handlers.py",
        "tests/test_plan_class_closure.py", "tests/test_plan_claims.py",
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
        "durable_reload_lineage":cc._to_json(durable),
        "outcome":"closed-or-replaced" if closed_or_replaced else "terminal-gate-rejection",
        "public_preflight_matrix":_preflight_matrix(ROOT),
    }
    validate_artifact(artifact, ROOT)
    Path(args.output).write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} with {len(attempts)} provider call(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
