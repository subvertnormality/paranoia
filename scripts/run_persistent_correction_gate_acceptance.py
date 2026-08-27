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
ARTIFACT_PATH = "docs/persistent_correction_gate_acceptance_2026-08-23.json"
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


def _successful_trailer(before: dict, after: dict, settlement: dict, audit: dict) -> str:
    lineage = cc._from_json(LINEAGE, deepcopy(after))
    prior_ids = {row["class_id"] for row in before["classes"]}
    minted = [row.class_id for row in lineage.classes.values() if row.class_id not in prior_ids]
    minted_by_record = rc.minted_record_ids(settlement["class_records"], minted)
    status = rc.register_status(settlement["class_records"], minted_by_record, phase="correction")
    return "\n".join((
        cc.render_trailer(
            lineage, register_status=status, minted=minted, include_verdict=False,
        ),
        rc.trailer(
            lineage.review_state,
            class_first_rounds={row.class_id:row.first_round for row in lineage.blocking()},
            session_ref=audit.get("session_ref"),
            correction_gates=audit["correction_gates"],
        ),
        rc.attempt_trailer(audit["attempt_ledger"]),
    ))


def _replay_terminal_lineage(before: dict, audit: dict) -> tuple[dict, str]:
    """Recompute terminal gate diagnostics and the complete unchanged substantive state."""
    message = audit.get("raw_excerpt")
    if (
        not isinstance(message, str)
        or _sha(message) != audit.get("raw_sha256")
        or audit.get("returncode") != 2 or audit.get("error") is not True
    ):
        raise ValueError("terminal audit does not retain its exact local failure message")
    attempts = audit.get("attempt_ledger")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("terminal gate outcome lacks attempts")
    terminal = attempts[-1]
    if not (
        terminal.get("role") == "correction-validation-retry"
        and terminal.get("outcome") == "validation-invalid"
        and "correction limit reached" in message
    ):
        raise ValueError("terminal attempt is not the bounded gate rejection")
    expected = deepcopy(before)
    state = expected["review_state"]
    for key in ("census_cache", "validation_debt", "staged_failure", "format_debt"):
        state.pop(key, None)
    failure = {"role":"correction-validation-retry", "kind":"validation", "message":message}
    rejected = audit.get("rejected_payloads")
    if rejected:
        failure["rejected_payloads"] = deepcopy(rejected)
    state["staged_failure"] = failure
    session = rc.validated_session_ref(terminal.get("session_ref"))
    if session is not None:
        state["correction_control"]["classes"][CLASS_ID]["last_session_ref"] = session
    lineage = cc._from_json(LINEAGE, deepcopy(expected))
    status = f"staged rejected (validation): {rc.trailer_diagnostic(message)}"
    trailer = "\n".join((
        cc.render_trailer(lineage, register_status=status, include_verdict=False),
        rc.trailer(
            state,
            class_first_rounds={row.class_id:row.first_round for row in lineage.blocking()},
            session_ref=session, round_label=7,
            correction_gates=audit["correction_gates"],
        ),
        rc.attempt_trailer(attempts),
    ))
    return expected, trailer


def _public_result(*, audit: dict, settlement: dict | None, after: dict, trailer: str) -> str:
    if settlement is not None:
        text = rc.render_review(settlement, after["review_state"])
        review = engines.Review(
            text=text, session_ref=audit.get("session_ref"), raw="",
            returncode=0, error=False,
        )
    else:
        message = audit["raw_excerpt"]
        text = rc.render_error_review(
            f"[paranoia-local error] staged review rejected (validation): {message}"
        )
        review = engines.Review(
            text=text, session_ref=None, raw=message, returncode=2, error=True,
        )
    engine = type("RecordedCodex", (), {"name":"codex"})()
    return f"{handlers._footer(review, engine)}\n\n{trailer}"


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


def _provider_failure_route(root: Path) -> dict:
    """Exercise a provider failure through public critique_branch and a real process."""
    runtime = Path(tempfile.mkdtemp(prefix="paranoia-provider-failure-"))
    state_root = runtime / "state"
    log_root = runtime / "logs"
    fake = runtime / "codex"
    fake.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--version\" ]; then echo 'codex-cli 0.144.6'; exit 0; fi\n"
        "cat >/dev/null\n"
        "printf '%s\\n' '{\"type\":\"thread.started\",\"thread_id\":\"capacity-fixture\"}'\n"
        "printf '%s\\n' '{\"type\":\"turn.failed\",\"error\":{\"message\":\"Selected model is at capacity\"}}'\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    previous = os.environ.get(cc.STATE_ROOT_ENV)
    os.environ[cc.STATE_ROOT_ENV] = str(state_root)
    engine = engines.CodexEngine()
    engine.binary = str(fake)
    try:
        result = handlers.critique_branch({
            "repo_path":str(root), "base_ref":"main", "head_ref":"HEAD",
            "lineage":"staged-provider-failure-acceptance", "round":1,
            "class_closure":True, "converge":True, "stakes":STAKES,
            "model":"gpt-5.6-sol", "effort":"high", "web_search":False,
        }, engine=engine, log_dir=log_root)
    finally:
        if previous is None:
            os.environ.pop(cc.STATE_ROOT_ENV, None)
        else:
            os.environ[cc.STATE_ROOT_ENV] = previous
    audits = list(log_root.glob("*.json"))
    if len(audits) != 1:
        raise RuntimeError(f"expected one provider-failure audit, got {len(audits)}")
    audit = _state(audits[0])
    lineage = cc.load_lineage(
        state_root, "staged-provider-failure-acceptance",
        stamp="provider-failure-reload", mode=cc.BRANCH_MODE,
    )
    return {
        "result_text":result, "result_sha256":_sha(result),
        "rendered_trailer":audit.get("rendered_trailer"), "audit":audit,
        "durable_lineage":cc._to_json(lineage),
        "attempt_ledger":audit.get("attempt_ledger"),
    }


def validate_artifact(
    artifact: dict, root: Path = ROOT, *, require_committed: bool = True,
) -> None:
    """Shared fail-closed builder/replay validator for the retained acceptance."""
    if require_committed:
        try:
            committed = json.loads(_git_bytes("show", f"HEAD:{ARTIFACT_PATH}"))
        except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            raise ValueError("retained acceptance lacks a valid committed envelope") from exc
        if committed != artifact:
            raise ValueError("retained acceptance differs from its committed Git envelope")
    expected_keys = {
        "acceptance_kind", "version", "date", "source_revision", "source_sha256",
        "provider", "fixture", "before_lineage", "after_lineage", "audit",
        "attempt_ledger", "provider_call_count", "elapsed_seconds", "result_text",
        "result_sha256", "rendered_trailer", "correction_gates",
        "durable_reload_lineage",
        "outcome", "public_preflight_matrix", "public_provider_failure_route",
    }
    if set(artifact) != expected_keys:
        raise ValueError("acceptance fields are not closed and exact")
    if artifact["acceptance_kind"] != "persistent-correction-gate-public-plan-handler":
        raise ValueError("wrong acceptance kind")
    surfaces = {
        "docs/how-it-works.md": (
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
        "src/paranoia_local/server.py", "docs/how-it-works.md", "AGENTS.md",
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
    if not isinstance(attempts, list) or len(attempts) != 1:
        raise ValueError("closure-sweep acceptance requires exactly one provider attempt")
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
    terminal_attempt = attempts[-1]
    if artifact["outcome"] != "closed-with-sibling-debt":
        raise ValueError("acceptance did not retain the required sibling-debt outcome")
    if (
        terminal_attempt.get("role") != "correction"
        or terminal_attempt.get("outcome") != "completed"
        or rc.validated_session_ref(terminal_attempt.get("session_ref")) is None
        or audit.get("session_ref") != terminal_attempt.get("session_ref")
        or audit.get("returncode") != 0 or audit.get("error") is not False
    ):
        raise ValueError("successful public session is not bound to one correction attempt")
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
    sibling_classes = [
        row for row in after["classes"]
        if row["class_id"] != CLASS_ID and row.get("first_round") == 7
        and row.get("status") in rc.UNPROVEN_STATUSES
        and row.get("severity") in rc.BLOCKING
    ]
    sibling_debt = [
        row for row in after["review_state"].get("debt", [])
        if row.get("status") == "open" and row.get("severity") in rc.BLOCKING
        and row.get("finding_id") != "G1"
        and any(
            sibling["class_id"] in row.get("class_ids", [])
            for sibling in sibling_classes
        )
    ]
    if not (
        disposed and sibling_classes and sibling_debt
        and after["review_state"].get("phase") == "correction"
        and settlement is not None
    ):
        raise ValueError("real correction did not durably settle a sibling blocker")
    if disposed:
        if not isinstance(settlement, dict) or settlement.get("role") != "correction":
            raise ValueError("accepted response lacks a materialized correction settlement")
        if not any(
            row.get("class_id") == CLASS_ID and row.get("op") in {"close", "replace"}
            for row in settlement.get("class_records", [])
        ):
            raise ValueError("settlement did not explicitly dispose the gated class")
        debt_update = next(
            (row for row in settlement.get("debt_updates", []) if row.get("id") == "D1"),
            None,
        )
        if not isinstance(debt_update, dict):
            raise ValueError("settlement omitted the gated class's debt outcome")
        if debt_update.get("status") != "closed":
            successor = after_class.get("superseded_by")
            durable_debt = next(
                (
                    row for row in after["review_state"].get("debt", [])
                    if row.get("id") == "D1"
                ),
                None,
            )
            if not (
                after_class["status"] == cc.SUPERSEDED
                and isinstance(successor, str) and successor
                and isinstance(durable_debt, dict)
                and durable_debt.get("status") == "open"
                and durable_debt.get("class_ids") == [successor]
            ):
                raise ValueError(
                    "settlement neither closed the gated debt nor transferred it "
                    "to the recorded replacement"
                )
        if after["review_state"].get("last_round") != 7:
            raise ValueError("successful settlement did not advance the durable label")
        if _replay_successful_lineage(before, settlement, audit) != after:
            raise ValueError("complete post-review lineage differs from canonical replay")
        expected_trailer = _successful_trailer(before, after, settlement, audit)
    expected_result = _public_result(
        audit=audit, settlement=settlement, after=after, trailer=expected_trailer,
    )
    expected_text = (
        rc.render_review(settlement, after["review_state"])
        if settlement is not None else rc.render_error_review(
            "[paranoia-local error] staged review rejected (validation): "
            f"{audit['raw_excerpt']}"
        )
    )
    if (
        trailer != expected_trailer or result != expected_result
        or audit.get("text") != expected_text
        or artifact["result_sha256"] != _sha(expected_result)
    ):
        raise ValueError("public response is not the independently reconstructed result")
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
    failure_route = artifact["public_provider_failure_route"]
    if set(failure_route) != {
        "result_text", "result_sha256", "rendered_trailer", "audit",
        "durable_lineage", "attempt_ledger",
    }:
        raise ValueError("provider-failure route fields are not closed and exact")
    failure_result = failure_route["result_text"]
    failure_trailer = failure_route["rendered_trailer"]
    failure_audit = failure_route["audit"]
    failure_state = failure_route["durable_lineage"]["review_state"]
    failure_attempts = failure_route["attempt_ledger"]
    if (
        not isinstance(failure_result, str)
        or failure_route["result_sha256"] != _sha(failure_result)
        or not isinstance(failure_trailer, str)
        or not failure_result.endswith(failure_trailer)
        or failure_audit.get("tool") != "critique_branch"
        or failure_audit.get("rendered_trailer") != failure_trailer
        or failure_audit.get("error") is not True
        or failure_state.get("staged_failure", {}).get("kind") != "provider"
        or failure_state.get("staged_failure", {}).get("message")
        != "Selected model is at capacity"
        or failure_state.get("validation_debt") is not None
        or not isinstance(failure_attempts, list) or not failure_attempts
        or failure_audit.get("attempt_ledger") != failure_attempts
        or any(
            row.get("engine") != "codex" or row.get("returncode") != 0
            or row.get("outcome") != "failed"
            or row.get("failure_detail_excerpt") != "Selected model is at capacity"
            for row in failure_attempts
        )
        or "staged engine failed (provider): Selected model is at capacity"
        not in failure_result
        or "CLASS-REGISTER: engine failed (provider): Selected model is at capacity"
        not in failure_trailer
        or "STRUCTURAL-FAILURE:" not in failure_trailer
        or "kind=provider" not in failure_trailer
        or "CONVERGENCE: BLOCKED" not in failure_trailer
    ):
        raise ValueError("public provider-failure route is not exact and source-bound")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", default=os.environ.get("PARANOIA_ACCEPTANCE_CODEX", "codex"))
    parser.add_argument(
        "--output",
        default=str(ROOT / ARTIFACT_PATH),
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
    closed_or_replaced = durable.classes[CLASS_ID].status in {cc.CLOSED, cc.SUPERSEDED}
    sibling_classes = [
        row for row in durable.classes.values()
        if row.class_id != CLASS_ID and row.first_round == 7
        and row.status in rc.UNPROVEN_STATUSES and row.severity in rc.BLOCKING
    ]
    sibling_debt = [
        row for row in durable.review_state.get("debt", [])
        if row.get("status") == "open" and row.get("severity") in rc.BLOCKING
        and row.get("finding_id") != "G1"
        and any(item.class_id in row.get("class_ids", []) for item in sibling_classes)
    ]
    if not (
        closed_or_replaced and sibling_classes and sibling_debt
        and durable.review_state.get("phase") == "correction"
        and len(attempts) == 1 and attempts[0].get("outcome") == "completed"
    ):
        raise RuntimeError("real correction did not retain the expected sibling blocker")
    revision = _run("git", "rev-parse", "HEAD")
    source_paths = [
        "src/paranoia_local/handlers.py", "src/paranoia_local/review_census.py",
        "src/paranoia_local/prompts.py", "scripts/run_persistent_correction_gate_acceptance.py",
        "src/paranoia_local/server.py", "docs/how-it-works.md", "AGENTS.md",
        "tests/test_review_census.py", "tests/test_handlers.py",
        "tests/test_plan_class_closure.py", "tests/test_plan_claims.py",
    ]
    artifact = {
        "acceptance_kind":"persistent-correction-gate-public-plan-handler",
        "version":2, "date":"2026-08-24", "source_revision":revision,
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
        "outcome":"closed-with-sibling-debt",
        "public_preflight_matrix":_preflight_matrix(ROOT),
        "public_provider_failure_route":_provider_failure_route(ROOT),
    }
    validate_artifact(artifact, ROOT, require_committed=False)
    Path(args.output).write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} with {len(attempts)} provider call(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
