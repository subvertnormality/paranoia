#!/usr/bin/env python3
"""Retain real-provider evidence for proactive plan-restatement discovery."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paranoia_local import class_closure as cc
from paranoia_local import engines, handlers, orientation, review_census as rc

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
Change only src/paranoia_local/prompts.py and tests/test_prompts.py.

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
) -> tuple[str, list[str], dict, dict]:
    prompts: list[str] = []
    original_run = engines.CodexEngine.run
    original_resume = engines.CodexEngine.resume

    def capture_run(self, prompt, *args, **kwargs):
        prompts.append(prompt)
        return original_run(self, prompt, *args, **kwargs)

    def capture_resume(self, session_ref, prompt, *args, **kwargs):
        prompts.append(prompt)
        return original_resume(self, session_ref, prompt, *args, **kwargs)

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
    return result, prompts, audit, lineage


def _targeted_seed(state_root: Path) -> None:
    parent = orientation.resolve_head(ROOT)
    snapshot = orientation.wrap_commit(
        ROOT, orientation.snapshot_tree(ROOT, parent), parent,
    )
    structural = rc.digest(f"{TARGETED_PLAN}\0{snapshot}")
    state = rc.normalize_state(None, stakes=STAKES, snapshot=structural)
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


def validate_artifact(
    artifact: dict, root: Path = ROOT, *, require_committed: bool = True,
) -> None:
    expected = {
        "acceptance_kind", "version", "date", "source_revision", "source_sha256",
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
    for relative, digest in artifact["source_sha256"].items():
        historical = subprocess.run(
            ["git", "show", f"{revision}:{relative}"], cwd=root, check=True,
            stdout=subprocess.PIPE,
        ).stdout
        if _sha_bytes(historical) != digest or (root / relative).read_bytes() != historical:
            raise ValueError(f"source binding mismatch for {relative}")
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
            "result_sha256", "audit", "durable_lineage",
        }:
            raise ValueError("route record is not closed")
        if row["lineage"] != lineage_id or row["plan"] != plan:
            raise ValueError("route input binding changed")
        if row["prompt_sha256"] != [_sha_text(item) for item in row["prompts"]]:
            raise ValueError("prompt digest mismatch")
        if row["result_sha256"] != _sha_text(row["result_text"]):
            raise ValueError("result digest mismatch")
        attempts = row["audit"].get("attempt_ledger")
        if [item.get("role") for item in attempts or []] != roles:
            raise ValueError("provider call topology changed")
        if any(item.get("outcome") != "completed" for item in attempts):
            raise ValueError("acceptance contains a failed provider attempt")
        if not row["result_text"].endswith(row["audit"].get("rendered_trailer", "")):
            raise ValueError("rendered trailer is not the returned durable result")

    findings = discovery["audit"]["staged_settlement"]["findings"]
    matches = [
        row for row in findings
        if "independently normative" in row["summary"].lower()
        or "sources of authority" in row["summary"].lower()
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
    args = parser.parse_args()
    if args.validate_only:
        validate_artifact(json.loads(args.output.read_text(encoding="utf-8")))
        return 0
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("commit bound source changes before generating acceptance")
    revision = _git("rev-parse", "HEAD")
    run_root = Path(tempfile.mkdtemp(prefix="plan-restatement-acceptance-"))
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
        result, prompts, audit, lineage = value
        return {
            "lineage":lineage_id, "plan":plan, "prompts":prompts,
            "prompt_sha256":[_sha_text(item) for item in prompts],
            "result_text":result, "result_sha256":_sha_text(result),
            "audit":audit, "durable_lineage":lineage,
        }

    artifact = {
        "acceptance_kind":"plan-normative-restatement-public-handler-v1",
        "version":1, "date":"2026-09-01", "source_revision":revision,
        "source_sha256":{
            relative:_sha_bytes((ROOT / relative).read_bytes()) for relative in SOURCES
        },
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
    validate_artifact(artifact, require_committed=False)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
