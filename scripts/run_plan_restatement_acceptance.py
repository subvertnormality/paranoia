#!/usr/bin/env python3
"""Retain real-provider evidence for proactive plan-restatement discovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import class_closure as cc
from paranoia_local import engines, handlers, orientation, prompts, review_census as rc
from paranoia_local import staged_protocol as sp

OUTPUT = ROOT / "docs" / "plan_restatement_acceptance_2026-09-01.json"
DISCOVERY_LINEAGE = "plan-restatement-discovery-acceptance-20260901"
TARGETED_LINEAGE = "plan-restatement-targeted-control-20260901"
STAKES = (
    "One trusted operator and OS; repository and plan bytes are untrusted data only; "
    "no repository execution, hostile local race, compromised OS, or multitenancy; "
    "one small plan; false clearance is high impact and recoverable blocking is acceptable."
)
DISCOVERY_PLAN = """# Queue batching change

## Governing limit
The queue batch maximum is normatively defined here as exactly 64 items. All implementations and tests must use this authority.

## Worker contract
This section independently and normatively defines the same queue batch maximum as exactly 64 items. The worker rejects a sixty-fifth item.

## API contract
This section independently and normatively defines the queue batch maximum as exactly 64 items. The API rejects a sixty-fifth item.

## Example
A worked example sends 64 items and succeeds. This example is illustrative and defers to the Governing limit.

## Implementation and acceptance
Update the queue configuration, worker, API documentation, and tests together. Run the focused queue tests and the full suite; fail delivery if either fails.
"""
TARGETED_PLAN = """# Targeted prompt correction

## Scope
Change only src/paranoia_local/prompts.py, tests/test_prompts.py, and README.md.

## Acceptance
Run `/home/andy/tools/paranoia-local/.venv/bin/pytest -q tests/test_prompts.py`; a nonzero exit blocks delivery.

## Documentation
Update README.md with the public behavior before delivery.

## Unrelated limits
This section independently defines the retry ceiling as 12.
Another operative section independently defines the retry ceiling as 12.
"""
SOURCES = (
    "AGENTS.md", "README.md", "src/paranoia_local/class_closure.py",
    "src/paranoia_local/handlers.py", "src/paranoia_local/prompts.py",
    "src/paranoia_local/review_census.py", "src/paranoia_local/staged_protocol.py",
    "scripts/run_plan_restatement_acceptance.py",
    "tests/test_plan_restatement_acceptance.py", "tests/test_prompts.py",
    "tests/test_review_census.py",
)


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode("utf-8", "surrogatepass"))


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _load_one(directory: Path, pattern: str) -> dict:
    paths = list(directory.glob(pattern))
    if len(paths) != 1:
        raise ValueError(f"expected one {pattern} record, found {len(paths)}")
    return json.loads(paths[0].read_text(encoding="utf-8"))


def _capture_call(
    arguments: dict, *, state_root: Path, log_dir: Path,
) -> tuple[str, list[str], dict, dict, list[dict]]:
    prompts: list[str] = []
    channels: dict[str, dict] = {}
    original_run = engines.CodexEngine.run
    original_resume = engines.CodexEngine.resume

    def capture_run(self, prompt, *args, **kwargs):
        prompts.append(prompt)
        review = original_run(self, prompt, *args, **kwargs)
        channels[review.session_ref or f"missing-{len(channels)}"] = {
            "session_ref":review.session_ref, "response_text":review.text or "",
            "raw":review.raw or "", "failure_detail":review.failure_detail or "",
            "stderr":review.stderr or "", "returncode":review.returncode,
            "error":review.error, "usage":review.usage,
        }
        return review

    def capture_resume(self, session_ref, prompt, *args, **kwargs):
        prompts.append(prompt)
        review = original_resume(self, session_ref, prompt, *args, **kwargs)
        channels[review.session_ref or f"missing-{len(channels)}"] = {
            "session_ref":review.session_ref, "response_text":review.text or "",
            "raw":review.raw or "", "failure_detail":review.failure_detail or "",
            "stderr":review.stderr or "", "returncode":review.returncode,
            "error":review.error, "usage":review.usage,
        }
        return review

    previous_root = os.environ.get(cc.STATE_ROOT_ENV)
    os.environ[cc.STATE_ROOT_ENV] = str(state_root)
    engines.CodexEngine.run = capture_run
    engines.CodexEngine.resume = capture_resume
    try:
        result = handlers.critique_plan(
            arguments, engine=engines.CodexEngine(), log_dir=log_dir,
        )
    finally:
        engines.CodexEngine.run = original_run
        engines.CodexEngine.resume = original_resume
        if previous_root is None:
            os.environ.pop(cc.STATE_ROOT_ENV, None)
        else:
            os.environ[cc.STATE_ROOT_ENV] = previous_root
    audit = _load_one(log_dir, "*-critique_plan-*.json")
    lineage = json.loads(
        (cc.lineage_dir(state_root) / f"{arguments['lineage']}.json").read_text(
            encoding="utf-8",
        )
    )
    (log_dir / "captured_prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    ordered_channels = [
        channels[item["session_ref"]] for item in audit["attempt_ledger"]
    ]
    (log_dir / "exact_attempt_channels.json").write_text(
        json.dumps(ordered_channels, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result, prompts, audit, lineage, ordered_channels


def _targeted_components() -> tuple[dict[str, cc.TrackedClass], list[dict]]:
    classes: dict[str, cc.TrackedClass] = {}
    debt: list[dict] = []
    definitions = (
        ("exact-scope", "The plan names the exact files in scope.", "plan:3-4"),
        ("exact-command", "The plan names an executable acceptance command.", "plan:6-7"),
        ("fail-closed", "The plan states that acceptance failure blocks delivery.", "plan:6-7"),
    )
    for index, (class_id, invariant, anchor) in enumerate(definitions, 1):
        classes[class_id] = cc.TrackedClass(
            class_id, invariant, cc.MAJOR, 1, cc.OPEN,
            procedure=f"Inspect {anchor} for the named obligation.",
        )
        debt.append({
            "id":f"D{index}", "finding_id":f"G{index}", "status":"open",
            "severity":"MAJOR", "summary":invariant, "reason":"seeded control debt",
            "remedy":f"Satisfy {invariant}", "evidence":[anchor], "source_ids":[],
            "class_ids":[class_id], "first_round":1, "last_round":1,
        })
    return classes, debt


def _targeted_seed(state_root: Path) -> None:
    parent = orientation.resolve_head(ROOT)
    snapshot = orientation.wrap_commit(
        ROOT, orientation.snapshot_tree(ROOT, parent), parent,
    )
    structural = rc.digest(f"{TARGETED_PLAN}\0{snapshot}")
    state = rc.normalize_state(None, stakes=STAKES, snapshot=structural)
    classes, debt = _targeted_components()
    state.update(phase="correction", last_round=1, debt=debt)
    cc.save_lineage(state_root, cc.Lineage(
        TARGETED_LINEAGE, rounds=1, next_seq=4, classes=classes,
        review_state=state, mode=cc.PLAN_MODE,
    ))


def _anchor_covers(anchor: object, line: int) -> bool:
    if not isinstance(anchor, str) or not anchor.startswith("plan:"):
        return False
    start, dash, end = anchor.removeprefix("plan:").partition("-")
    if not start.isdigit() or (dash and not end.isdigit()):
        return False
    return int(start) <= line <= int(end or start)


def _replay_validated_payloads(row: dict, roles: list[str]) -> dict:
    """Re-run retained raw stdout through the production extractor and protocol."""
    responses: list[str] = []
    for channels in row["exact_attempt_channels"]:
        review = engines.CodexEngine().parse_output(channels["raw"])
        if (
            review.session_ref != channels["session_ref"]
            or review.text != channels["response_text"]
            or review.raw != channels["raw"]
            or review.error != channels["error"]
            or (review.failure_detail or "") != channels["failure_detail"]
            or review.usage != channels["usage"]
        ):
            raise ValueError("retained raw provider envelope does not reconstruct its response")
        responses.append(review.text)

    if roles[0].startswith("census-"):
        manifests: list[dict] = []
        for role, response in zip(roles[:3], responses[:3], strict=True):
            lane = role.removeprefix("census-")
            value = sp.decode_lane(response, mode=cc.PLAN_MODE, lane=lane)
            sp.validate_lane_value(value, lane=lane, active_classes=[])
            renamed = {finding["id"]:f"{lane}:{finding['id']}" for finding in value["findings"]}
            for finding in value["findings"]:
                finding["id"] = renamed[finding["id"]]
            for coverage in value["coverage"]:
                coverage["finding_ids"] = [
                    renamed[finding_id] for finding_id in coverage["finding_ids"]
                ]
            for assessment in value["class_assessments"]:
                if assessment["finding_id"] is not None:
                    assessment["finding_id"] = renamed[assessment["finding_id"]]
            manifests.append(value)
        sources = [finding for manifest in manifests for finding in manifest["findings"]]
        settlement = sp.materialize_decision(
            responses[3], mode=cc.PLAN_MODE, role="census",
            source_ids=[finding["id"] for finding in sources],
            source_severities={finding["id"]:finding["severity"] for finding in sources},
            source_evidence={finding["id"]:finding["evidence"] for finding in sources},
            assessment_verdicts={}, assessment_findings={}, assessment_evidence={},
            active_classes=[], durable_debt=[],
        )
        return {"manifests":manifests, "settlement":settlement}

    task = json.loads(row["prompts"][0].split("===== TASK INPUT =====\n\n", 1)[1])
    settlement = sp.materialize_decision(
        responses[0], mode=cc.PLAN_MODE, role="correction",
        active_classes=task["active_classes"], durable_debt=task["existing_debt"],
    )
    return {"manifests":[], "settlement":settlement}


def _reconstruct_prompts(row: dict, roles: list[str]) -> list[str]:
    """Render the exact expected provider inputs through production prompt builders."""
    if roles[0].startswith("census-"):
        body = handlers._plan_body(
            sp.ArtifactView.from_text(DISCOVERY_PLAN), None, None, [], True,
        )
        body = (
            f"=== REVIEW STAKES ===\n{STAKES}\n\n{body}\n\n"
            "The pinned repository evidence root is `repository/`. Treat that prefix "
            "as the project root; no live Git or web tools are available."
        )
        manifests = row["validated_payloads"]["manifests"]
        expected = [
            handlers._staged_lane_prompt(
                mode=cc.PLAN_MODE, lane=lane, active_classes=[], body=body,
            )
            for lane in sp.LANES[cc.PLAN_MODE]
        ]
        consolidation_body = json.dumps({
            "role":"census", "stakes":STAKES, "manifests":manifests,
            "active_classes":[], "existing_debt":[],
        }, ensure_ascii=False, separators=(",", ":"))
        expected.append(prompts.compose(
            f"{prompts.staged_consolidation_instructions(cc.PLAN_MODE)}\n"
            f"{sp.citation_instructions(cc.PLAN_MODE)}\n"
            f"{sp.class_decision_instructions(cc.PLAN_MODE, 'census', active_classes=[])}",
            consolidation_body,
        ))
        return expected

    classes, debt = _targeted_components()
    lineage = cc.Lineage(
        TARGETED_LINEAGE, rounds=1, next_seq=4, classes=classes,
        review_state={"debt":debt}, mode=cc.PLAN_MODE,
    )
    body = handlers._plan_body(
        sp.ArtifactView.from_text(TARGETED_PLAN), None, None, [], True,
        class_blocks=[cc.render_unmechanized(lineage)],
    )
    body += (
        "\n\nThe pinned repository evidence root is `repository/`. Treat that prefix "
        "as the project root; no live Git or web tools are available."
    )
    expected_task = {
        "role":"correction", "stakes":STAKES, "existing_debt":debt,
        "active_classes":handlers._active_class_rows(lineage, cc.PLAN_MODE),
        "correction_gates":[], "checklist":[],
        "artifact":f"=== REVIEW STAKES ===\n{STAKES}\n\n{body}",
        "review_scope":"targeted",
    }
    task = json.loads(row["prompts"][0].split("===== TASK INPUT =====\n\n", 1)[1])
    if task != expected_task:
        raise ValueError("targeted prompt task differs from its seeded production reconstruction")
    outcome_ids = sp.expected_outcome_class_ids(
        "correction", active_classes=task["active_classes"],
        durable_debt=task["existing_debt"],
    )
    instructions = (
        f"{prompts.staged_followup_instructions(cc.PLAN_MODE)}\n"
        f"{sp.citation_instructions(cc.PLAN_MODE)}\n"
        f"{sp.class_decision_instructions(cc.PLAN_MODE, 'correction', active_classes=task['active_classes'], outcome_class_ids=outcome_ids, correction_gates=[])}"
    )
    return [prompts.compose(instructions, json.dumps(expected_task, ensure_ascii=False))]


def validate_artifact(
    artifact: dict, root: Path = ROOT, *, require_committed: bool = True,
) -> None:
    expected = {
        "acceptance_kind", "version", "date", "source_revision", "source_sha256",
        "allowed_later_source_diffs",
        "provider", "stakes", "discovery", "targeted_control", "claims",
    }
    if set(artifact) != expected:
        raise ValueError("acceptance envelope is not closed")
    if (
        artifact["acceptance_kind"] != "plan-normative-restatement-public-handler-v1"
        or artifact["version"] != 1 or artifact["date"] != "2026-09-01"
        or artifact["stakes"] != STAKES
    ):
        raise ValueError("acceptance identity is not exact")
    if require_committed:
        committed = json.loads(_git("show", f"HEAD:{OUTPUT.relative_to(root)}"))
        if committed != artifact:
            raise ValueError("acceptance differs from its committed Git envelope")
    revision = artifact["source_revision"]
    if _git("rev-parse", f"{revision}^{{commit}}") != revision:
        raise ValueError("source revision is not a canonical commit")
    if set(artifact["source_sha256"]) != set(SOURCES):
        raise ValueError("source inventory is not exact")
    changed: set[str] = set()
    allowed = artifact["allowed_later_source_diffs"]
    if not isinstance(allowed, dict):
        raise ValueError("later-source allowance inventory is absent")
    for relative, digest in artifact["source_sha256"].items():
        historical = subprocess.run(
            ["git", "show", f"{revision}:{relative}"], cwd=root, check=True,
            stdout=subprocess.PIPE,
        ).stdout
        if _sha_bytes(historical) != digest:
            raise ValueError(f"historical source binding mismatch for {relative}")
        if (root / relative).read_bytes() != historical:
            changed.add(relative)
            row = allowed.get(relative)
            if not isinstance(row, dict) or set(row) != {"sha256", "scope"}:
                raise ValueError(f"later-source allowance is absent for {relative}")
            diff = subprocess.run(
                ["git", "diff", "--no-ext-diff", revision, "--", relative],
                cwd=root, check=True, stdout=subprocess.PIPE,
            ).stdout
            if _sha_bytes(diff) != row["sha256"] or not row["scope"].strip():
                raise ValueError(f"later-source allowance mismatch for {relative}")
    if changed != set(allowed):
        raise ValueError("later-source allowance inventory is not exact")
    provider = artifact["provider"]
    if set(provider) != {"engine", "model", "effort", "cli_version"}:
        raise ValueError("provider binding is not closed")
    if provider["engine"] != "codex" or provider["model"] != "gpt-5.6-sol":
        raise ValueError("provider route is not the accepted Codex route")

    discovery = artifact["discovery"]
    targeted = artifact["targeted_control"]
    for row, plan, lineage_id, roles in (
        (discovery, DISCOVERY_PLAN, DISCOVERY_LINEAGE,
         ["census-domain", "census-execution", "census-integrity", "consolidation"]),
        (targeted, TARGETED_PLAN, TARGETED_LINEAGE, ["correction"]),
    ):
        if set(row) != {
            "lineage", "plan", "prompts", "prompt_sha256", "result_text",
            "result_sha256", "audit", "durable_lineage", "validated_payloads",
            "validated_payload_sha256", "provider_response_sha256",
            "exact_attempt_channels",
        }:
            raise ValueError("route record is not closed")
        if row["lineage"] != lineage_id or row["plan"] != plan:
            raise ValueError("route input binding changed")
        if row["prompt_sha256"] != [_sha_text(item) for item in row["prompts"]]:
            raise ValueError("prompt digest mismatch")
        if row["prompts"] != _reconstruct_prompts(row, roles):
            raise ValueError("retained prompts differ from production reconstruction")
        if row["result_sha256"] != _sha_text(row["result_text"]):
            raise ValueError("result digest mismatch")
        attempts = row["audit"].get("attempt_ledger")
        if [item.get("role") for item in attempts or []] != roles:
            raise ValueError("provider call topology changed")
        if any(item.get("outcome") != "completed" for item in attempts):
            raise ValueError("acceptance contains a failed provider attempt")
        if row["provider_response_sha256"] != [
            item.get("response_sha256") for item in attempts
        ]:
            raise ValueError("provider response digests are not attempt-bound")
        for prompt, attempt, channels in zip(
            row["prompts"], attempts, row["exact_attempt_channels"], strict=True,
        ):
            session_ref = attempt.get("session_ref")
            role = attempt.get("role")
            role_marker = (
                f"ROLE: census lane {role.removeprefix('census-')}"
                if isinstance(role, str) and role.startswith("census-")
                else '"role":"census"' if role == "consolidation"
                else '"role": "correction"'
            )
            required_channels = (
                "raw_sha256", "response_sha256", "failure_detail_sha256",
                "stderr_sha256",
            )
            if (
                not isinstance(session_ref, str) or not session_ref
                or any(
                    not isinstance(attempt.get(key), str)
                    or len(attempt[key]) != 64
                    for key in required_channels
                )
                or not attempt.get("raw_excerpt", "").startswith(
                    '{"type":"thread.started","thread_id":' + json.dumps(session_ref)
                )
                or not isinstance(attempt.get("response_excerpt"), str)
                or not attempt["response_excerpt"]
                or role_marker not in prompt
            ):
                raise ValueError("attempt channel, session, role, and prompt binding failed")
            exact_fields = {
                "session_ref", "response_text", "raw", "failure_detail", "stderr",
                "returncode", "error", "usage",
            }
            if set(channels) != exact_fields or channels["session_ref"] != session_ref:
                raise ValueError("exact attempt channels are not closed and session-bound")
            for value_key, digest_key, excerpt_key in (
                ("response_text", "response_sha256", "response_excerpt"),
                ("raw", "raw_sha256", "raw_excerpt"),
                ("failure_detail", "failure_detail_sha256", "failure_detail_excerpt"),
                ("stderr", "stderr_sha256", "stderr_excerpt"),
            ):
                if (
                    _sha_text(channels[value_key]) != attempt[digest_key]
                    or channels[value_key][:4000] != (attempt.get(excerpt_key) or "")
                ):
                    raise ValueError(f"exact {value_key} channel digest mismatch")
            if channels["returncode"] != attempt["returncode"]:
                raise ValueError("exact return code differs from the attempt ledger")
            if channels["error"] is not False or channels["usage"] != attempt["usage"]:
                raise ValueError("exact parser status or usage differs from the attempt ledger")
        expected_payloads = {
            "manifests":row["audit"].get("staged_manifests") or [],
            "settlement":row["audit"].get("staged_settlement"),
        }
        if row["validated_payloads"] != expected_payloads:
            raise ValueError("exact validated responses differ from the audit projection")
        if _replay_validated_payloads(row, roles) != expected_payloads:
            raise ValueError("raw provider envelopes do not replay to the audited payloads")
        payload_digest = _sha_text(json.dumps(
            expected_payloads, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ))
        if row["validated_payload_sha256"] != payload_digest:
            raise ValueError("validated response payload digest mismatch")
        for manifest in expected_payloads["manifests"]:
            lane = manifest.get("lane")
            parsed = sp.decode_canonical_lane(
                json.dumps(manifest, ensure_ascii=False), mode=cc.PLAN_MODE, lane=lane,
            )
            sp.validate_lane_value(parsed, lane=lane, active_classes=[])
        if not row["result_text"].endswith(row["audit"].get("rendered_trailer", "")):
            raise ValueError("rendered trailer is not the returned durable result")

    findings = discovery["audit"]["staged_settlement"]["findings"]
    settlement = discovery["audit"]["staged_settlement"]
    records = settlement["class_records"]
    dispositions = {
        row["finding_id"]:records[row["record_index"]]
        for row in settlement["class_dispositions"]
        if row["kind"] == "new_class"
    }
    matches = [
        row for row in findings
        if "authorit" in dispositions.get(row["id"], {}).get("invariant", "").lower()
        and any(
            token in dispositions[row["id"]]["invariant"].lower()
            for token in ("exactly one", "single")
        )
    ]
    if len(matches) != 1:
        raise ValueError("discovery did not produce one aggregate restatement finding")
    evidence = matches[0]["evidence"]
    if not all(any(_anchor_covers(anchor, line) for anchor in evidence) for line in (4, 7, 10)):
        raise ValueError("aggregate finding omits an operative authority")
    if any(_anchor_covers(anchor, 13) for anchor in evidence):
        raise ValueError("illustrative deferred example was treated as independent authority")
    if discovery["durable_lineage"]["review_state"]["phase"] != "correction":
        raise ValueError("discovery did not persist blocking structural debt")

    targeted_task = json.loads(targeted["prompts"][0].split("===== TASK INPUT =====\n\n", 1)[1])
    if targeted_task.get("review_scope") != "targeted" or targeted_task.get("checklist") != []:
        raise ValueError("targeted control did not use the bounded correction scope")
    settlement = targeted["audit"]["staged_settlement"]
    if settlement["findings"] or targeted["durable_lineage"]["review_state"]["phase"] != "final":
        raise ValueError("targeted correction discovered unrelated novelty or failed to close")
    if any(_anchor_covers(anchor, 12) for row in settlement["findings"] for anchor in row["evidence"]):
        raise ValueError("targeted correction audited the unrelated restatement cluster")
    claims = artifact["claims"]
    if set(claims) != {"proves", "does_not_prove"}:
        raise ValueError("acceptance claims are not closed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--reuse-run-root", type=Path)
    parser.add_argument("--source-revision")
    args = parser.parse_args()
    if args.validate_only:
        validate_artifact(json.loads(args.output.read_text(encoding="utf-8")))
        return 0
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("commit bound source changes before generating acceptance")
    revision = args.source_revision or _git("rev-parse", "HEAD")
    if args.reuse_run_root and not args.source_revision:
        raise ValueError("--reuse-run-root requires --source-revision")
    run_root = args.reuse_run_root or Path(tempfile.mkdtemp(
        prefix="plan-restatement-acceptance-",
    ))

    def retained_route(name: str, lineage_id: str) -> tuple:
        log_dir = run_root / f"{name}-logs"
        audit = _load_one(log_dir, "*-critique_plan-*.json")
        prompts = json.loads((log_dir / "captured_prompts.json").read_text(
            encoding="utf-8",
        ))
        channels = json.loads((log_dir / "exact_attempt_channels.json").read_text(
            encoding="utf-8",
        ))
        for channel in channels:
            if "error" not in channel or "usage" not in channel:
                parsed = engines.CodexEngine().parse_output(channel["raw"])
                channel["error"] = parsed.error
                channel["usage"] = parsed.usage
        lineage = json.loads(
            (run_root / f"{name}-state" / "lineages" / f"{lineage_id}.json").read_text(
                encoding="utf-8",
            )
        )
        review = engines.Review(
            text=audit["text"], session_ref=audit["session_ref"], raw=audit["text"],
        )
        result = handlers._footer(review, engines.CodexEngine())
        result += "\n\n" + audit["rendered_trailer"]
        return result, prompts, audit, lineage, channels

    if args.reuse_run_root:
        discovery = retained_route("discovery", DISCOVERY_LINEAGE)
        targeted = retained_route("targeted", TARGETED_LINEAGE)
    else:
        discovery = _capture_call({
            "repo_path":str(ROOT), "plan_text":DISCOVERY_PLAN,
            "lineage":DISCOVERY_LINEAGE, "round":1, "class_closure":True,
            "claim_verification":False, "web_search":False,
            "model":"gpt-5.6-sol", "effort":"high", "stakes":STAKES,
        }, state_root=run_root / "discovery-state", log_dir=run_root / "discovery-logs")
        targeted_state = run_root / "targeted-state"
        _targeted_seed(targeted_state)
        targeted = _capture_call({
            "repo_path":str(ROOT), "plan_text":TARGETED_PLAN,
            "lineage":TARGETED_LINEAGE, "round":2, "class_closure":True,
            "claim_verification":False, "web_search":False,
            "model":"gpt-5.6-sol", "effort":"high", "stakes":STAKES,
        }, state_root=targeted_state, log_dir=run_root / "targeted-logs")

    def route(lineage_id: str, plan: str, value: tuple) -> dict:
        result, prompts, audit, lineage, channels = value
        validated_payloads = {
            "manifests":audit.get("staged_manifests") or [],
            "settlement":audit.get("staged_settlement"),
        }
        return {
            "lineage":lineage_id, "plan":plan, "prompts":prompts,
            "prompt_sha256":[_sha_text(item) for item in prompts],
            "result_text":result, "result_sha256":_sha_text(result),
            "audit":audit, "durable_lineage":lineage,
            "validated_payloads":validated_payloads,
            "validated_payload_sha256":_sha_text(json.dumps(
                validated_payloads, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            )),
            "provider_response_sha256":[
                item["response_sha256"] for item in audit["attempt_ledger"]
            ],
            "exact_attempt_channels":channels,
        }

    artifact = {
        "acceptance_kind":"plan-normative-restatement-public-handler-v1",
        "version":1, "date":"2026-09-01", "source_revision":revision,
        "source_sha256":{
            relative:_sha_bytes(subprocess.run(
                ["git", "show", f"{revision}:{relative}"], cwd=ROOT, check=True,
                stdout=subprocess.PIPE,
            ).stdout) for relative in SOURCES
        },
        "allowed_later_source_diffs":{},
        "provider":{
            "engine":"codex", "model":"gpt-5.6-sol", "effort":"high",
            "cli_version":subprocess.run(
                ["codex", "--version"], check=True, capture_output=True, text=True,
            ).stdout.strip(),
        },
        "stakes":STAKES,
        "discovery":route(DISCOVERY_LINEAGE, DISCOVERY_PLAN, discovery),
        "targeted_control":route(TARGETED_LINEAGE, TARGETED_PLAN, targeted),
        "claims":{
            "proves":[
                "A real Codex four-call broad plan census produced one aggregate finding for every independently authoritative operative restatement.",
                "The same finding excluded an illustrative example that explicitly deferred to the governing authority.",
                "A separate real Codex targeted correction closed three supplied classes without discovering an unrelated restatement cluster.",
            ],
            "does_not_prove":[
                "Every future provider response will classify every semantic restatement correctly.",
                "Textual equality by itself identifies normative authority.",
                "Branch review behavior changed.",
            ],
        },
    }
    for relative in SOURCES:
        historical = subprocess.run(
            ["git", "show", f"{revision}:{relative}"], cwd=ROOT, check=True,
            stdout=subprocess.PIPE,
        ).stdout
        if (ROOT / relative).read_bytes() != historical:
            diff = subprocess.run(
                ["git", "diff", "--no-ext-diff", revision, "--", relative],
                cwd=ROOT, check=True, stdout=subprocess.PIPE,
            ).stdout
            artifact["allowed_later_source_diffs"][relative] = {
                "sha256":_sha_bytes(diff),
                "scope":"Acceptance-only replay support and structural validator correction; production plan-review prompts and handler behavior are unchanged.",
            }
    validate_artifact(artifact, require_committed=False)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
