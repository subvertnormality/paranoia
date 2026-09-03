#!/usr/bin/env python3
"""Retain real-provider evidence for proactive plan-restatement discovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import class_closure as cc
from paranoia_local import engines, handlers, orientation, prompts, review_census as rc
from paranoia_local import staged_protocol as sp

OUTPUT = ROOT / "docs" / "plan_restatement_acceptance_2026-09-01.json"
DISCOVERY_LINEAGE = "plan-restatement-discovery-acceptance-20260901"
TARGETED_LINEAGE = "plan-restatement-targeted-control-20260901"
FINAL_LINEAGE = TARGETED_LINEAGE
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
    "AGENTS.md", "README.md", "scripts/run_plan_restatement_acceptance.py",
    "tests/test_plan_restatement_acceptance.py", "tests/test_prompts.py",
    "tests/test_review_census.py",
    *tuple(
        f"src/paranoia_local/{name}" for name in (
            "__init__.py", "arbitrate_handler.py", "arbitration.py",
            "arbitration_research.py", "class_closure.py", "cli.py", "config.py",
            "engines.py", "evidence.py", "external_sources.py", "handlers.py",
            "inert_git.py", "inert_tree.py", "logs.py", "orientation.py",
            "plan_claims.py", "prompts.py", "review_census.py", "runner.py",
            "server.py", "staged_protocol.py", "textsafe.py", "worktree.py",
        )
    ),
)
CLAIMS = {
    "proves":[
        "A real Codex four-call broad plan census produced one aggregate finding for every independently authoritative operative restatement.",
        "The same finding excluded an illustrative example that explicitly deferred to the governing authority.",
        "A separate real Codex targeted correction closed three supplied classes without discovering an unrelated restatement cluster.",
        "A following real Codex cold final discovered that unrelated operative restatement cluster and persisted blocking debt.",
    ],
    "does_not_prove":[
        "Every future provider response will classify every semantic restatement correctly.",
        "Textual equality by itself identifies normative authority.",
        "Branch review behavior changed.",
    ],
}
ISSUE_98_INVARIANT_SWEEP_INSTRUCTIONS = """For every supplied unmechanized active class that this role assesses, treat the class invariant and
procedure as the primary search boundary, not the current finding, debt wording, known anchors, or
claimed patch. Enumerate every distinct site or property category named by that invariant or
procedure and inspect the complete reviewed artifact for each one before returning `satisfied` or
closing the class. The assessment evidence rationales must account for every named category,
including an explicit statement when a category has no applicable site. If any occurrence remains,
report all independently evidenced occurrences in the class's single aggregate finding. Do not
accept a repair merely because it resolves every previously cited site."""


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


def _audit_projection(audit: dict) -> dict:
    """Retain only audit fields the source-bound public replay reproduces exactly."""
    projected = json.loads(json.dumps(audit, ensure_ascii=False))
    projected.pop("timestamp", None)
    for attempt in projected.get("attempt_ledger") or []:
        attempt.pop("duration_ms", None)
        attempt.pop("stderr_sha256", None)
        attempt.pop("stderr_excerpt", None)
    return projected


def _capture_call(
    arguments: dict, *, state_root: Path, log_dir: Path,
) -> tuple[str, list[str], dict, dict, list[dict], list[dict]]:
    prompts: list[str] = []
    channels: dict[str, dict] = {}
    invocations: list[dict] = []
    original_run = engines.CodexEngine.run
    original_resume = engines.CodexEngine.resume

    def capture_run(self, prompt, *args, **kwargs):
        prompts.append(prompt)
        invocations.append(_invocation(prompt, args, kwargs))
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
        invocations.append(_invocation(prompt, args, kwargs))
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
    (log_dir / "exact_invocations.json").write_text(
        json.dumps(invocations, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result, prompts, audit, lineage, ordered_channels, invocations


def _invocation(prompt: str, args: tuple, kwargs: dict) -> dict:
    schema = kwargs.get("response_schema")
    schema_text = json.dumps(
        schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return {
        "prompt_sha256": _sha_text(prompt),
        "model": args[1] if len(args) > 1 else kwargs.get("model"),
        "effort": args[2] if len(args) > 2 else kwargs.get("effort"),
        "timeout": kwargs.get("timeout"),
        "web_search": args[3] if len(args) > 3 else kwargs.get("web_search"),
        "response_schema_sha256": _sha_text(schema_text),
        "response_schema": schema,
    }


def _historical_no_concession_prompt(prompt: str) -> str:
    """Project a current empty-concession prompt to this pre-cutover artifact."""
    prompt = prompt.replace(
        "For a satisfied unmechanized class, omit flat evidence and emit member_coverage containing every\n"
        "server-supplied stable member ID exactly once with its own evidence. A legacy class with no members\n"
        "cannot be satisfied; report it violated for replacement with an inventoried definition.\n\n",
        "\n",
    )
    prompt = prompt.replace(ISSUE_98_INVARIANT_SWEEP_INSTRUCTIONS + "\n\n", "")
    prompt = prompt.replace(
        "For a satisfied unmechanized assessment or outcome, omit flat `evidence` and emit\n"
        "`member_coverage` with exactly one row for every stable member ID in that class's server-supplied\n"
        "`members` list. Bind each member to its own evidence. Different members may cite the same anchor;\n"
        "the server checks member identity before deriving and deduplicating the flat durable evidence. A\n"
        "class with an empty legacy member list cannot be satisfied: replace it with a definition containing\n"
        "the complete stable inventory. If any member remains violated, return `violated` instead.\n\n",
        "",
    )
    prompt = prompt.replace(
        " Every unmechanized new or replacement definition must enumerate\n"
        "the complete closed set of stable member IDs governed by its invariant.",
        "",
    )
    prompt = prompt.replace(
        " Every unmechanized new-class definition must enumerate the complete closed set of stable\n"
        "member IDs governed by its invariant.",
        "",
    )
    prompt = prompt.replace(
        "In correction, a standalone `close` for an otherwise outcome-optional unmechanized class must\n"
        "author that class's `satisfied` outcome and evidence; an evidence-free lifecycle action cannot\n"
        "establish that the invariant-wide search completed.\n\n",
        "",
    )
    owns_class_guidance = (
        "class_outcomes is a closed object permitting exactly these class IDs:" in prompt
    )
    prompt, count = re.subn(
        r"class_outcomes is a closed object permitting exactly these class IDs: "
        r"\[[^\]]*\](?:; required keys are exactly: |\. Every permitted key is "
        r"required by the provider schema; use null for a semantically optional "
        r"outcome that you are not authoring\. Non-null outcomes are required "
        r"exactly for these class IDs: )(\[[^\]]*\])\. ",
        r"class_outcomes is a closed object keyed by exactly these required class IDs: \1. ",
        prompt,
    )
    if owns_class_guidance and count != 1:
        raise ValueError("current prompt omits the #98 class-outcome guidance")
    prompt = prompt.replace(
        "Every close requires an authored satisfied outcome with evidence. When an authoritative "
        "outcome exists, reopen requires violated; other outcome-free standalone lifecycle "
        "actions remain legal only as listed. ",
        "When an authoritative outcome exists, close requires satisfied and reopen requires "
        "violated; outcome-free standalone lifecycle actions remain legal only as listed. ",
    )
    prompt = prompt.replace("PRIOR CONCESSIONS: {}\n", "")
    start = " concession_challenges is a closed object"
    finish = "Never put class_id inside an outcome or action value."
    if start in prompt:
        begin = prompt.index(start)
        end = prompt.index(finish, begin)
        prompt = prompt[:begin] + " " + prompt[end:]
    marker = "===== TASK INPUT =====\n\n"
    head, found, task_text = prompt.partition(marker)
    if found and task_text.startswith("{"):
        task = json.loads(task_text)
        prior = task.pop("prior_concessions", None)
        if prior not in (None, [], {}):
            raise ValueError("historical replay cannot discard a concession")
        for row in task.get("active_classes", []):
            row.pop("members", None)
        artifact = task.get("artifact")
        if isinstance(artifact, str):
            task["artifact"] = artifact.replace(
                "\n  authoritative members: MISSING — replace before satisfaction", "",
            )
        compact = task_text.startswith('{"role":"census"')
        task_text = json.dumps(
            task, ensure_ascii=False,
            separators=(",", ":") if compact else None,
        )
        prompt = head + found + task_text
    return prompt


def _historical_no_concession_invocation(
    prompt: str, args: tuple, kwargs: dict,
) -> dict:
    """Bind current replay to the exact pre-cutover prompt and schema."""
    value = _invocation(prompt, args, kwargs)
    value["prompt_sha256"] = _sha_text(_historical_no_concession_prompt(prompt))
    schema = deepcopy(value["response_schema"])

    def project_members(node):
        if isinstance(node, dict):
            alternatives = node.get("anyOf")
            if isinstance(alternatives, list):
                node["anyOf"] = [
                    item for item in alternatives
                    if "member_coverage" not in item.get("properties", {})
                ]
            properties = node.get("properties")
            if isinstance(properties, dict) and "members" in properties:
                properties.pop("members")
                node["required"] = [
                    item for item in node.get("required", []) if item != "members"
                ]
            for child in node.values():
                project_members(child)
        elif isinstance(node, list):
            for child in node:
                project_members(child)

    project_members(schema)
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if "concession_challenges" in properties:
        properties.pop("concession_challenges")
        if "concession_challenges" not in required:
            raise ValueError("current replay schema does not require concession_challenges")
        required.remove("concession_challenges")
    value["response_schema"] = schema
    value["response_schema_sha256"] = _sha_text(json.dumps(
        schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ))
    return value


def _pre_concession_response(text: str) -> str:
    """Project retained pre-#94/#106 payloads into the current decoder."""
    wire = json.loads(text)
    if "concession_challenges" in wire:
        raise ValueError("historical response unexpectedly owns a concession challenge")
    wire["concession_challenges"] = {}

    def add_historical_members(node):
        if isinstance(node, dict):
            if (
                "invariant" in node and "severity" in node and "procedure" in node
                and "members" not in node
            ):
                node["members"] = ["historical-single-member"]
            for child in node.values():
                add_historical_members(child)
        elif isinstance(node, list):
            for child in node:
                add_historical_members(child)

    add_historical_members(wire)
    return json.dumps(wire, ensure_ascii=False, separators=(",", ":"))


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


def _targeted_initial(snapshot: str) -> cc.Lineage:
    structural = rc.digest(f"{TARGETED_PLAN}\0{snapshot}")
    state = rc.normalize_state(None, stakes=STAKES, snapshot=structural)
    classes, debt = _targeted_components()
    state.update(phase="correction", last_round=1, debt=debt)
    return cc.Lineage(
        TARGETED_LINEAGE, rounds=1, next_seq=4, classes=classes,
        review_state=state, mode=cc.PLAN_MODE,
    )


def _targeted_seed(state_root: Path) -> cc.Lineage:
    parent = orientation.resolve_head(ROOT)
    snapshot = orientation.wrap_commit(
        ROOT, orientation.snapshot_tree(ROOT, parent), parent,
    )
    lineage = _targeted_initial(snapshot)
    cc.save_lineage(state_root, lineage)
    return lineage


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
        if review.raw != channels["raw"]:
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
            _pre_concession_response(responses[3]),
            mode=cc.PLAN_MODE, role="census",
            source_ids=[finding["id"] for finding in sources],
            source_severities={finding["id"]:finding["severity"] for finding in sources},
            source_evidence={finding["id"]:finding["evidence"] for finding in sources},
            assessment_verdicts={}, assessment_findings={}, assessment_evidence={},
            active_classes=[], durable_debt=[],
            require_closure_coverage=False,
        )
        if settlement.pop("concession_challenges", None) != []:
            raise ValueError("historical census concession projection is not empty")
        for record in settlement["class_records"]:
            record.pop("members", None)
        return {"manifests":manifests, "settlement":settlement}

    task = json.loads(row["prompts"][0].split("===== TASK INPUT =====\n\n", 1)[1])
    durable_debt = (
        row["initial_lineage"]["review_state"]["debt"]
        if roles[0] == "final" else task["existing_debt"]
    )
    role = roles[0]
    settlement = sp.materialize_decision(
        _pre_concession_response(responses[0]),
        mode=cc.PLAN_MODE, role=role,
        active_classes=task["active_classes"], durable_debt=durable_debt,
        require_closure_coverage=False,
    )
    if settlement.pop("concession_challenges", None) != []:
        raise ValueError("historical follow-up concession projection is not empty")
    for record in settlement["class_records"]:
        record.pop("members", None)
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
                prior_concessions_text="{}",
            )
            for lane in sp.LANES[cc.PLAN_MODE]
        ]
        consolidation_body = json.dumps({
            "role":"census", "stakes":STAKES, "manifests":manifests,
            "active_classes":[], "existing_debt":[], "prior_concessions":{},
        }, ensure_ascii=False, separators=(",", ":"))
        expected.append(prompts.compose(
            f"{prompts.staged_consolidation_instructions(cc.PLAN_MODE)}\n"
            f"{sp.citation_instructions(cc.PLAN_MODE)}\n"
            "PRIOR CONCESSIONS: {}\n"
            f"{sp.class_decision_instructions(cc.PLAN_MODE, 'census', active_classes=[], prior_concessions={})}",
            consolidation_body,
        ))
        return [_historical_no_concession_prompt(item) for item in expected]

    role = roles[0]
    if role == "final":
        lineage = cc._from_json(FINAL_LINEAGE, row["initial_lineage"])
        debt = [item for item in lineage.review_state["debt"] if item["status"] == "open"]
    else:
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
        "role":role, "stakes":STAKES, "existing_debt":debt,
        "active_classes":handlers._active_class_rows(lineage, cc.PLAN_MODE),
        "prior_concessions":{},
        "correction_gates":[],
        "checklist":list(sp.CHECKLIST) if role == "final" else [],
        "artifact":f"=== REVIEW STAKES ===\n{STAKES}\n\n{body}",
    }
    if role == "correction":
        expected_task["review_scope"] = "targeted"
    task = json.loads(row["prompts"][0].split("===== TASK INPUT =====\n\n", 1)[1])
    historical_task = dict(expected_task)
    historical_task.pop("prior_concessions")
    if task != historical_task:
        raise ValueError("targeted prompt task differs from its seeded production reconstruction")
    outcome_ids = sp.expected_outcome_class_ids(
        role, active_classes=task["active_classes"],
        durable_debt=task["existing_debt"],
    )
    instructions = (
        f"{prompts.staged_followup_instructions(cc.PLAN_MODE)}\n"
        f"{sp.citation_instructions(cc.PLAN_MODE)}\n"
        "PRIOR CONCESSIONS: {}\n"
        f"{sp.class_decision_instructions(cc.PLAN_MODE, role, active_classes=task['active_classes'], outcome_class_ids=outcome_ids, correction_gates=[], prior_concessions={})}"
    )
    return [_historical_no_concession_prompt(
        prompts.compose(instructions, json.dumps(expected_task, ensure_ascii=False)),
    )]


def _replay_public_handler(artifact: dict, source_tree: str) -> None:
    """Rebuild results and durable successors through the production public handler."""
    routes = (
        ("discovery", artifact["discovery"], DISCOVERY_PLAN, 1),
        ("targeted", artifact["targeted_control"], TARGETED_PLAN, 2),
        ("final", artifact["final_control"], TARGETED_PLAN, 3),
    )
    original_run = engines.CodexEngine.run
    original_resume = engines.CodexEngine.resume
    original_head = orientation.resolve_head
    original_tree = orientation.snapshot_tree
    original_decode = sp.decode_decision_with_issues
    original_materialize = sp.materialize_decision_value

    def replay_decode(text: str, *args, **kwargs):
        kwargs["require_closure_coverage"] = False
        return original_decode(_pre_concession_response(text), *args, **kwargs)

    def replay_materialize(*args, **kwargs):
        settlement = original_materialize(*args, **kwargs)
        if settlement.pop("concession_challenges", None) != []:
            raise ValueError("historical handler concession projection is not empty")
        return settlement
    previous_root = os.environ.get(cc.STATE_ROOT_ENV)
    with tempfile.TemporaryDirectory(prefix="plan-restatement-replay-") as raw_root:
        replay_root = Path(raw_root)
        os.environ[cc.STATE_ROOT_ENV] = str(replay_root / "state")
        orientation.resolve_head = lambda repo: artifact["source_revision"]
        orientation.snapshot_tree = lambda repo, parent: source_tree
        try:
            for name, row, plan, round_no in routes:
                if name == "targeted":
                    source_snapshot = orientation.wrap_commit(
                        ROOT, source_tree, artifact["source_revision"],
                    )
                    cc.save_lineage(
                        replay_root / "state",
                        _targeted_initial(source_snapshot),
                    )
                pending = {
                    invocation["prompt_sha256"]:(invocation, channels)
                    for invocation, channels in zip(
                        row["exact_invocations"], row["exact_attempt_channels"],
                        strict=True,
                    )
                }
                if len(pending) != len(row["exact_invocations"]):
                    raise ValueError("retained route contains duplicate provider prompts")

                def playback_run(self, prompt, *args, **kwargs):
                    actual = _historical_no_concession_invocation(prompt, args, kwargs)
                    matched = pending.pop(actual["prompt_sha256"], None)
                    if matched is None:
                        raise ValueError("public-handler replay admitted an unknown provider call")
                    invocation, channels = matched
                    if actual != invocation:
                        raise ValueError("public-handler replay invocation differs from retained input")
                    playback_engine = engines.CodexEngine()
                    return playback_engine._finalize_review(
                        playback_engine.parse_output(channels["raw"]),
                        returncode=channels["returncode"],
                        stderr="",
                        measured_duration_ms=0,
                    )

                engines.CodexEngine.run = playback_run
                engines.CodexEngine.resume = lambda *args, **kwargs: playback_run(
                    args[0], args[2], *args[3:], **kwargs
                )
                sp.decode_decision_with_issues = replay_decode
                sp.materialize_decision_value = replay_materialize
                log_dir = replay_root / f"{name}-logs"
                result = handlers.critique_plan({
                    "repo_path":str(ROOT), "plan_text":plan,
                    "lineage":row["lineage"], "round":round_no,
                    "class_closure":True, "claim_verification":False,
                    "web_search":False, "model":"gpt-5.6-sol",
                    "effort":"high", "stakes":STAKES,
                }, engine=engines.CodexEngine(), log_dir=log_dir,
                   now=lambda: "20260901T000000")
                if pending:
                    raise ValueError("public-handler replay omitted a retained invocation")
                replay_audit = _load_one(log_dir, "*-critique_plan-*.json")
                replay_lineage = json.loads(
                    (cc.lineage_dir(replay_root / "state") / f"{row['lineage']}.json")
                    .read_text(encoding="utf-8")
                )
                if result != row["result_text"]:
                    raise ValueError("public-handler replay did not reconstruct returned result")
                if replay_lineage != row["durable_lineage"]:
                    raise ValueError("public-handler replay did not reconstruct durable lineage")
                if _audit_projection(replay_audit) != row["audit_projection"]:
                    raise ValueError("public-handler replay did not reconstruct audit settlement")
        finally:
            engines.CodexEngine.run = original_run
            engines.CodexEngine.resume = original_resume
            sp.decode_decision_with_issues = original_decode
            sp.materialize_decision_value = original_materialize
            orientation.resolve_head = original_head
            orientation.snapshot_tree = original_tree
            if previous_root is None:
                os.environ.pop(cc.STATE_ROOT_ENV, None)
            else:
                os.environ[cc.STATE_ROOT_ENV] = previous_root


def _reconstruct_retained_successor(
    *, initial: dict, row: dict, plan: str, round_no: int, revision: str,
) -> dict:
    """Recover an intermediate durable successor without another provider call."""
    original_run = engines.CodexEngine.run
    original_resume = engines.CodexEngine.resume
    original_head = orientation.resolve_head
    original_tree = orientation.snapshot_tree
    previous_root = os.environ.get(cc.STATE_ROOT_ENV)
    with tempfile.TemporaryDirectory(prefix="plan-restatement-successor-") as raw_root:
        state_root = Path(raw_root) / "state"
        log_dir = Path(raw_root) / "logs"
        cc.save_lineage(state_root, cc._from_json(row["lineage"], initial))
        os.environ[cc.STATE_ROOT_ENV] = str(state_root)
        source_tree = _git("rev-parse", f"{revision}^{{tree}}")
        orientation.resolve_head = lambda repo: revision
        orientation.snapshot_tree = lambda repo, parent: source_tree
        invocations = iter(row["exact_invocations"])
        channels = iter(row["exact_attempt_channels"])

        def playback(self, prompt, *args, **kwargs):
            try:
                invocation = next(invocations)
                channel = next(channels)
            except StopIteration as exc:
                raise ValueError("retained successor replay admitted an extra call") from exc
            if _invocation(prompt, args, kwargs) != invocation:
                raise ValueError("retained successor replay invocation changed")
            parsed = engines.CodexEngine().parse_output(channel["raw"])
            return replace(
                parsed, stderr=channel["stderr"],
                failure_detail=channel["failure_detail"],
                returncode=channel["returncode"],
            )

        engines.CodexEngine.run = playback
        engines.CodexEngine.resume = playback
        try:
            handlers.critique_plan({
                "repo_path":str(ROOT), "plan_text":plan,
                "lineage":row["lineage"], "round":round_no,
                "class_closure":True, "claim_verification":False,
                "web_search":False, "model":"gpt-5.6-sol",
                "effort":"high", "stakes":STAKES,
            }, engine=engines.CodexEngine(), log_dir=log_dir,
               now=lambda: row["audit"]["timestamp"])
            return json.loads(
                (cc.lineage_dir(state_root) / f"{row['lineage']}.json").read_text(
                    encoding="utf-8",
                )
            )
        finally:
            engines.CodexEngine.run = original_run
            engines.CodexEngine.resume = original_resume
            orientation.resolve_head = original_head
            orientation.snapshot_tree = original_tree
            if previous_root is None:
                os.environ.pop(cc.STATE_ROOT_ENV, None)
            else:
                os.environ[cc.STATE_ROOT_ENV] = previous_root


def validate_artifact(
    artifact: dict, root: Path = ROOT, *, require_committed: bool = True,
) -> None:
    expected = {
        "acceptance_kind", "version", "date", "source_revision", "source_sha256",
        "allowed_later_source_diffs",
        "provider", "stakes", "discovery", "targeted_control", "final_control",
        "claims",
    }
    if set(artifact) != expected:
        raise ValueError("acceptance envelope is not closed")
    if (
        artifact["acceptance_kind"] != "plan-normative-restatement-public-handler-v2"
        or artifact["version"] != 2 or artifact["date"] != "2026-09-01"
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
    if set(provider) != {"engine", "model", "effort", "web_search"}:
        raise ValueError("provider binding is not closed")
    if provider != {
        "engine":"codex", "model":"gpt-5.6-sol", "effort":"high",
        "web_search":False,
    }:
        raise ValueError("provider route is not the accepted Codex route")

    discovery = artifact["discovery"]
    targeted = artifact["targeted_control"]
    final = artifact["final_control"]
    tree = _git("rev-parse", f"{revision}^{{tree}}")
    source_snapshot = orientation.wrap_commit(root, tree, revision)
    expected_discovery_initial = cc._to_json(
        cc.Lineage(DISCOVERY_LINEAGE, mode=cc.PLAN_MODE)
    )
    expected_targeted_initial = cc._to_json(_targeted_initial(source_snapshot))
    if discovery.get("initial_lineage") != expected_discovery_initial:
        raise ValueError("discovery initial lineage is not source-derived")
    if targeted.get("initial_lineage") != expected_targeted_initial:
        raise ValueError("targeted initial lineage is not source-derived")
    if final.get("initial_lineage") != targeted.get("durable_lineage"):
        raise ValueError("final initial lineage is not the targeted durable successor")
    for row, plan, lineage_id, roles in (
        (discovery, DISCOVERY_PLAN, DISCOVERY_LINEAGE,
         ["census-domain", "census-execution", "census-integrity", "consolidation"]),
        (targeted, TARGETED_PLAN, TARGETED_LINEAGE, ["correction"]),
        (final, TARGETED_PLAN, FINAL_LINEAGE, ["final"]),
    ):
        if set(row) != {
            "lineage", "plan", "prompts", "prompt_sha256", "result_text",
            "result_sha256", "audit_projection", "durable_lineage", "validated_payloads",
            "validated_payload_sha256", "provider_response_sha256",
            "exact_attempt_channels", "exact_invocations", "initial_lineage",
        }:
            raise ValueError("route record is not closed")
        if row["lineage"] != lineage_id or row["plan"] != plan:
            raise ValueError("route input binding changed")
        if row["prompt_sha256"] != [_sha_text(item) for item in row["prompts"]]:
            raise ValueError("prompt digest mismatch")
        if row["prompts"] != _reconstruct_prompts(row, roles):
            raise ValueError("retained prompts differ from production reconstruction")
        if len(row["exact_invocations"]) != len(row["prompts"]):
            raise ValueError("exact invocation inventory does not match provider calls")
        if row["result_sha256"] != _sha_text(row["result_text"]):
            raise ValueError("result digest mismatch")
        attempts = row["audit_projection"].get("attempt_ledger")
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
                else f'"role": "{role}"'
            )
            required_channels = (
                "raw_sha256", "response_sha256", "failure_detail_sha256",
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
                "raw", "returncode",
            }
            if set(channels) != exact_fields:
                raise ValueError("raw provider channel envelope is not closed")
            if (
                type(channels["returncode"]) is not int
                or type(attempt.get("returncode")) is not int
            ):
                raise ValueError("provider return code must be an exact integer")
            parsed = engines.CodexEngine().parse_output(channels["raw"])
            derived = {
                "session_ref":parsed.session_ref,
                "response_sha256":_sha_text(parsed.text),
                "raw_sha256":_sha_text(parsed.raw),
                "failure_detail_sha256":_sha_text(parsed.failure_detail or ""),
                "usage":parsed.usage,
            }
            if any(attempt.get(key) != value for key, value in derived.items()):
                raise ValueError("audit attempt does not derive from raw provider stdout")
            if attempt.get("returncode") != channels["returncode"]:
                raise ValueError("audit return code does not match retained process status")
            for value, excerpt_key in (
                (parsed.text, "response_excerpt"),
                (parsed.raw, "raw_excerpt"),
                (parsed.failure_detail or "", "failure_detail_excerpt"),
            ):
                if value[:4000] != (attempt.get(excerpt_key) or ""):
                    raise ValueError("audit excerpt does not derive from raw provider stdout")
            if parsed.error or attempt.get("outcome") != "completed":
                raise ValueError("accepted provider stdout does not represent completion")
        for prompt, invocation in zip(
            row["prompts"], row["exact_invocations"], strict=True,
        ):
            if set(invocation) != {
                "prompt_sha256", "model", "effort", "timeout", "web_search",
                "response_schema_sha256", "response_schema",
            }:
                raise ValueError("provider invocation is not closed")
            schema_text = json.dumps(
                invocation["response_schema"], ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            )
            if (
                invocation["prompt_sha256"] != _sha_text(prompt)
                or invocation["model"] != "gpt-5.6-sol"
                or invocation["effort"] != "high"
                or invocation["web_search"] is not False
                or invocation["response_schema_sha256"] != _sha_text(schema_text)
            ):
                raise ValueError("provider invocation differs from its retained route")
        expected_payloads = {
            "manifests":row["audit_projection"].get("staged_manifests") or [],
            "settlement":row["audit_projection"].get("staged_settlement"),
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
        if not row["result_text"].endswith(
            row["audit_projection"].get("rendered_trailer", "")
        ):
            raise ValueError("rendered trailer is not the returned durable result")

    _replay_public_handler(artifact, tree)

    findings = discovery["audit_projection"]["staged_settlement"]["findings"]
    settlement = discovery["audit_projection"]["staged_settlement"]
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
    settlement = targeted["audit_projection"]["staged_settlement"]
    if settlement["findings"] or targeted["durable_lineage"]["review_state"]["phase"] != "final":
        raise ValueError("targeted correction discovered unrelated novelty or failed to close")
    if any(
        _anchor_covers(anchor, line)
        for row in settlement["findings"] for anchor in row["evidence"]
        for line in (13, 14)
    ):
        raise ValueError("targeted correction audited the unrelated restatement cluster")
    final_findings = final["audit_projection"]["staged_settlement"]["findings"]
    if len(final_findings) != 1 or not all(
        any(_anchor_covers(anchor, line) for anchor in final_findings[0]["evidence"])
        for line in (13, 14)
    ):
        raise ValueError("cold final did not discover the complete unrelated restatement cluster")
    if final["durable_lineage"]["review_state"]["phase"] != "correction":
        raise ValueError("cold final did not persist its newly discovered blocking debt")
    if artifact["claims"] != CLAIMS:
        raise ValueError("acceptance claims are not exact")


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
        invocations = json.loads((log_dir / "exact_invocations.json").read_text(
            encoding="utf-8",
        ))
        # The first retained run recorded keyword arguments exactly but omitted the
        # four positional Engine.run arguments. They are closed constants of this
        # source-bound harness and are reconstructed here; public-handler replay below
        # proves that the production call accepts exactly this completed invocation.
        for invocation in invocations:
            if invocation.get("model") is None:
                invocation.update(
                    model="gpt-5.6-sol", effort="high", web_search=False,
                )
        for channel in channels:
            if "error" not in channel or "usage" not in channel:
                parsed = engines.CodexEngine().parse_output(channel["raw"])
                channel["error"] = parsed.error
                channel["usage"] = parsed.usage
        state_name = "targeted" if name == "final" else name
        lineage = json.loads(
            (run_root / f"{state_name}-state" / "lineages" / f"{lineage_id}.json").read_text(
                encoding="utf-8",
            )
        )
        review = engines.Review(
            text=audit["text"], session_ref=audit["session_ref"], raw=audit["text"],
        )
        result = handlers._footer(review, engines.CodexEngine())
        result += "\n\n" + audit["rendered_trailer"]
        return result, prompts, audit, lineage, channels, invocations

    if args.reuse_run_root:
        discovery = retained_route("discovery", DISCOVERY_LINEAGE)
        targeted = list(retained_route("targeted", TARGETED_LINEAGE))
        final = retained_route("final", FINAL_LINEAGE)
        targeted_initial = cc._from_json(
            TARGETED_LINEAGE,
            json.loads((run_root / "targeted-initial.json").read_text(encoding="utf-8")),
        )
        targeted[3] = _reconstruct_retained_successor(
            initial=cc._to_json(targeted_initial),
            row={
                "lineage":TARGETED_LINEAGE, "audit":targeted[2],
                "exact_attempt_channels":targeted[4],
                "exact_invocations":targeted[5],
            },
            plan=TARGETED_PLAN, round_no=2, revision=revision,
        )
        targeted = tuple(targeted)
    else:
        discovery = _capture_call({
            "repo_path":str(ROOT), "plan_text":DISCOVERY_PLAN,
            "lineage":DISCOVERY_LINEAGE, "round":1, "class_closure":True,
            "claim_verification":False, "web_search":False,
            "model":"gpt-5.6-sol", "effort":"high", "stakes":STAKES,
        }, state_root=run_root / "discovery-state", log_dir=run_root / "discovery-logs")
        targeted_state = run_root / "targeted-state"
        targeted_initial = _targeted_seed(targeted_state)
        (run_root / "targeted-initial.json").write_text(
            json.dumps(cc._to_json(targeted_initial), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        targeted = _capture_call({
            "repo_path":str(ROOT), "plan_text":TARGETED_PLAN,
            "lineage":TARGETED_LINEAGE, "round":2, "class_closure":True,
            "claim_verification":False, "web_search":False,
            "model":"gpt-5.6-sol", "effort":"high", "stakes":STAKES,
        }, state_root=targeted_state, log_dir=run_root / "targeted-logs")
        final = _capture_call({
            "repo_path":str(ROOT), "plan_text":TARGETED_PLAN,
            "lineage":FINAL_LINEAGE, "round":3, "class_closure":True,
            "claim_verification":False, "web_search":False,
            "model":"gpt-5.6-sol", "effort":"high", "stakes":STAKES,
        }, state_root=targeted_state, log_dir=run_root / "final-logs")

    empty_initial = cc.Lineage(DISCOVERY_LINEAGE, mode=cc.PLAN_MODE)
    def route(lineage_id: str, plan: str, value: tuple, initial: cc.Lineage | dict) -> dict:
        result, prompts, audit, lineage, channels, invocations = value
        validated_payloads = {
            "manifests":audit.get("staged_manifests") or [],
            "settlement":audit.get("staged_settlement"),
        }
        return {
            "lineage":lineage_id, "plan":plan, "prompts":prompts,
            "prompt_sha256":[_sha_text(item) for item in prompts],
            "result_text":result, "result_sha256":_sha_text(result),
            "audit_projection":_audit_projection(audit),
            "durable_lineage":lineage,
            "validated_payloads":validated_payloads,
            "validated_payload_sha256":_sha_text(json.dumps(
                validated_payloads, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            )),
            "provider_response_sha256":[
                item["response_sha256"] for item in audit["attempt_ledger"]
            ],
            "exact_attempt_channels":[
                {"raw":item["raw"], "returncode":item["returncode"]}
                for item in channels
            ],
            "exact_invocations":invocations,
            "initial_lineage":(
                cc._to_json(initial) if isinstance(initial, cc.Lineage) else initial
            ),
        }

    artifact = {
        "acceptance_kind":"plan-normative-restatement-public-handler-v2",
        "version":2, "date":"2026-09-01", "source_revision":revision,
        "source_sha256":{
            relative:_sha_bytes(subprocess.run(
                ["git", "show", f"{revision}:{relative}"], cwd=ROOT, check=True,
                stdout=subprocess.PIPE,
            ).stdout) for relative in SOURCES
        },
        "allowed_later_source_diffs":{},
        "provider":{
            "engine":"codex", "model":"gpt-5.6-sol", "effort":"high",
            "web_search":False,
        },
        "stakes":STAKES,
        "discovery":route(DISCOVERY_LINEAGE, DISCOVERY_PLAN, discovery, empty_initial),
        "targeted_control":route(
            TARGETED_LINEAGE, TARGETED_PLAN, targeted, targeted_initial,
        ),
        "final_control":route(
            FINAL_LINEAGE, TARGETED_PLAN, final, targeted[3],
        ),
        "claims":CLAIMS,
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
