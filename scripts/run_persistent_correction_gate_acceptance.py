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
from paranoia_local import (
    engines, handlers, orientation, prompts, review_census as rc,
    staged_protocol as sp,
)

LINEAGE = "persistent-correction-gate-acceptance-20260823"
CLASS_ID = "gate-class"
SIBLING_CLASS_ID = "source-binding-class"
ARTIFACT_PATH = "docs/persistent_correction_gate_acceptance_2026-08-23.json"
LEGACY_SOURCE_REVISION = "bb068a1c359765f12b9c2295a88f039424c7d4f9"
LEGACY_REPAIR_PLAN_SHA256 = "7060753ab927b4a4276a00693f6ff498d2315f9be77f131aa425f30fbfd8e2c5"
ACCEPTANCE_SOURCES = tuple(sorted(
    str(path.relative_to(ROOT))
    for path in (ROOT / "src" / "paranoia_local").glob("*.py")
)) + (
    "scripts/run_persistent_correction_gate_acceptance.py",
    "README.md", "docs/how-it-works.md", "docs/tool-reference.md",
    "docs/llm-reference.md", "AGENTS.md", "CLAUDE.md",
    "docs/staged_review_protocol_v2_acceptance.md",
    "tests/test_review_census.py", "tests/test_handlers.py",
    "tests/test_plan_class_closure.py", "tests/test_plan_claims.py",
)
PLAN = (
    "# Change\n\n"
    "Update only scripts/run_persistent_correction_gate_acceptance.py, "
    "tests/test_review_census.py, and its retained artifact.\n"
    "Invoke critique_plan through the public handler with an exact CodexEngine.\n"
    "Seed the declared active classes and durable correction debt before provider spend.\n"
    "Record the completed attempt, settlement, prompt digest, and durable reload.\n"
    "The retained artifact does not bind a newly discovered blocker to its exact plan source line.\n"
    "Fail generation on provider, validation, persistence, source-binding, or phase mismatch.\n"
    "Replay the fixed plan through a later correction and require its debt to close.\n"
    "Then invoke a separate cold final and require that final alone to reach clear.\n"
    "Tests verify source hashes, prompt roles, class/debt identity, phase order, and tamper rejection."
)
FIXED_PLAN = PLAN.replace(
    "The retained artifact does not bind a newly discovered blocker to its exact plan source line.",
    "The retained artifact binds the seeded source-binding blocker to its exact plan source line.",
) + (
    "\nThe validator requires the new debt to name source-binding-class exactly and its "
    "governing finding evidence to contain a plan anchor whose closed range covers line 7."
    "\nThe source-bound test mutates that class identity and evidence anchor and requires "
    "validation to reject both changes."
    "\nRun every identity, evidence, phase, durable-reload, and source-hash validation before "
    "the single artifact publication write; failure of any named validation exits nonzero "
    "before publication. This fixture makes no claim about filesystem write-failure atomicity."
    "\nFor the separate final, retain its exact prompt and require the complete fixed plan, all "
    "nine checklist items, the exact gate-class and source-binding-class roster, and no open debt."
    "\nRequire correction, repair, and final to use three distinct provider sessions, and reject "
    "a coordinated mutation of any final prompt binding before Path.write_text."
    "\nRetain one closed server-owned sibling binding with class ID source-binding-class, the "
    "authoritative coordinate defined by the validator requirement above, its debt and finding "
    "IDs, and the provider evidence unchanged."
    "\nValidate that authoritative coordinate independently from provider-range containment, and reject "
    "a mutation of either channel before Path.write_text."
    "\nThe retained artifact source inventory is the deterministic complete set of every "
    "Python module under src/paranoia_local, plus this generator, README.md, how-it-works.md, "
    "tool-reference.md, llm-reference.md, AGENTS.md, CLAUDE.md, "
    "staged_review_protocol_v2_acceptance.md, and the four named test modules "
    "enforced by the shared ACCEPTANCE_SOURCES constant. Commit every bound source before generation "
    "so source_revision and current bytes agree, validate the completed artifact, then publish "
    "it in a separate commit. Before publication, require removed, added, or replaced inventory "
    "members, changed source digests, and dirty bound-source bytes all to reject."
)
SIBLING_LINE = 7
STAKES = (
    "One trusted operator and OS; repository and plan bytes are untrusted data; no "
    "hostile local race or repository execution; two classes and one claim-free plan; "
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


def _anchor_covers_plan_line(anchor: object, line: int) -> bool:
    if not isinstance(anchor, str) or not anchor.startswith("plan:"):
        return False
    raw = anchor.removeprefix("plan:")
    start, dash, end = raw.partition("-")
    if not start.isdigit() or (dash and not end.isdigit()):
        return False
    lower = int(start)
    upper = int(end) if dash else lower
    return lower <= line <= upper


def _critique_plan_with_prompt_capture(
    engine: engines.CodexEngine, arguments: dict, log_dir: Path,
) -> tuple[str, list[str]]:
    """Invoke the exact built-in route while observing prompts sent by role clones."""
    captured: list[str] = []
    original_run = engines.CodexEngine.run
    original_resume = engines.CodexEngine.resume

    def capture_run(self, prompt, *call_args, **call_kwargs):
        captured.append(prompt)
        return original_run(self, prompt, *call_args, **call_kwargs)

    def capture_resume(self, session_ref, prompt, *call_args, **call_kwargs):
        captured.append(prompt)
        return original_resume(
            self, session_ref, prompt, *call_args, **call_kwargs,
        )

    engines.CodexEngine.run = capture_run
    engines.CodexEngine.resume = capture_resume
    try:
        result = handlers.critique_plan(arguments, engine=engine, log_dir=log_dir)
    finally:
        engines.CodexEngine.run = original_run
        engines.CodexEngine.resume = original_resume
    return result, captured


def _fixture_lineage(structural_snapshot: str) -> cc.Lineage:
    state = rc.normalize_state(None, stakes=STAKES, snapshot=structural_snapshot)
    state.update(phase="correction", last_round=6, debt=[{
        "id":"D1", "finding_id":"G1", "status":"open", "severity":"MAJOR",
        "summary":"the correction gate lacked public-handler acceptance",
        "reason":"acceptance was not yet exercised", "remedy":"exercise the handler",
        "evidence":["plan:4"], "source_ids":[], "class_ids":[CLASS_ID],
        "first_round":1, "last_round":6,
    }])
    state["correction_control"] = {"version":1, "classes":{
        CLASS_ID:{
            "reset_round":None, "reopen_count":0, "last_session_ref":None,
        },
        SIBLING_CLASS_ID:{
            "reset_round":None, "reopen_count":0, "last_session_ref":None,
        },
    }}
    tracked = cc.TrackedClass(
        CLASS_ID, "The plan requires public-handler acceptance for the correction gate.",
        cc.MAJOR, 1, cc.OPEN, procedure="Inspect the plan acceptance obligation.",
    )
    sibling = cc.TrackedClass(
        SIBLING_CLASS_ID,
        "The retained acceptance binds the seeded source-binding blocker to its exact plan source line.",
        cc.MAJOR, 6, cc.OPEN,
        procedure="Inspect the retained finding and debt evidence against the plan source line.",
    )
    return cc.Lineage(
        LINEAGE, rounds=6, classes={CLASS_ID:tracked, SIBLING_CLASS_ID:sibling},
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
        engine_name=audit["engine"],
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
        rc.set_phase(state, "correction" if blocking_debt else "census")
        state["unbound_class_ids"] = unbound
        state.pop("unbound_classes", None)
    elif lineage.blocking():
        rc.set_phase(state, "correction")
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
        "allowed_later_source_diffs",
        "provider", "fixture", "before_lineage", "after_lineage", "audit",
        "attempt_ledger", "provider_call_count", "elapsed_seconds", "result_text",
        "result_sha256", "rendered_trailer", "correction_gates",
        "durable_reload_lineage",
        "correction_prompt", "correction_prompt_sha256",
        "sibling_binding",
        "repair_plan", "repair_plan_sha256", "repair_result_text",
        "repair_result_sha256", "repair_prompts", "repair_prompt_sha256",
        "repair_audit", "repair_attempt_ledger", "after_repair_lineage",
        "repair_durable_reload_lineage", "final_result_text",
        "final_result_sha256", "final_prompts", "final_prompt_sha256",
        "final_audit", "final_attempt_ledger", "final_lineage",
        "final_durable_reload_lineage", "total_provider_call_count",
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
        "README.md": (
            "lineage", "class_id", "debt_id", "lineage_mode",
            "HOLD", "CONCEDE", "never grants clearance",
        ),
        "docs/tool-reference.md": (
            "lineage", "class_id", "debt_id", "lineage_mode",
            "HOLD", "CONCEDE", "never grants convergence",
        ),
        "docs/llm-reference.md": (
            "lineage", "class_id", "debt_id", "lineage_mode",
            "HOLD", "CONCEDE", "non-mutating",
        ),
        "src/paranoia_local/server.py": (
            "all-or-none", "debt_id", "HOLD", "CONCEDE",
            "never grants clearance",
        ),
    }
    for relative, required in surfaces.items():
        text = (root / relative).read_text(encoding="utf-8")
        missing = [token for token in required if token not in text]
        if missing:
            raise ValueError(f"{relative} omits public contract tokens {missing!r}")
    revision = artifact["source_revision"]
    expected_sources = set(ACCEPTANCE_SOURCES)
    if revision == LEGACY_SOURCE_REVISION:
        expected_sources -= {"README.md", "docs/tool-reference.md", "docs/llm-reference.md"}
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("source revision is not a full commit")
    if set(artifact["source_sha256"]) != expected_sources:
        raise ValueError("source inventory is not exact")
    allowed_later = artifact["allowed_later_source_diffs"]
    if not isinstance(allowed_later, dict):
        raise ValueError("later-source allowance inventory is absent")
    changed: set[str] = set()
    for relative, expected in artifact["source_sha256"].items():
        historical = subprocess.run(
            ["git", "show", f"{revision}:{relative}"], cwd=root, check=True,
            stdout=subprocess.PIPE,
        ).stdout
        if hashlib.sha256(historical).hexdigest() != expected:
            raise ValueError(f"historical source digest mismatch for {relative}")
        if (root / relative).read_bytes() != historical:
            changed.add(relative)
            allowance = allowed_later.get(relative)
            if not isinstance(allowance, dict) or set(allowance) != {"sha256", "scope"}:
                raise ValueError(f"later-source allowance is absent for {relative}")
            diff = subprocess.run(
                ["git", "diff", "--no-ext-diff", revision, "--", relative],
                cwd=root, check=True, stdout=subprocess.PIPE,
            ).stdout
            if hashlib.sha256(diff).hexdigest() != allowance["sha256"]:
                raise ValueError(f"later-source allowance mismatch for {relative}")
            if not isinstance(allowance["scope"], str) or not allowance["scope"].strip():
                raise ValueError(f"later-source allowance scope is empty for {relative}")
    if set(allowed_later) != changed:
        raise ValueError("later-source allowance inventory is not exact")
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
    prompt = artifact["correction_prompt"]
    if (
        not isinstance(prompt, str)
        or artifact["correction_prompt_sha256"] != _sha(prompt)
        or prompt.count(handlers.PLAN_CLOSURE_CANDIDATE_INSTRUCTIONS) != 1
        or "===== TASK INPUT =====\n\n" not in prompt
    ):
        raise ValueError("captured correction prompt is not exact")
    task = json.loads(prompt.split("===== TASK INPUT =====\n\n", 1)[1])
    if not (
        task.get("role") == "correction"
        and task.get("stakes") == STAKES
        and task.get("review_scope") == "closure_candidate"
        and task.get("checklist") == list(sp.CHECKLIST)
        and len(task.get("existing_debt", [])) == 1
        and task["existing_debt"][0].get("id") == "D1"
        and [row.get("class_id") for row in task.get("active_classes", [])]
        == [CLASS_ID, SIBLING_CLASS_ID]
        and PLAN.splitlines()[SIBLING_LINE - 1] in task.get("artifact", "")
    ):
        raise ValueError("captured correction task is not the closure-candidate fixture")
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
    if (
        not isinstance(attempts, list) or not 1 <= len(attempts) <= 2
        or attempts[-1].get("outcome") != "completed"
        or any(row.get("outcome") != "validation-invalid" for row in attempts[:-1])
    ):
        raise ValueError("closure-sweep acceptance exceeded its bounded retry topology")
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
        raise ValueError(
            "successful public session is not bound to its terminal attempt "
            "or did not use exactly one correction"
        )
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
        if row["class_id"] == SIBLING_CLASS_ID
        and row.get("status") in cc.UNPROVEN_STATUSES
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
    sibling_finding_ids = {row["finding_id"] for row in sibling_debt}
    sibling_findings = [
        row for row in settlement.get("findings", [])
        if row.get("id") in sibling_finding_ids
        and any(
            _anchor_covers_plan_line(anchor, SIBLING_LINE)
            for anchor in row.get("evidence", [])
        )
    ]
    if not (
        disposed and sibling_classes and sibling_debt and sibling_findings
        and after["review_state"].get("phase") == "correction"
        and settlement is not None
    ):
        raise ValueError("real correction did not durably settle a sibling blocker")
    sibling_binding = artifact["sibling_binding"]
    if not (
        set(sibling_binding) == {
            "class_id", "debt_id", "finding_id", "anchor", "provider_evidence",
        }
        and sibling_binding["class_id"] == SIBLING_CLASS_ID
        and sibling_binding["anchor"] == f"plan:{SIBLING_LINE}"
        and sibling_binding["debt_id"] in {row["id"] for row in sibling_debt}
        and sibling_binding["finding_id"] in sibling_finding_ids
        and sibling_binding["provider_evidence"] == sibling_findings[0]["evidence"]
        and any(
            _anchor_covers_plan_line(anchor, SIBLING_LINE)
            for anchor in sibling_binding["provider_evidence"]
        )
    ):
        raise ValueError("exact server-owned sibling binding is not source-faithful")
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

    repair_plan = artifact["repair_plan"]
    repair_result = artifact["repair_result_text"]
    repair_prompts = artifact["repair_prompts"]
    repair_audit = artifact["repair_audit"]
    repair_attempts = artifact["repair_attempt_ledger"]
    after_repair = artifact["after_repair_lineage"]
    repair_plan_is_bound = (
        repair_plan == FIXED_PLAN
        or (
            artifact["source_revision"] == LEGACY_SOURCE_REVISION
            and artifact["repair_plan_sha256"] == LEGACY_REPAIR_PLAN_SHA256
        )
    )
    if not (
        repair_plan_is_bound
        and artifact["repair_plan_sha256"] == _sha(repair_plan)
        and isinstance(repair_result, str)
        and artifact["repair_result_sha256"] == _sha(repair_result)
        and isinstance(repair_prompts, list) and repair_prompts
        and artifact["repair_prompt_sha256"] == [_sha(row) for row in repair_prompts]
        and repair_audit.get("round") == 8
        and repair_audit.get("plan_digest") == _sha(repair_plan)[:16]
        and repair_audit.get("attempt_ledger") == repair_attempts
        and isinstance(repair_attempts, list) and 1 <= len(repair_attempts) <= 2
        and repair_attempts[-1].get("role") in {
            "correction", "correction-validation-retry",
        }
        and repair_attempts[-1].get("outcome") == "completed"
        and repair_result.endswith(repair_audit.get("rendered_trailer", ""))
        and artifact["repair_durable_reload_lineage"] == after_repair
        and after_repair["review_state"].get("phase") == "final"
        and not any(
            row.get("status") == "open" and row.get("severity") in rc.BLOCKING
            for row in after_repair["review_state"].get("debt", [])
        )
        and next(
            row for row in after_repair["classes"]
            if row["class_id"] == SIBLING_CLASS_ID
        )["status"] == cc.CLOSED
        and "STRUCTURAL-PHASE: final" in repair_result
        and "CONVERGENCE: NOT-BLOCKED" not in repair_result
    ):
        raise ValueError("later correction does not stop at the final boundary")
    repair_task = json.loads(
        repair_prompts[0].split("===== TASK INPUT =====\n\n", 1)[1]
    )
    if not (
        repair_task.get("role") == "correction"
        and repair_task.get("stakes") == STAKES
        and repair_task.get("review_scope") == "closure_candidate"
        and repair_task.get("checklist") == list(sp.CHECKLIST)
        and repair_plan.splitlines()[SIBLING_LINE - 1]
        in repair_task.get("artifact", "")
        and repair_prompts[0].count(
            handlers.PLAN_CLOSURE_CANDIDATE_INSTRUCTIONS
        ) == 1
    ):
        raise ValueError("repair prompt is not the expected closure-candidate correction")

    final_result = artifact["final_result_text"]
    final_prompts = artifact["final_prompts"]
    final_audit = artifact["final_audit"]
    final_attempts = artifact["final_attempt_ledger"]
    final_lineage = artifact["final_lineage"]
    if not (
        isinstance(final_result, str)
        and artifact["final_result_sha256"] == _sha(final_result)
        and isinstance(final_prompts, list) and final_prompts
        and artifact["final_prompt_sha256"] == [_sha(row) for row in final_prompts]
        and final_audit.get("round") == 9
        and final_audit.get("plan_digest") == _sha(repair_plan)[:16]
        and final_audit.get("attempt_ledger") == final_attempts
        and isinstance(final_attempts, list) and 1 <= len(final_attempts) <= 2
        and final_attempts[-1].get("role") in {"final", "final-validation-retry"}
        and final_attempts[-1].get("outcome") == "completed"
        and final_result.endswith(final_audit.get("rendered_trailer", ""))
        and artifact["final_durable_reload_lineage"] == final_lineage
        and final_lineage["review_state"].get("phase") == "clear"
        and "STRUCTURAL-PHASE: clear" in final_result
        and "CONVERGENCE: NOT-BLOCKED" in final_result
        and artifact["total_provider_call_count"] == (
            len(attempts) + len(repair_attempts) + len(final_attempts)
        )
    ):
        raise ValueError("separate cold final does not exclusively reach clear")
    final_task = json.loads(
        final_prompts[0].split("===== TASK INPUT =====\n\n", 1)[1]
    )
    if not (
        final_task.get("role") == "final"
        and final_task.get("stakes") == STAKES
        and final_task.get("checklist") == list(sp.CHECKLIST)
        and final_task.get("existing_debt") == []
        and [row.get("class_id") for row in final_task.get("active_classes", [])]
        == [CLASS_ID, SIBLING_CLASS_ID]
        and all(
            line in final_task.get("artifact", "")
            for line in repair_plan.splitlines() if line
        )
        and handlers.PLAN_CLOSURE_CANDIDATE_INSTRUCTIONS not in final_prompts[0]
        and len({
            audit.get("session_ref"), repair_audit.get("session_ref"),
            final_audit.get("session_ref"),
        }) == 3
        and all(
            rc.validated_session_ref(session) is not None
            for session in (
                audit.get("session_ref"), repair_audit.get("session_ref"),
                final_audit.get("session_ref"),
            )
        )
    ):
        raise ValueError("final prompt/session is not a fresh complete regression")
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
    common = {
        "repo_path":str(ROOT), "lineage":LINEAGE, "class_closure":True,
        "claim_verification":False, "model":"gpt-5.6-sol", "effort":"high",
        "web_search":False, "stakes":STAKES,
    }
    result, captured_prompts = _critique_plan_with_prompt_capture(
        engine, {**common, "plan_text":PLAN, "round":7}, log_root / "round7",
    )
    after = _state(state_path)
    audits = list((log_root / "round7").glob("*.json"))
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
    if len(captured_prompts) != len(attempts):
        raise RuntimeError("captured correction prompts do not match provider attempts")
    durable = cc.load_lineage(state_root, LINEAGE, stamp="reload", mode=cc.PLAN_MODE)
    closed_or_replaced = durable.classes[CLASS_ID].status in {cc.CLOSED, cc.SUPERSEDED}
    sibling_classes = [durable.classes[SIBLING_CLASS_ID]]
    sibling_debt = [
        row for row in durable.review_state.get("debt", [])
        if row.get("status") == "open" and row.get("severity") in rc.BLOCKING
        and row.get("finding_id") != "G1"
        and any(item.class_id in row.get("class_ids", []) for item in sibling_classes)
    ]
    settlement = audit.get("staged_settlement") or {}
    sibling_finding_ids = {row["finding_id"] for row in sibling_debt}
    sibling_findings = [
        row for row in settlement.get("findings", [])
        if row.get("id") in sibling_finding_ids
        and any(
            _anchor_covers_plan_line(anchor, SIBLING_LINE)
            for anchor in row.get("evidence", [])
        )
    ]
    if not (
        closed_or_replaced and sibling_classes and sibling_debt and sibling_findings
        and durable.review_state.get("phase") == "correction"
        and len(attempts) == 1 and attempts[0].get("outcome") == "completed"
    ):
        raise RuntimeError("real correction did not retain the expected sibling blocker")

    repair_result, repair_prompts = _critique_plan_with_prompt_capture(
        engine, {**common, "plan_text":FIXED_PLAN, "round":8}, log_root / "round8",
    )
    after_repair = _state(state_path)
    repair_audits = list((log_root / "round8").glob("*.json"))
    if len(repair_audits) != 1:
        raise RuntimeError(f"expected one repair audit, got {len(repair_audits)}")
    repair_audit = _state(repair_audits[0])
    repair_attempts = repair_audit.get("attempt_ledger")
    repair_reload = cc.load_lineage(
        state_root, LINEAGE, stamp="repair-reload", mode=cc.PLAN_MODE,
    )
    if not (
        isinstance(repair_attempts, list) and 1 <= len(repair_attempts) <= 2
        and repair_attempts[-1].get("outcome") == "completed"
        and repair_reload.review_state.get("phase") == "final"
        and repair_reload.classes[SIBLING_CLASS_ID].status == cc.CLOSED
        and not any(
            row.get("status") == "open" and row.get("severity") in rc.BLOCKING
            for row in repair_reload.review_state.get("debt", [])
        )
        and "STRUCTURAL-PHASE: final" in repair_result
        and "CONVERGENCE: NOT-BLOCKED" not in repair_result
    ):
        repair_diagnostic = {
            "phase":repair_reload.review_state.get("phase"),
            "classes":{
                class_id:tracked.status
                for class_id, tracked in repair_reload.classes.items()
            },
            "open_debt":[
                {
                    "finding_id":row.get("finding_id"),
                    "summary":row.get("summary"),
                    "class_ids":row.get("class_ids"),
                }
                for row in repair_reload.review_state.get("debt", [])
                if row.get("status") == "open"
            ],
            "attempts":[
                {key:row.get(key) for key in ("role", "outcome", "validation_issue")}
                for row in repair_attempts or []
            ],
            "result_tail":repair_result[-1200:],
        }
        raise RuntimeError(
            "later real correction did not stop at the final boundary: "
            + json.dumps(repair_diagnostic, ensure_ascii=False, sort_keys=True)
        )

    final_result, final_prompts = _critique_plan_with_prompt_capture(
        engine, {**common, "plan_text":FIXED_PLAN, "round":9}, log_root / "round9",
    )
    final_lineage = _state(state_path)
    final_audits = list((log_root / "round9").glob("*.json"))
    if len(final_audits) != 1:
        raise RuntimeError(f"expected one final audit, got {len(final_audits)}")
    final_audit = _state(final_audits[0])
    final_attempts = final_audit.get("attempt_ledger")
    final_reload = cc.load_lineage(
        state_root, LINEAGE, stamp="final-reload", mode=cc.PLAN_MODE,
    )
    if not (
        isinstance(final_attempts, list) and 1 <= len(final_attempts) <= 2
        and final_attempts[-1].get("role") in {"final", "final-validation-retry"}
        and final_attempts[-1].get("outcome") == "completed"
        and final_reload.review_state.get("phase") == "clear"
        and "STRUCTURAL-PHASE: clear" in final_result
        and "CONVERGENCE: NOT-BLOCKED" in final_result
    ):
        raise RuntimeError(
            "separate real cold final did not exclusively reach clear: "
            + json.dumps({
                "phase":final_reload.review_state.get("phase"),
                "classes":{
                    class_id:tracked.status
                    for class_id, tracked in final_reload.classes.items()
                },
                "open_debt":[
                    {
                        "finding_id":row.get("finding_id"),
                        "summary":row.get("summary"),
                        "class_ids":row.get("class_ids"),
                    }
                    for row in final_reload.review_state.get("debt", [])
                    if row.get("status") == "open"
                ],
                "attempts":[
                    {key:row.get(key) for key in (
                        "role", "outcome", "validation_issue",
                    )}
                    for row in final_attempts or []
                ],
                "result_tail":final_result[-1200:],
            }, ensure_ascii=False, sort_keys=True)
        )
    elapsed = time.monotonic() - started
    revision = _run("git", "rev-parse", "HEAD")
    source_paths = list(ACCEPTANCE_SOURCES)
    artifact = {
        "acceptance_kind":"persistent-correction-gate-public-plan-handler",
        "version":2, "date":"2026-08-24", "source_revision":revision,
        "source_sha256":{
            path:hashlib.sha256(_git_bytes("show", f"{revision}:{path}")).hexdigest()
            for path in source_paths
        },
        "allowed_later_source_diffs":{},
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
        "correction_prompt":captured_prompts[0],
        "correction_prompt_sha256":_sha(captured_prompts[0]),
        "sibling_binding":{
            "class_id":SIBLING_CLASS_ID,
            "debt_id":sibling_debt[0]["id"],
            "finding_id":sibling_findings[0]["id"],
            "anchor":f"plan:{SIBLING_LINE}",
            "provider_evidence":sibling_findings[0]["evidence"],
        },
        "repair_plan":FIXED_PLAN, "repair_plan_sha256":_sha(FIXED_PLAN),
        "repair_result_text":repair_result,
        "repair_result_sha256":_sha(repair_result),
        "repair_prompts":repair_prompts,
        "repair_prompt_sha256":[_sha(prompt) for prompt in repair_prompts],
        "repair_audit":repair_audit, "repair_attempt_ledger":repair_attempts,
        "after_repair_lineage":after_repair,
        "repair_durable_reload_lineage":cc._to_json(repair_reload),
        "final_result_text":final_result,
        "final_result_sha256":_sha(final_result),
        "final_prompts":final_prompts,
        "final_prompt_sha256":[_sha(prompt) for prompt in final_prompts],
        "final_audit":final_audit, "final_attempt_ledger":final_attempts,
        "final_lineage":final_lineage,
        "final_durable_reload_lineage":cc._to_json(final_reload),
        "total_provider_call_count":(
            len(attempts) + len(repair_attempts) + len(final_attempts)
        ),
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
